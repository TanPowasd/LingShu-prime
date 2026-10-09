"""evalsuite 适配层：把「行为探针 / 性质测试 / 性能」与具体实现的 API 隔开。

探针只调用本文件定义的抽象操作（Mem 的方法），不直接碰任何实现的类/表/SQL。
两种实现：
  impl="legacy" → lingshu.core.core（上游 2bb8291 与各修复线，旧 API）
  impl="ng"     → lingshu_ng.compat（新实现的兼容门面，同样按旧 API 调用）

缺能力的处理（不偏袒任何一方）：
  - 模块导入失败 / 门面缺属性 / NotImplementedError  → 抛 NA（读数记 N/A，不计分）
  - 操作本身抛出的其他异常照常上抛，由探针决定这是 BUG 还是 ERR。

归一化节点：dict(id, content, layer, importance, confidence, tags, access_count, modality)
"""
from __future__ import annotations

import importlib
import json
import math
import os
import tempfile
import time


class NA(BaseException):
    """该实现不具备此能力（导入失败 / 未实现）。

    刻意继承 BaseException：探针里「except Exception: 吞掉」的分支不会把『未实现』误判成『安全地拒绝了』，
    NA 一定冒泡到 runner，记为 NA（计 0 分），杜绝靠不实现拿 OK。"""


IMPLS = ("legacy", "ng")


def _need(obj, name):
    try:
        return getattr(obj, name)
    except AttributeError:
        raise NA(f"missing:{type(obj).__name__}.{name}")


def _call(obj, name, *a, **k):
    fn = _need(obj, name)
    try:
        return fn(*a, **k)
    except NotImplementedError as ex:
        raise NA(f"notimpl:{name}:{ex}")


def _layer_str(layer):
    return getattr(layer, "value", layer)


def norm_node(n):
    if n is None:
        return None
    if isinstance(n, dict):
        d = dict(n)
        d["layer"] = _layer_str(d.get("layer"))
        return d
    tags = getattr(n, "tags", []) or []
    return {"id": n.id, "content": n.content, "layer": _layer_str(n.layer),
            "importance": n.importance, "confidence": n.confidence,
            "tags": list(tags), "access_count": getattr(n, "access_count", 0),
            "modality": getattr(n, "modality", "text"),
            "temporal": getattr(n, "temporal_coordinate", None)}


def _nid(x):
    if x is None:
        return None
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("id") or x.get("node_id")
    return getattr(x, "id", None) or getattr(x, "node_id", None)


class Adapter:
    """工厂：A.open(...) → Mem。"""

    def __init__(self, impl: str):
        if impl not in IMPLS:
            raise ValueError(impl)
        self.impl = impl
        try:
            if impl == "legacy":
                self.mod = importlib.import_module("lingshu.core.core")
            else:
                self.mod = importlib.import_module("lingshu_ng.compat")
        except Exception as ex:  # 包不存在 / 尚未写完
            raise NA(f"import:{type(ex).__name__}:{ex}")
        self.Engine = _need(self.mod, "SpacetimeMemoryEngine")
        self.Layer = _need(self.mod, "MemoryLayer")
        self._tmp = tempfile.mkdtemp(prefix="evs_")

    # ---- 枚举映射 ----
    def layer(self, s):
        return self.Layer(s)

    def role(self, s):
        Role = _need(self.mod, "Role")
        return Role(s)

    def edge_type(self, s):
        ET = _need(self.mod, "EdgeType")
        return ET(s)

    def tmpdb(self, name=None):
        """每次调用都给出一个新的库文件路径（同名前缀也不复用）。"""
        self._n = getattr(self, "_n", 0) + 1
        return os.path.join(self._tmp, f"{name or 'm'}_{self._n}_{time.time_ns()}.db")

    def tmpfile(self, name):
        return os.path.join(self._tmp, name)

    def set_designer_key(self, key):
        os.environ["AEIS_DESIGNER_KEY"] = key

    def open(self, db=None, role="primary", identity=None) -> "Mem":
        db = db or ":memory:"
        kw = {}
        if role != "primary":
            kw["role"] = self.role(role)
        if identity is not None:
            kw["identity"] = identity
        try:
            e = self.Engine(db, **kw)
        except NotImplementedError as ex:
            raise NA(f"notimpl:engine:{ex}")
        return Mem(self, e, db)

    # ---- 激活引擎（独立组件） ----
    def activation_engine(self, db, audit=None):
        if self.impl == "legacy":
            try:
                act = importlib.import_module("lingshu.core.activation")
            except ImportError as ex:
                raise NA(f"import:activation:{ex}")
        else:
            act = None
            for c in ("lingshu_ng.compat_activation", "lingshu_ng.activation"):
                try:
                    act = importlib.import_module(c)
                    break
                except ImportError:
                    continue
            if act is None:
                raise NA("import:ng activation")
        AE = _need(act, "ActivationEngine")
        return AE(db, audit or self.tmpfile(f"audit{time.time_ns()}.jsonl"))

    def self_model_cls(self):
        return _need(self.mod, "SelfModel")


