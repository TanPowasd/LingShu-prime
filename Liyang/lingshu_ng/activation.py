# -*- coding: utf-8 -*-
"""activation · 扩散激活引擎（工作态 / 自条件 / 审计），纯标准库

旧实现的缺陷类别：无保护 ``import numpy``（击穿轻核承诺 #7）、空查询把全图当种子满分(#199/#161)、
空图抛 ValueError(#95)、SciPy 图缓存不刷新(#126)、公式声明 max 而实现 Σ(#53)、
OPPOSITE 边按 0.5 兴奋传导、工作态不带极性(#229)、种子落表记成 propagate 且 hop 恒 0
(core2-new-05)、``:memory:`` 每次连到新空库(core-rest-08)。

不变量：
  A1 空/纯空白查询 ⇒ 0 个种子、空工作态（status=ok）；空图同理。
  A2 每次 activate 看到的都是库的当前拓扑：派生图（规范化文本 + 出边邻接）按连接的
     **提交指纹**（``PRAGMA data_version`` + ``total_changes``）缓存，任何连接对库的任何提交、
     本连接的任何增删改都会令指纹变化 ⇒ 下次激活整体重读（从不读到过期图；#126 的反面）。
     本引擎自己写 activation_nodes 不改图，写后在同一把锁内顺延指纹。
  A3 传播 = 逐跳 max-product：act(v) ← max(act(v), act(u)·decay(type))；兴奋与抑制分通道，
     （实现只沿「上一跳值有变化」的前沿节点的出边松弛——值未变的节点其贡献上一跳已计入且通道
     单调不降，结果与逐跳全边扫描逐位相同）；
     OPPOSITE 边只进抑制通道；净激活 = 兴奋 − 抑制，被抑制节点以 polarity=-1 落表、
     不进入下一轮自条件先验。
  A4 落表 source ∈ {seed, self_condition, propagate}，hop = 首次被激活的跳数。
  A5 SELF 层不做种子（与检索同一层规则）。
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from collections import Counter
from itertools import compress, repeat
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from .dedup import normalize, normalize_many
from .layers import LayerPolicy
from .numeric import unit
from .store.db import Database
from .types import now

__all__ = ["ActivationEngine", "EDGE_BASE_DECAY", "INHIBITORY", "SELF_CONDITION_WEIGHT", "ALGO"]

ALGO = "activation-ng-0.1"
_DATA_ROOT = os.environ.get("LINGSHU_DATA_ROOT", "data")
DB = os.path.join(_DATA_ROOT, "aeis_memory.db")
AUDIT_PATH = os.path.join(_DATA_ROOT, "activation_audit.jsonl")
EDGE_BASE_DECAY: Dict[str, float] = {
    "causal": 0.85, "similar": 0.75, "counterpart": 0.75, "hierarchical": 0.70,
    "sequential": 0.60, "spatial_adjacent": 0.50, "spatial_contains": 0.50,
    "spatial_connected": 0.50, "opposite": 0.80,
}
INHIBITORY = frozenset({"opposite"})
DEFAULT_DECAY = 0.5
SELF_CONDITION_WEIGHT = 0.5


class _RawPort:
    """借用的原始 sqlite3 连接（所有权在调用方，绝不关闭）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """内部辅助函数。"""
        self.conn = conn
        self.lock = threading.RLock()

    def all(self, sql: str, params: Sequence[Any] = ()) -> List[Any]:
        """锁内执行查询并取全部行。"""
        with self.lock:
            return self.conn.execute(sql, tuple(params)).fetchall()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """借用连接上的事务：成功 commit，异常 rollback。"""
        with self.lock:
            try:
                yield self.conn
            except BaseException:
                self.conn.rollback()
                raise
            self.conn.commit()


