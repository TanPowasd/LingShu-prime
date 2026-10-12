# -*- coding: utf-8 -*-
"""引擎侧版本链索引：写入期零 LLM 登记版本事件（持久化在同一 SQLite 库的 chain_events 表），
召回期按题面路由，把「当前（时点）版本段 → 别名声明段 → 变更链段（编年）」排在基础召回之前。

开关：``LINGSHU_NG_CHAIN=1``（引擎构造时读取）或 ``MemoryEngine.enable_chain()``；默认关闭，关闭时
引擎行为与 ng 完全一致（不建表、不登记、不改召回）。对外 API 不变：``recall`` 仍返回 ``[(Node, score)]``；
另加只读的 ``chain_answer(question)``（结构化现值/历史/变更链/四态/缘由，带来源原文）。

一致性约定：事件挂在来源节点 id 上；节点被删除/退役后，其事件在召回编排里被跳过（查询时按存在性过滤），
但账本里的版本事实本身不回滚（与 ng「派生索引」口径一致；需要时可 ``rebuild()`` 从现存节点全量重建）。"""
from __future__ import annotations

import os
import threading
from typing import Dict, List, Optional, Tuple

from .extract import extract, parse_header, split_sentences
from .ledger import Ledger, Rec
from .reader import answer, plan
from .route import route

__all__ = ["ChainIndex", "ENV_KEY", "env_enabled"]

ENV_KEY = "LINGSHU_NG_CHAIN"

_DDL = """
CREATE TABLE IF NOT EXISTS chain_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id TEXT NOT NULL, ns TEXT NOT NULL, entity TEXT NOT NULL, attr TEXT, op TEXT NOT NULL,
  value TEXT, alt TEXT, reason TEXT, seq INTEGER NOT NULL, line INTEGER NOT NULL, quote TEXT NOT NULL,
  rename_from_seq INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chain_events_key ON chain_events(ns, entity, attr, seq);
CREATE INDEX IF NOT EXISTS idx_chain_events_node ON chain_events(node_id);
CREATE TABLE IF NOT EXISTS chain_segments (node_id TEXT PRIMARY KEY, ns TEXT NOT NULL, seq INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_chain_segments_ns_seq ON chain_segments(ns, seq);
"""


def env_enabled() -> bool:
    return os.environ.get(ENV_KEY, "").strip().lower() in ("1", "true", "yes", "on")