class Mem:
    """一个记忆引擎实例上的抽象操作。"""

    def __init__(self, A: Adapter, e, db):
        self.A, self.e, self.db = A, e, db

    @property
    def store(self):
        return _need(self.e, "store")

    # ================= 写入 =================
    def add(self, content, layer="knowledge", importance=None, tags=None, entities=None,
            modality="text", skip_dedup=False):
        """返回节点 id。layer ∈ knowledge/context/anchor/structure。"""
        kw = {}
        if importance is not None:
            kw["importance"] = importance
        if layer == "knowledge":
            if tags is not None:
                kw["tags"] = tags
            if entities is not None:
                kw["entities"] = entities
            if modality != "text":
                kw["modality"] = modality
            if skip_dedup:
                kw["skip_dedup"] = True
            return _nid(_call(self.e, "add_perception", content, **kw))
        if layer == "context":
            if tags is not None:
                kw["tags"] = tags
            return _nid(_call(self.e, "add_context", content, **kw))
        if layer == "anchor":
            return _nid(_call(self.e, "set_anchor", content, **kw))
        if layer == "structure":
            return _nid(_call(self.e, "add_structure_node", content, **kw))
        raise ValueError(layer)

    def add_ret(self, content, **kw):
        """add_perception 原始返回（用于判定合并/新建的可区分性）。"""
        return _call(self.e, "add_perception", content, **kw)

    def ingest_frame(self, frame):
        return _nid(_call(self.e, "ingest_frame", frame))

    def external_anchor(self, kind, content):
        return _nid(_call(self.e, "register_external_anchor", kind, content))

    def put_raw_node(self, node_id, content, layer, importance=0.5):
        """以同 id 写一整行（store.add_node 语义：INSERT OR REPLACE）。"""
        import dataclasses
        old = _call(self.store, "get_node", node_id)
        if old is None:
            raise ValueError("no such node")
        new = dataclasses.replace(old, content=content, layer=self.A.layer(layer),
                                  importance=importance)
        return _call(self.store, "add_node", new)

    def tag(self, nid, tag):
        return _call(self.store, "tag_node", nid, tag)

    def protect(self, nid, reason="probe"):
        return _call(self.e, "protect_node", nid, reason)

    def protected(self):
        return list(_call(self.e, "get_protected_nodes"))

    def delete(self, nid):
        return _call(self.store, "delete_node", nid)

    def set_importance_delta(self, nid, d):
        return _call(self.store, "update_node_importance", nid, d)

    def set_confidence_delta(self, nid, d):
        return _call(self.store, "update_node_confidence", nid, d)

    def set_context_cap(self, n):
        return _call(self.e, "set_context_cap", n)

    def set_dedup(self, threshold):
        return _call(self.e, "set_dedup_config", threshold)

    def verifier_config(self):
        return dict(_call(self.e, "get_verifier_config"))

    # ================= 读取 =================
    def get(self, nid):
        return norm_node(_call(self.store, "get_node", nid))

    def layer_nodes(self, layer):
        return [norm_node(n) for n in _call(self.store, "get_layer_nodes", self.A.layer(layer))]

    def anchors(self):
        return [norm_node(n) for n in _call(self.e, "get_anchors")]

    def count(self, layer):
        return _call(self.store, "count_layer", self.A.layer(layer))

    def all_nodes(self, limit=100000):
        return [norm_node(n) for n in _call(self.store, "query_nodes", limit=limit)]

    def by_tag(self, tag):
        return [norm_node(n) for n in _call(self.store, "get_nodes_by_tag", tag)]

    def search(self, q, limit=10):
        return [(norm_node(n), s) for n, s in _call(self.e, "search_content", q, limit=limit)]

    def recall(self, q, limit=10):
        return [(norm_node(n), s) for n, s in _call(self.e, "recall", q, limit=limit)]

    def what_happened_at(self, ts, tol=60.0):
        r = _call(self.e, "what_happened_at", ts, tol)
        out = []
        for x in r:
            if isinstance(x, dict):
                out.append(x.get("id") or x.get("node_id"))
            elif isinstance(x, (tuple, list)):
                out.append(_nid(x[0]))
            else:
                out.append(_nid(x))
        return out

    def timeline(self, start, end):
        return [_nid(x) for x in _call(self.e, "get_timeline", start, end)]

    def spatiotemporal(self, nid, time_radius):
        return [(_nid(n), d) for n, d in _call(self.e, "spatiotemporal_query", nid, time_radius=time_radius)]

    # ================= 维护 =================
    def decay(self, n=1, factor=0.02):
        for _ in range(n):
            _call(self.e, "decay_cycle", factor)

    def store_decay(self, n=1, factor=0.02, min_conf=0.1):
        for _ in range(n):
            _call(self.store, "decay_cycle", factor=factor, min_confidence=min_conf)

    def maintenance(self):
        return _call(self.e, "run_maintenance_cycle")

    def consolidate(self):
        return _call(self.e, "consolidate_cycle")

    def forget_advisor(self):
        return _call(self.e, "forget_advisor")

    def induce(self):
        return _call(self.e, "induce_concepts")

    def start_auto_decay(self, interval):
        return _call(self.e, "start_auto_decay", interval)

    def close(self):
        return _call(self.e, "close")

    def reopen(self, role="primary"):
        try:
            self.close()
        except Exception:
            pass
        return self.A.open(self.db, role=role)

    # ================= 图 / 因果 =================
    def add_edge(self, a, b, rel="causal", conf=0.5):
        r = _call(self.e, "add_edge", a, b, relation_type=self.A.edge_type(rel), confidence=conf)
        return _nid(r)

    def get_edge(self, eid):
        ed = _call(self.store, "get_edge", eid)
        if ed is None:
            return None
        return {"id": ed.id, "src": ed.source_id, "dst": ed.target_id,
                "rel": _layer_str(ed.relation_type), "confidence": ed.confidence,
                "verified": bool(ed.verified)}

    def edges_of(self, nid):
        out = _call(self.store, "get_outgoing_edges", nid) + _call(self.store, "get_incoming_edges", nid)
        return [{"id": x.id, "src": x.source_id, "dst": x.target_id,
                 "rel": _layer_str(x.relation_type), "confidence": x.confidence} for x in out]

    def verify_edge(self, eid, conf=None):
        return _call(self.e, "verify_edge", eid, conf)

    def replace_edge(self, eid, src, dst, rel="opposite"):
        """以同 id 覆盖一条边（store.add_edge 的 INSERT OR REPLACE 语义）。"""
        import dataclasses
        old = _call(self.store, "get_edge", eid)
        new = dataclasses.replace(old, source_id=src, target_id=dst,
                                  relation_type=self.A.edge_type(rel), verified=False)
        return _call(self.store, "add_edge", new)

    def cycles(self, max_depth=10):
        return [[(x.source_id, x.target_id) for x in c] for c in _call(self.store, "find_cycles", max_depth=max_depth)]

    def has_cycle(self):
        return bool(_call(self.store, "has_causal_cycle"))

    def reason(self, start, end=None, max_depth=5):
        return _call(self.e, "reason_causal", start, end, max_depth=max_depth)

    def conflict(self, a, b):
        return _call(self.e, "register_conflict", a, b)

    def subgraph_replace(self, parent, old_root, new_subtree):
        return _call(self.e, "subgraph_replace", parent, old_root, new_subtree)

    # ================= 自检 / 导出导入 =================
    def self_check(self):
        return dict(_call(self.e, "self_check"))

    def integrity(self):
        return dict(_call(self.e, "verify_integrity"))

    def export(self, path):
        return _call(self.e, "export_all", path)

    def import_(self, path):
        return _call(self.e, "import_all", path)

    def shared_sync(self):
        return _call(self.e, "prepare_shared_sync")

    # ================= 自我层 =================
    def update_self(self, updates, link=None):
        if link is None:
            return _call(self.e, "update_self", updates)
        return _call(self.e, "update_self", updates, link_to_node_id=link)

    def update_trust(self, t_total, rnd):
        return _call(self.e, "update_trust_state", t_total, rnd)

    def self_state(self):
        sm = _call(self.e, "get_self_model")
        return {"identity": getattr(sm, "identity", None), "values": list(getattr(sm, "values", []) or []),
                "history_len": len(getattr(sm, "history", []) or []),
                "value_evolution_len": len(getattr(sm, "value_evolution", []) or []),
                "t_total": (getattr(sm, "trust_state", {}) or {}).get("t_total"),
                "extra": {k: v for k, v in vars(sm).items() if not k.startswith("_")} if hasattr(sm, "__dict__") else {}}

    def record_value_change(self, value, trigger, replaces=None):
        sm = _call(self.e, "get_self_model")
        fn = _need(sm, "record_value_change")
        if replaces is None:
            return fn(value, trigger)
        try:
            return fn(value, trigger, replaces=replaces)
        except TypeError:
            return fn(value, trigger)

    # ================= 技能 / 负记忆 =================
    def store_skill(self, name, desc, proc, conf=0.5):
        return _call(self.e, "store_skill", name, desc, proc, conf)

    def record_skill(self, actions, outcome, success, hint=None):
        return _nid(_call(self.e, "record_action_sequence", actions, outcome, success, skill_hint=hint))

    def skills(self, q="", limit=100):
        return list(_call(self.e, "recall_skill", q, limit))

    def rejected(self):
        return list(_call(self.e, "list_rejected_paths"))

    # ================= 门控（长期记忆） =================
    def gate_write(self, content, hint=None, tags=None, source="snapshot"):
        kw = {"source": source}
        if hint is not None:
            kw["importance_hint"] = hint
        if tags is not None:
            kw["tags"] = tags
        return dict(_call(self.e, "longterm_snapshot", content, **kw))

    def prefeed(self, content):
        return dict(_call(self.e, "prefeed_input", content))

    def novelty(self, content):
        g = _call(self.e, "_ensure_gate")
        return float(_call(g, "_novelty", content))

    # ================= 治理（晋升 / 盲区 / 验证标准 / 升级点） =================
    def propose(self, nid, who="requester", reason="r"):
        return _call(self.e, "propose_promotion", nid, who, reason)

    def verify_proposal(self, pid, who="verifier"):
        return _call(self.e, "verify_promotion", pid, who)

    def adjudicate(self, pid, who="adjudicator", approved=True, key=None):
        return _call(self.e, "adjudicate_promotion", pid, who, approved, designer_key=key)

    def blindspot(self, code, desc):
        return _call(self.e, "register_blindspot", code, desc)

    def open_blindspots(self):
        return list(_call(self.e, "get_open_blindspots"))

    def store_resolve_blindspot(self, bid):
        """绕过门面直接在存储层关闭盲区（检测「密钥只在门面」）。"""
        return _call(self.store, "resolve_blindspot", bid)

    def propose_standard(self, name, param, value, reason, who):
        return _call(self.e, "propose_verifier_standard", name, param, value, reason, who)

    def review_standard(self, vid, who, ok=True):
        return _call(self.e, "review_verifier_standard", vid, who, ok)

    def cs_review_standard(self, vid, who, ok=True):
        return _call(self.e, "cs_review_verifier_standard", vid, who, ok)

    def adjudicate_standard(self, vid, who, ok=True, key=None):
        return _call(self.e, "adjudicate_verifier_standard", vid, who, ok, designer_key=key)

    def escalations(self, enabled_only=True):
        return list(_call(self.e, "list_escalation_points", enabled_only))

    def add_escalation(self, code, trigger, cond, action="提交维生系统", sev="high"):
        return _call(self.store, "add_escalation_point", code, trigger, cond, action, sev)

    def check_escalation(self, sig, value=None):
        return list(_call(self.e, "check_escalation", sig, value))

    def spy_escalation(self):
        """包一层计数器：返回列表，每次引擎内部调用 check_escalation 追加一条。"""
        calls = []
        orig = _need(self.e, "check_escalation")
        self.e.check_escalation = lambda *a, **k: (calls.append(a), orig(*a, **k))[1]
        return calls

    def insight(self, content):
        return dict(_call(self.store, "insight_record", content, conditions={}))

    def insight_verify(self, nid, level="V2", evidence=None):
        kw = {"level": level}
        if evidence is not None:
            kw["evidence"] = evidence
        return dict(_call(self.store, "insight_verify", nid, **kw))

    def reflect(self, claim):
        return dict(_call(self.e, "recursive_reflect", claim))

    # ================= 事件 =================
    def notify(self, t, payload=None):
        return _call(self.e, "notify_event", t, payload or {})

    def consume(self):
        return dict(_call(self.e, "consume_events"))

    def pending_events(self):
        return len(_need(self.e, "_event_queue"))

    def force_paused(self):
        class _P:
            state = "paused"
        self.e._lifecycle = _P()

    def unpause(self):
        self.e._lifecycle = None

    # ================= 激活 =================
    def activate(self, query, hops=2, workset="default", self_condition=0.0):
        if self.db == ":memory:":
            raise ValueError("activation 需要文件库")
        if not hasattr(self, "_act"):
            self._act = self.A.activation_engine(self.db)
        r = _call(self._act, "activate", query, workset=workset, hops=hops, self_condition=self_condition)
        return r

    def workset(self, workset="default", limit=50):
        st = _call(self._act, "workset_state", workset, limit)
        return [(m.get("node_id"), m.get("activation")) for m in st.get("top", st.get("members", []))]


    # ================= 其它（时间坐标 / 子模块 / 门面） =================
    def add_at(self, content, ts, layer="knowledge", importance=0.5, nid=None):
        """写一个指定时间坐标的节点（store.add_node + 模块的 STNode/ConditionSpace）。"""
        STNode = _need(self.A.mod, "STNode")
        CS = _need(self.A.mod, "ConditionSpace")
        nid = nid or f"at_{time.time_ns()}"
        n = STNode(id=nid, content=content, modality="text", spatial_coordinates={"x": 0.0},
                   temporal_coordinate=ts, condition_space=CS("测试台", "evalsuite", (ts, ts + 1), "合成"),
                   importance=importance, layer=self.A.layer(layer), last_access=ts, created_at=ts)
        _call(self.store, "add_node", n)
        return nid

    def set_escalation(self, eid, enabled):
        return _call(self.e, "set_escalation_enabled", eid, enabled)

    def facade(self, name, action, params=None):
        return dict(_call(self.e, name, action, params or {}))


def submodule(A, name):
    """实现的子模块：legacy → lingshu.core.<name>；ng → lingshu_ng.compat.<name> 或 lingshu_ng.<name>。"""
    alias = {"time_core": "timecore"}.get(name, name)
    cands = [f"lingshu.core.{name}"] if A.impl == "legacy" else [
        f"lingshu_ng.compat_{name}", f"lingshu_ng.compat_{alias}", f"lingshu_ng.{name}", f"lingshu_ng.{alias}"]
    for c in cands:
        try:
            return importlib.import_module(c)
        except ImportError:
            continue
    if A.impl == "ng" and hasattr(A.mod, name):
        return getattr(A.mod, name)
    raise NA(f"import:{name}")


def finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)