def _port(db_path: str, conn: Optional[sqlite3.Connection], store: Any) -> Any:
    """内部辅助函数。"""
    db = getattr(store, "db", None) if store is not None else None
    if isinstance(db, Database):
        return db
    if conn is None and store is not None:
        conn = store.conn
    if conn is not None:
        port = _RawPort(conn)
        with port.tx() as c:
            c.execute("CREATE TABLE IF NOT EXISTS activation_nodes (id TEXT PRIMARY KEY, workset TEXT "
                      "NOT NULL, node_id TEXT NOT NULL, activation REAL NOT NULL, source TEXT NOT NULL, "
                      "hop INTEGER NOT NULL, ts REAL NOT NULL, polarity INTEGER DEFAULT 1)")
        return port
    if db_path == ":memory:":
        raise ValueError("ActivationEngine: ':memory:' 每次连接都是新空库，请传 conn= 或 store= 共享连接")
    return Database(db_path)


class ActivationEngine:
    """认知图上的工作态维护器。签名与旧版一致：(db_path, audit_path, conn=None, store=None)。"""

    def __init__(self, db_path: str = DB, audit_path: str = AUDIT_PATH,
                 conn: Optional[sqlite3.Connection] = None, store: Any = None) -> None:
        """内部辅助函数。"""
        self.db_path = db_path
        self.audit_path = audit_path
        self.port = _port(db_path, conn, store)

    # ------------------------------------------------------------ 读图（A2）
    def _conn(self) -> sqlite3.Connection:
        """内部辅助函数。"""
        return self.port.conn

    def _fingerprint(self) -> Tuple[int, int]:
        """库的提交指纹：其它连接提交 ⇒ data_version 变；本连接增删改 ⇒ total_changes 变。"""
        c = self._conn()
        with self.port.lock:
            return int(c.execute("PRAGMA data_version").fetchone()[0]), int(c.total_changes)

    def _derived(self) -> "_GraphView":
        """当前拓扑的派生图（指纹未变则复用，否则整体重读）。"""
        fp = self._fingerprint()
        view = getattr(self, "_view", None)
        if view is None or view.fp != fp:
            view = self._view = _GraphView.load(self.port, fp, view)
        return view

    def _graph(self) -> Tuple[Dict[str, Tuple[str, bool]], List[Tuple[str, str, str]]]:
        """参考读图（旧口径，逐条从库读出、不缓存）：(节点 → (规范化文本, 可做种子), 边 [(src, dst, relation)] 按 rowid)。
        ``activate`` 走 :meth:`_derived` 的派生图；二者对种子与传播给出相同结果（性质测试守护）。"""
        cond, params = LayerPolicy.layers_where("layer", searchable=True)
        texts = {}
        for nid, content, tags, ok in self.port.all(f"SELECT id, content, tags, ({cond}) FROM nodes", params):
            texts[nid] = (normalize((content or "") + " " + _tag_text(tags)), bool(ok))
        arcs = [(r[0], r[1], r[2]) for r in self.port.all(
            "SELECT source_id, target_id, relation_type FROM edges ORDER BY rowid")]
        return texts, arcs

    @staticmethod
    def _seeds(query: str, texts: Dict[str, Tuple[str, bool]], top_k: int) -> List[Tuple[str, float]]:
        """参考实现（逐节点扫描）；``activate`` 走 :meth:`_GraphView.seeds`，结果逐项相同。"""
        q = normalize(query)
        if not q:
            return []                                                  # A1
        toks = {q[i:i + 2] for i in range(len(q) - 1)} | {q}
        scores = []
        for nid, (hay, seedable) in texts.items():
            if not seedable:
                continue                                               # A5
            s = sum(1 for t in toks if t in hay) / len(toks)
            if s > 0:
                scores.append((nid, round(s, 6)))
        scores.sort(key=lambda x: (-x[1], x[0]))
        return scores[:top_k]

    @staticmethod
    def _propagate(pos: Dict[str, float], arcs: Sequence[Tuple[str, str, str]], hops: int,
                   first_hop: Dict[str, int], trace: Optional[List[Dict]] = None,
                   floor: float = 0.0) -> Dict[str, float]:
        """A3 参考实现（逐跳全边扫描）；返回抑制通道。``pos``/``first_hop`` 就地更新。

        ``trace`` 给定时逐跳追加旧版审计口径的 ``{"step", "phase": "propagate",
        "activated_count", "max_act"}``（重构路径全程留痕，旧 activation.py 的 steps）。
        """
        neg: Dict[str, float] = {}
        for hop in range(1, hops + 1):
            nxt_pos, nxt_neg = dict(pos), dict(neg)
            for s, t, rel in arcs:
                a = pos.get(s, 0.0)
                if a <= 0:
                    continue
                v = a * EDGE_BASE_DECAY.get(rel, DEFAULT_DECAY)
                bucket = nxt_neg if rel in INHIBITORY else nxt_pos
                if v > bucket.get(t, 0.0):
                    bucket[t] = v
            for nid in set(nxt_pos) | set(nxt_neg):
                if nid not in first_hop:
                    first_hop[nid] = hop
            pos.clear()
            pos.update(nxt_pos)
            neg = nxt_neg
            _trace_hop(trace, hop, pos, floor)
        return neg

    @staticmethod
    def _propagate_frontier(pos: Dict[str, float], out: Dict[str, List[Tuple[str, float, bool]]], hops: int,
                            first_hop: Dict[str, int], trace: Optional[List[Dict]] = None,
                            floor: float = 0.0) -> Dict[str, float]:
        """A3 的前沿实现：与 :meth:`_propagate` 逐位相同（同一乘积、同一严格大于比较），只是
        每跳只松弛「上一跳值变化过」的节点的出边（其余节点的贡献已在更早一跳计入，通道单调不降）。"""
        neg: Dict[str, float] = {}
        frontier = [nid for nid, a in pos.items() if a > 0]
        for hop in range(1, hops + 1):
            snap = {nid: pos[nid] for nid in frontier}       # 本跳读上一跳的值（不读本跳新值）
            changed = set()
            for s, a in snap.items():
                for t, d, inhib in out.get(s, ()):
                    v = a * d
                    bucket = neg if inhib else pos
                    if v > bucket.get(t, 0.0):
                        bucket[t] = v
                        if not inhib:
                            changed.add(t)
                        if t not in first_hop:
                            first_hop[t] = hop
            frontier = list(changed)
            _trace_hop(trace, hop, pos, floor)
        return neg

    def _seed_by_text(self, query: str, top_k: int = 12) -> List[Tuple[str, float]]:
        """旧版同名入口：按当前图给查询选种子（空/纯空白查询 0 个种子，#199）。"""
        return self._derived().seeds(query or "", int(top_k))

    @property
    def _adj(self) -> None:
        """旧版 scipy 稀疏邻接缓存；ng 每次激活现读边表（无缓存可过期），恒为 None。"""
        return None

    # ------------------------------------------------------------ 激活
    def activate(self, query: str, conditions: Optional[Dict] = None, workset: str = "default",
                 top_k: int = 12, hops: int = 2, act_floor: float = 0.15,
                 self_condition: float = 0.0, prior_workset: Optional[str] = None) -> Dict:
        """种子 → 扩散 → 工作态落表 + 审计。参数语义与旧版一致。"""
        t0 = now()
        w = unit(self_condition, "self_condition")
        view = self._derived()
        seeds = view.seeds(query or "", int(top_k))
        pos: Dict[str, float] = {nid: s for nid, s in seeds}
        prior = prior_workset or workset
        carried = []
        if w > 0:
            for nid, a in self.carry_vector(prior).items():
                if nid in view.known:
                    carried.append(nid)
                    pos[nid] = max(pos.get(nid, 0.0), float(a) * w)
        first_hop = {nid: 0 for nid in pos}
        steps: List[Dict] = [{"step": 0, "phase": "seed", "activated": [nid for nid, _ in seeds],
                              "scores": {nid: round(s, 4) for nid, s in seeds}}]
        if w > 0:
            steps.append({"step": 0, "phase": "self_condition", "prior_workset": prior,
                          "weight": w, "carried": len(carried)})
        neg = self._propagate_frontier(pos, view.out, int(hops), first_hop, steps, float(act_floor))
        seed_ids = {nid for nid, _ in seeds}
        members, suppressed = self._split(pos, neg, act_floor)
        sources = {nid: ("seed" if nid in seed_ids else "self_condition" if nid in carried
                         else "propagate") for nid, _ in members + suppressed}
        self._write(workset, members, suppressed, sources, first_hop)
        audit = {"algo": ALGO, "ts": now(), "workset": workset, "query": query,
                 "conditions": conditions or {}, "seeds": len(seeds), "steps": steps,
                 "self_condition": {"weight": w, "prior_workset": prior if w > 0 else None,
                                    "carried": len(carried)},
                 "workset_size": len(members), "suppressed": [m[0] for m in suppressed[:10]],
                 "top": [m[0] for m in members[:10]], "latency_ms": round((now() - t0) * 1000, 1)}
        self._audit(audit)
        return {"status": "ok", "workset": workset, "size": len(members), "top": members[:10],
                "seeds": len(seeds), "hops": hops, "carried": len(carried),
                "suppressed": suppressed[:10], "latency_ms": audit["latency_ms"]}

    @staticmethod
    def _split(pos: Dict[str, float], neg: Dict[str, float], floor: float):
        """内部辅助函数。"""
        members, suppressed = [], []
        for nid in set(pos) | set(neg):
            net = pos.get(nid, 0.0) - neg.get(nid, 0.0)
            if net >= floor:
                members.append((nid, round(net, 4)))
            elif neg.get(nid, 0.0) >= floor and neg.get(nid, 0.0) > pos.get(nid, 0.0):
                suppressed.append((nid, round(neg[nid], 4)))
        members.sort(key=lambda x: (-x[1], x[0]))
        suppressed.sort(key=lambda x: (-x[1], x[0]))
        return members, suppressed

    def _write(self, workset: str, members, suppressed, sources: Dict[str, str],
               hops: Dict[str, int]) -> None:
        """内部辅助函数。"""
        t = now()
        rows = [(f"act_{uuid.uuid4().hex[:12]}", workset, nid, a, sources[nid], hops.get(nid, 0), t, pol)
                for pol, group in ((1, members), (-1, suppressed)) for nid, a in group]
        with self.port.tx() as c:
            view = getattr(self, "_view", None)
            before = (int(c.execute("PRAGMA data_version").fetchone()[0]), int(c.total_changes))
            c.execute("DELETE FROM activation_nodes WHERE workset=?", (workset,))
            c.executemany("INSERT INTO activation_nodes (id, workset, node_id, activation, source, hop, "
                          "ts, polarity) VALUES (?,?,?,?,?,?,?,?)", rows)
            if view is not None and view.fp == before:      # A2：自己的工作态写入不改图，顺延指纹
                view.fp = (before[0], int(c.total_changes))

    def _audit(self, audit: Dict) -> None:
        """内部辅助函数。"""
        os.makedirs(os.path.dirname(os.path.abspath(self.audit_path)), exist_ok=True)
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------ 工作态读写
    def carry_vector(self, workset: str = "default") -> Dict[str, float]:
        """上一步工作态中**兴奋**成员的 node_id → 激活值（抑制成员不回注，A3）。"""
        rows = self.port.all("SELECT node_id, activation FROM activation_nodes WHERE workset=? "
                             "AND COALESCE(polarity,1) > 0", (workset,))
        return {r[0]: float(r[1]) for r in rows}

    def workset_state(self, workset: str = "default", limit: int = 20) -> Dict:
        """当前工作态（含内容摘要与极性）。"""
        rows = self.port.all(
            "SELECT a.node_id, a.activation, COALESCE(a.polarity,1), n.content, n.layer, n.importance "
            "FROM activation_nodes a LEFT JOIN nodes n ON n.id=a.node_id WHERE a.workset=? "
            "ORDER BY COALESCE(a.polarity,1) DESC, a.activation DESC LIMIT ?", (workset, limit))
        members = [{"node_id": r[0], "activation": r[1], "polarity": r[2],
                    "content": (r[3] or "")[:80], "layer": r[4], "importance": r[5]} for r in rows]
        return {"workset": workset, "size": len(members), "members": members}

    def export_workset(self, workset: str) -> Dict:
        """可序列化快照（含 source / hop / polarity）。"""
        rows = self.port.all("SELECT node_id, activation, source, hop, ts, COALESCE(polarity,1) "
                             "FROM activation_nodes WHERE workset=? ORDER BY rowid", (workset,))
        return {"algo": ALGO, "workset": workset, "ts": now(),
                "members": [{"node_id": r[0], "activation": r[1], "source": r[2], "hop": r[3],
                             "ts": r[4], "polarity": r[5]} for r in rows]}

    def import_workset(self, snapshot: Dict, workset: Optional[str] = None) -> Dict:
        """恢复快照（source 记为 restored，保留 hop 与极性）。"""
        ws = workset or snapshot["workset"]
        t = now()
        rows = [(f"act_{uuid.uuid4().hex[:12]}", ws, m["node_id"], unit(m["activation"], "activation"),
                 "restored", int(m.get("hop", 0)), t, int(m.get("polarity", 1)))
                for m in snapshot.get("members", [])]
        with self.port.tx() as c:
            c.execute("DELETE FROM activation_nodes WHERE workset=?", (ws,))
            c.executemany("INSERT INTO activation_nodes (id, workset, node_id, activation, source, hop, "
                          "ts, polarity) VALUES (?,?,?,?,?,?,?,?)", rows)
        return {"status": "ok", "workset": ws, "restored": len(rows)}