class ChainIndex:
    def __init__(self, store, order: str = "chrono") -> None:
        self.store = store
        self.order = order
        #: 非变更类问最多前置多少个编排段（None/0＝不限，至多 limit）；其余名额留给基础召回。
        #: v2 默认 3：抽取只覆盖部分事件句时，账本的「当前版本」可能其实是旧版本——只前置 3 段、其余交还基础召回，
        #: 把「编排压掉了基础召回本来命中的正确段」的损失压低（dev 扰动 50%：逐题 gold@6 负 12→1；干净语料不变）。
        self.max_promote: Optional[int] = 3
        #: 编排段放法：front＝全部前置；interleave＝编排段与基础召回交错（编排段先）
        self.place = "front"
        #: 共现守卫：同命名空间、晚于账本当前版本且不晚于时点的段里「同句共现实体与属性、却没解析成事件」者先交出
        self.co_guard = True
        self.ledger = Ledger()
        self._lock = threading.RLock()
        with store.db.tx() as c:
            for stmt in _DDL.split(";"):
                if stmt.strip():
                    c.execute(stmt)
        self._load()

    # ------------------------------------------------------------ 持久化
    def _load(self) -> None:
        for r in self.store.db.all("SELECT node_id, ns, entity, attr, op, value, alt, reason, seq, line, quote, "
                                   "rename_from_seq FROM chain_events ORDER BY id"):
            self.ledger.add_rec(Rec(r[1], r[2], r[3], r[4], r[5], r[6], r[7], int(r[8]), int(r[9]), r[0], r[10], r[11]))
        for nid, ns, seq in self.store.db.all("SELECT node_id, ns, seq FROM chain_segments"):
            self.ledger._ns_counter[ns] = max(self.ledger._ns_counter.get(ns, 0), int(seq))
            self.ledger._ns_max[ns] = max(self.ledger._ns_max.get(ns, 0), int(seq))

    def note(self, node_id: str, content: str) -> int:
        """登记一个新写入节点的版本事件（零 LLM）。同一节点重复登记被忽略。返回登记事件数。"""
        if not isinstance(content, str) or not content:
            return 0
        with self._lock:
            if self.store.db.one("SELECT 1 FROM chain_segments WHERE node_id=?", (node_id,)) is not None:
                return 0
            h = parse_header(content)
            ns = h.ns or ""
            seq = h.seq if h.seq is not None else self.ledger._ns_counter.get(ns, 0) + 1
            recs = self.ledger.add_text(content, ref=node_id, seq=seq, ns=ns)
            with self.store.db.tx() as c:
                c.execute("INSERT OR IGNORE INTO chain_segments(node_id, ns, seq) VALUES (?,?,?)", (node_id, ns, seq))
                c.executemany("INSERT INTO chain_events(node_id, ns, entity, attr, op, value, alt, reason, seq, line, "
                              "quote, rename_from_seq) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                              [(r.ref, r.ns, r.entity, r.attr, r.op, r.value, r.alt, r.reason, r.seq, r.line, r.quote,
                                r.rename_from_seq) for r in recs])
            return len(recs)

    def rebuild(self) -> int:
        """从现存知识节点全量重建账本（按写入时间序）。"""
        with self._lock:
            with self.store.db.tx() as c:
                c.execute("DELETE FROM chain_events")
                c.execute("DELETE FROM chain_segments")
            self.ledger = Ledger()
            n = 0
            for nid, content in self.store.db.all("SELECT id, content FROM nodes ORDER BY created_at, rowid"):
                n += self.note(nid, content)
            return n

    # ------------------------------------------------------------ 读
    def _alive(self, ids: List[str], exclude=frozenset()) -> List[str]:
        """只留仍在库、在可检索层、未归档（与基础召回同一过滤口径 Q5）、且不在 exclude 里的节点。"""
        if not ids:
            return []
        from ..retrieval import _layer_values, _retired
        use = _layer_values(None)
        ok = set()
        for i in range(0, len(ids), 500):
            part = ids[i:i + 500]
            ph = ",".join("?" * len(part))
            for nid, imp, tj, layer in self.store.db.all(
                    f"SELECT id, importance, tags, layer FROM nodes WHERE id IN ({ph})", part):
                if layer in use and not _retired(imp, tj) and nid not in exclude:
                    ok.add(nid)
        return [i for i in ids if i in ok]

    def _co_scan(self, window: int = 50):
        """共现守卫的候选来源：同命名空间、序号落在 (账本当前版本, 时点] 的段（从最新往回至多 window 段）。"""
        def co(ns, names, attr, lo, hi, window=window):
            if not attr or hi <= lo:
                return []
            rows = self.store.db.all("SELECT s.node_id, s.seq, n.content FROM chain_segments s JOIN nodes n ON n.id = s.node_id "
                                     "WHERE s.ns=? AND s.seq>? AND s.seq<=? ORDER BY s.seq DESC LIMIT ?",
                                     (ns, lo, min(hi, 2 ** 62), window))
            out = []
            for nid, sq, content in rows:
                for sent in split_sentences(content or ""):
                    if attr in sent and any(n in sent for n in names) and not extract(sent):
                        out.append((nid, int(sq)))
                        break
            return out
        return co

    def _ns_pref(self, hits) -> List[str]:
        """基础召回里各命名空间首次出现的先后（同名实体跨命名空间而题面无法消歧时，用它排先后）。"""
        ids = [getattr(n, "id", None) for n, _ in hits][:20]
        ids = [i for i in ids if i]
        if not ids:
            return []
        ph = ",".join("?" * len(ids))
        m = dict(self.store.db.all(f"SELECT node_id, ns FROM chain_segments WHERE node_id IN ({ph})", ids))
        out: List[str] = []
        for i in ids:
            if i in m and m[i] not in out:
                out.append(m[i])
        return out

    def route_recall(self, query: str, hits: List[Tuple[object, float]], limit: int, fetch,
                     pool=None) -> List[Tuple[object, float]]:
        """把编排出的版本段排到基础召回之前（去重、截 limit）。题面落不到账本键时原样返回。
        pool：保留参数（兼容）；共现守卫直接按 (命名空间, 序号区间) 扫段，见 :meth:`_co_scan`。"""
        co = self._co_scan() if self.co_guard else None
        with self._lock:
            refs = plan(self.ledger, query, self.order, co=co, ns_pref=self._ns_pref(hits))
        cap = limit
        if self.max_promote and route(query).intent != "change":
            cap = min(limit, self.max_promote)
        refs = self._alive(refs)[:cap]
        if not refs:
            return hits
        nodes = fetch(refs)
        chain = [nodes[r] for r in refs if r in nodes]
        got = {n.id for n in chain}
        base = [n for n, _ in hits if n.id not in got]
        if self.place == "interleave" and route(query).intent != "change":
            seq, i, j = [], 0, 0
            while len(seq) < limit and (i < len(chain) or j < len(base)):
                if i < len(chain) and (len(seq) % 2 == 0 or j >= len(base)):
                    seq.append(chain[i]); i += 1
                elif j < len(base):
                    seq.append(base[j]); j += 1
        else:
            seq = (chain + base)[:limit]
        top = max([s for _, s in hits] + [1.0])
        return [(n, round(top + (len(seq) - k) * 1e-3, 6)) for k, n in enumerate(seq)]

    def answer(self, question: str) -> Dict:
        with self._lock:
            return answer(self.ledger, question)

    def stats(self) -> Dict:
        return {"events": len(self.ledger.recs), "namespaces": len(self.ledger.namespaces()),
                "keys": len(self.ledger._by_key)}
