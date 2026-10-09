# -*- coding: utf-8 -*-
"""semindex · 可选的第二路召回：注入式语义索引（M1 语义检索提供者，duck-typed 注入 · D-005）

旧项目在 M1 声明了「语义检索提供者」注入口（integrated ``core.py:2539`` ``_embedding_provider``、
``set_embedding_provider``「provider.encode(text)->List[float]；provider.search(query,limit)->List[str]」
``core.py:3163-3165``），核心零外部 import；但从未接进召回。本模块把它接上，规则：

  S1 写入路径不变：原文照旧零 LLM 落库；向量只是**派生索引**，不进主库、不参与完整性/导出。
     写入期只把 (id, 原文) 放进待编码队列（O(1)）；编码在后台线程批量做（或查询前补齐），可随时丢弃重建。
  S2 查询前补齐：按 nodes.rowid 水位扫一次新行（覆盖不经 perceive 的写入口与重开后的旧库），
     把队列编码完再检索（索引与库一致，不返回过期结果）。
  S3 融合：词面组合召回（Q4–Q8）的名次与语义名次按 :data:`PATTERN` 交错（L=词面、D=语义，跳过已入选者），
     语义候选同样过 exclude / 退役 / 可检索层过滤；随后照常做 Q6 对侧补全。
  S4 无提供者 ⇒ 完全不生效（默认配置不变）；提供者出错 ⇒ 记录 ``error`` 并退回纯词面，不影响写入与召回。

提供者两种形态（都可）：
  * 自带索引：``add(ids, texts)`` + ``search(query, limit) -> [(id, score)] 或 [id]``（如 lingshu_ng.embed）；
  * 只有 ``encode(text) -> List[float]``：本模块在内存里保存向量，查询时纯 Python 余弦（小库可用，大库慢）。
"""
from __future__ import annotations

import math
import threading
import time
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = ["SemanticIndex", "PATTERN", "interleave"]

#: 交错样式：L = 词面名次、D = 语义名次（HMB 零 LLM 检索轨实测，见 evalsuite_hard/hmbq/ITER_HMBQ.md）
PATTERN = "LDD"
#: 后台线程一次编码的批大小
BATCH = 16
#: 水位扫描每页行数
PAGE = 2000


def interleave(lex: Sequence[str], sem: Sequence[str], limit: int, pattern: str = PATTERN) -> List[str]:
    """按 pattern 交错两路名次（去重）；一路用尽时由另一路补满。"""
    out: List[str] = []
    seen = set()
    its = {"L": iter(lex), "D": iter(sem)}
    k, dry = 0, set()
    while len(out) < limit and len(dry) < 2:
        src = pattern[k % len(pattern)] if len(pattern) else "L"
        src = src if src not in dry else ("D" if src == "L" else "L")
        k += 1
        for nid in its[src]:
            if nid not in seen:
                out.append(nid)
                seen.add(nid)
                break
        else:
            dry.add(src)
    return out


class _VecTable:
    """只有 encode 的提供者：内存向量表 + 纯 Python 余弦。"""

    def __init__(self, provider) -> None:
        self.p = provider
        self.v: Dict[str, Tuple[float, ...]] = {}

    def add(self, ids: Sequence[str], texts: Sequence[str]) -> None:
        """编码并保存（L2 归一）。"""
        for nid, t in zip(ids, texts):
            x = [float(a) for a in self.p.encode(t)]
            n = math.sqrt(sum(a * a for a in x)) or 1.0
            self.v[nid] = tuple(a / n for a in x)

    def search(self, query: str, limit: int) -> List[Tuple[str, float]]:
        """余弦前 limit 名。"""
        q = [float(a) for a in self.p.encode(query)]
        n = math.sqrt(sum(a * a for a in q)) or 1.0
        sc = [(nid, sum(a * b for a, b in zip(q, v)) / n) for nid, v in self.v.items()]
        sc.sort(key=lambda x: (-x[1], x[0]))
        return sc[:limit]