def _trace_hop(trace: Optional[List[Dict]], hop: int, pos: Dict[str, float], floor: float) -> None:
    """旧版审计口径的逐跳留痕：{"step", "phase": "propagate", "activated_count", "max_act"}。"""
    if trace is not None:
        trace.append({"step": hop, "phase": "propagate",
                      "activated_count": sum(1 for v in pos.values() if v >= floor),
                      "max_act": round(max(pos.values(), default=0.0), 4)})


def _sort_rows(rows: List[tuple], old_known: Dict[str, int], old_hay: Dict[str, str],
               known: Dict[str, int], seed: Dict[str, str], todo: List[Tuple[str, str]]) -> None:
    """一批 (id, content, tags, 可做种子) 行：记原文签名；可做种子且原文未变的沿用旧文本，否则排入待规范化。"""
    for nid, content, tags, ok in rows:
        sig = known[nid] = hash((content, tags, bool(ok)))
        if not ok:
            continue                                                   # A5：不可做种子，不留文本
        if old_known.get(nid) == sig and nid in old_hay:
            seed[nid] = old_hay[nid]
        else:
            todo.append((nid, (content or "") + " " + _tag_text(tags)))


def _kth_count(hits: Counter, top_k: int) -> int:
    """第 top_k 名的命中数（不足 top_k 个则为最低命中数）：按命中数直方图从高往低累计。"""
    need = top_k
    for c, k in sorted(Counter(hits.values()).items(), reverse=True):
        need -= k
        if need <= 0:
            return c
    return min(hits.values())


def _tag_text(tags: Any) -> str:
    """tags 列（JSON 数组）→ 空格连接的文本；坏 JSON 视为无标签（与旧读图口径一致）。"""
    if not tags or tags == "[]":
        return ""
    try:
        return " ".join(json.loads(tags))
    except ValueError:
        return ""


class _GraphView:
    """某一提交指纹下的派生图（A2）：节点签名表、可做种子节点的有序 (id, 规范化文本) 表、出边邻接。只读快照。

    常驻只留激活要用的：``known``（节点 → 原文签名，判存在 + 增量重读）、``ids``/``hays``（A5 可做种子的节点按
    id 排序）、``out``（src → [(dst, 衰减系数, 是否抑制)]）与边表签名。不留原文、不留边表副本。"""
    __slots__ = ("fp", "known", "ids", "hays", "out", "arcs_sig")

    #: 流式读节点 / 批量规范化的批大小（限制重读时的瞬时 Python 堆）
    CHUNK = 4096

    @classmethod
    def build(cls, fp: Tuple[int, int], texts: Dict[str, Tuple[str, bool]],
              arcs: Sequence[Tuple[str, str, str]]) -> "_GraphView":
        """由参考口径的 (texts, arcs) 直接构造（测试用）。"""
        v = cls.__new__(cls)
        v.fp = fp
        v.known = {nid: None for nid in texts}
        v.ids = sorted(nid for nid, (_, ok) in texts.items() if ok)
        v.hays = [texts[nid][0] for nid in v.ids]
        v.out, v.arcs_sig = cls._out(arcs), None
        return v

    @staticmethod
    def _out(arcs: Sequence[Tuple[str, str, str]]) -> Dict[str, List[Tuple[str, float, bool]]]:
        """出边邻接：src → [(dst, 衰减系数, 是否抑制)]（插入序）。"""
        out: Dict[str, List[Tuple[str, float, bool]]] = {}
        for s, t, rel in arcs:
            out.setdefault(s, []).append((t, EDGE_BASE_DECAY.get(rel, DEFAULT_DECAY), rel in INHIBITORY))
        return out

    @classmethod
    def load(cls, port: Any, fp: Tuple[int, int], prev: Optional["_GraphView"] = None) -> "_GraphView":
        """从库读出（锁内流式读节点、再读边）。

        ``prev`` 为上一份派生图：原文签名 hash((content, tags, 可做种子)) 未变的节点沿用其规范化文本；
        边表签名相同则沿用邻接——增量重建，结果与从零读出相同。"""
        with port.lock:
            cur = port.conn.cursor()
            cur.row_factory = None
            known, seed, fresh = cls._scan_nodes(cur, prev)
            arcs = cur.execute("SELECT source_id, target_id, relation_type FROM edges ORDER BY rowid").fetchall()
        v = cls.__new__(cls)
        v.fp, v.known, v.arcs_sig = fp, known, hash(tuple(arcs))
        v.out = prev.out if prev is not None and prev.arcs_sig == v.arcs_sig else cls._out(arcs)
        if prev is not None and not fresh and seed.keys() == set(prev.ids):
            v.ids, v.hays = prev.ids, prev.hays                      # 可做种子的文本表原样沿用
        else:
            v.ids = sorted(seed)
            v.hays = [seed[nid] for nid in v.ids]
        return v

    @classmethod
    def _scan_nodes(cls, cur: Any, prev: Optional["_GraphView"]) -> Tuple[Dict[str, int], Dict[str, str], int]:
        """流式扫节点表：(节点→原文签名, 可做种子节点→规范化文本, 本次新算文本的节点数)。"""
        cond, params = LayerPolicy.layers_where("layer", searchable=True)
        old_known = prev.known if prev is not None else {}
        old_hay = dict(zip(prev.ids, prev.hays)) if prev is not None else {}
        known: Dict[str, int] = {}
        seed: Dict[str, str] = {}
        todo: List[Tuple[str, str]] = []
        fresh = 0
        cur.execute(f"SELECT id, content, tags, ({cond}) FROM nodes", params)
        for rows in iter(lambda: cur.fetchmany(cls.CHUNK), []):
            _sort_rows(rows, old_known, old_hay, known, seed, todo)
            if len(todo) >= cls.CHUNK:
                fresh += cls._drain(todo, seed)
        return known, seed, fresh + cls._drain(todo, seed)

    @staticmethod
    def _drain(todo: List[Tuple[str, str]], seed: Dict[str, str]) -> int:
        """把待规范化的节点批量算完、并入 seed；返回本批条数。"""
        n = len(todo)
        for (nid, _), hay in zip(todo, normalize_many([x[1] for x in todo])):
            seed[nid] = hay
        todo.clear()
        return n

    def seeds(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """与 :meth:`ActivationEngine._seeds` 逐项相同：得分 = 命中 token 占比（round 6 位），
        按 (-得分, id) 取前 top_k。按 token 逐个在有序文本表上做 C 层子串扫描后计数。"""
        q = normalize(query)
        if not q:
            return []                                                  # A1
        toks = {q[i:i + 2] for i in range(len(q) - 1)} | {q}
        hays, n = self.hays, len(self.hays)
        if n == 0 or top_k <= 0:
            return []
        if len(toks) > 100_000:          # 超长查询：round(·, 6) 可能并列相邻命中数，退回参考实现
            return ActivationEngine._seeds(query, {nid: (h, True) for nid, h in zip(self.ids, hays)}, top_k)
        hits: Counter = Counter()
        for t in toks:
            hits.update(compress(range(n), map(str.__contains__, hays, repeat(t))))
        if not hits:
            return []
        thr, m = _kth_count(hits, top_k), len(toks)      # 只对不低于阈值的候选精确排序（id 表有序 ⇒ 下标序即 id 序）
        cand = sorted(((-round(c / m, 6), i) for i, c in hits.items() if c >= thr))
        return [(self.ids[i], -negs) for negs, i in cand[:top_k]]