class SemanticIndex:
    """派生语义索引（绑定一个 Store 与一个提供者）。线程安全：提供者调用全部经 ``self._plock``。"""

    def __init__(self, store, provider, background: bool = True) -> None:
        self.store = store
        self.provider = provider if hasattr(provider, "search") and hasattr(provider, "add") else _VecTable(provider)
        self.error: Optional[str] = None
        self.encoded = 0
        self.encode_sec = 0.0
        self._known: set = set()
        self._pending: List[Tuple[str, str]] = []
        self._qlock = threading.Lock()
        self._plock = threading.Lock()
        self._wake = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._stop = False
        self._mark = 0
        self._inflight = 0
        self._thread: Optional[threading.Thread] = None
        if background:
            self._thread = threading.Thread(target=self._loop, name="ng-semindex", daemon=True)
            self._thread.start()

    # ------------------------------------------------------------ 写入期（O(1)）
    def note(self, node_id: str, text: str) -> None:
        """写入钩子：入队待编码（不编码、不读库）。"""
        if self.error is not None or not isinstance(text, str) or not text.strip():
            return
        with self._qlock:
            if node_id in self._known:
                return
            self._known.add(node_id)
            self._pending.append((node_id, text))
            self._idle.clear()
        self._wake.set()

    # ------------------------------------------------------------ 编码
    def _take(self) -> List[Tuple[str, str]]:
        with self._qlock:
            part, self._pending = self._pending[:BATCH], self._pending[BATCH:]
            self._inflight += len(part)
            return part

    def _done(self, n: int) -> None:
        with self._qlock:
            self._inflight -= n
            if not self._pending and self._inflight == 0:
                self._idle.set()

    def _encode(self, part: List[Tuple[str, str]]) -> None:
        t0 = time.perf_counter()
        try:
            with self._plock:
                self.provider.add([a for a, _ in part], [b for _, b in part])
        except Exception as e:  # 提供者是外部注入件：任何失败都退回纯词面（S4），不影响写入与召回
            self.error = f"{type(e).__name__}: {e}"
            with self._qlock:
                self._pending.clear()
            self._done(len(part))
            return
        self.encoded += len(part)
        self.encode_sec += time.perf_counter() - t0
        self._done(len(part))

    def _loop(self) -> None:
        while not self._stop:
            self._wake.wait(0.5)
            self._wake.clear()
            while not self._stop and self.error is None:
                part = self._take()
                if not part:
                    break
                self._encode(part)

    def catch_up(self) -> int:
        """S2：按 rowid 水位把未入队的新行（含旧库已有行、非 perceive 写入）入队；返回新入队数。"""
        n = 0
        while True:
            rows = self.store.db.all("SELECT rowid, id, content FROM nodes WHERE rowid > ? ORDER BY rowid LIMIT ?",
                                     (self._mark, PAGE))
            if not rows:
                return n
            for rid, nid, content in rows:
                with self._qlock:
                    fresh = nid not in self._known
                if fresh:
                    self.note(nid, content)
                    n += 1
            self._mark = rows[-1][0]

    def sync(self) -> None:
        """补齐水位并把队列编码完（调用线程里直接编码，不等后台线程）。"""
        self.catch_up()
        while self.error is None:
            part = self._take()
            if not part:
                break
            self._encode(part)
        # 后台线程可能正持有最后一批：等它编完
        while self.error is None and not self._idle.wait(1.0):
            if self._thread is None or not self._thread.is_alive():
                break

    # ------------------------------------------------------------ 查询
    def search(self, query: str, limit: int) -> List[Tuple[str, float]]:
        """语义前 limit 名 [(id, score)]；提供者失效时返回 []。"""
        if self.error is not None:
            return []
        self.sync()
        if self.error is not None:
            return []
        try:
            with self._plock:
                res = list(self.provider.search(query, int(limit)))
        except Exception as e:  # 同 _encode：退回纯词面
            self.error = f"{type(e).__name__}: {e}"
            return []
        return [(r, 0.0) if isinstance(r, str) else (str(r[0]), float(r[1])) for r in res]

    def stats(self) -> Dict:
        """编码计数与累计耗时（摊销成本报告用）。"""
        return {"encoded": self.encoded, "encode_sec": round(self.encode_sec, 4), "pending": len(self._pending),
                "error": self.error}

    def close(self) -> None:
        """停后台线程。"""
        self._stop = True
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
