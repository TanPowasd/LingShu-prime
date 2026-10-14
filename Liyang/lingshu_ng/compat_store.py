# -*- coding: utf-8 -*-
"""compat_store · 旧 ``LayeredStore`` 的兼容门面（自 compat 拆出，stab-r1）

拆分原因：compat 定义 LayeredStore 并再导出 SpacetimeMemoryEngine，而 compat_engine 构造时又要回头导入
compat.LayeredStore，形成 compat ↔ compat_engine 直接双向依赖。现在 LayeredStore 住在本模块，
compat 与 compat_engine 都单向依赖本模块；``lingshu_ng.compat.LayeredStore`` 仍是同一个类对象，行为逐字节不变。
规则与「有意不同」之处见 :mod:`lingshu_ng.compat` 的说明。
"""
from __future__ import annotations

import itertools
import logging
from typing import Dict, List, Optional, Sequence, Tuple

from . import causal, graphquery
from .decay import Maintenance
from .dedup import bigrams, jaccard
from .governance import designer_key_configured, verify_designer
from .insight import Insights
from .layers import LayerPolicy, LayerViolation
from .negative import NegativeMemory
from .retrieval import SYNONYM_GROUPS, Retriever, expand_terms
from .self_model import SelfModel
from .skills import SkillBook
from .store import Store, schema
from .timecore import cred_step
from .types import (CausalChain, ConditionSpace, Edge, EdgeType, MemoryLayer, Node, NodeType, Role,
                    now)
from .decay import elapsed_factor
from .numeric import require_finite
from .promotion import adjudicate
from .store.nodes import _SELECT as NODE_SELECT

__all__ = ["LayeredStore", "CAUSAL_MAX_PATHS"]

_log = logging.getLogger(__name__)

#: 上游 ``_CAUSAL_MAX_PATHS``（#327）：因果路径枚举的缺省上限
from ._consts import CAUSAL_MAX_PATHS  # noqa: E402  = 1000，值定义在 _consts（同一对象）
#: 上游 ``_DECAY_PERIOD_SECONDS`` / ``_LAST_DECAY_META_KEY``（#176）：时间模式衰减的周期与「上次衰减时刻」键
DECAY_PERIOD_SECONDS = 60.0
LAST_DECAY_META_KEY = "_last_decay_at"


def _pos_int(v: object, name: str) -> int:
    """正整数形参校验（bool / 非整数 / ≤0 → ValueError）。"""
    if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
        raise ValueError(f"{name} 须为正整数，收到 {v!r}")
    return v


class LayeredStore:
    """旧 LayeredStore 的形状；内部是一个 ng :class:`Store`。"""

    IMMUTABLE_LAYERS = {m for m in MemoryLayer if not LayerPolicy.rule(m).deletable}

    @staticmethod
    def _decay_excluded_layer_values() -> Tuple[str, ...]:
        """边衰减排除的层（由层规则表 edge_decays=False 导出；与 IMMUTABLE_LAYERS 同集，上游 #205）。"""
        return tuple(m.value for m in LayerPolicy.layers(edge_decays=False))
    SCHEMA_VERSION = schema.SCHEMA_VERSION
    SYNONYM_GROUPS = [set(g) for g in SYNONYM_GROUPS]

    def __init__(self, db_path: str = ":memory:", role: Role = Role.PRIMARY,
                 _ng_store: Optional[Store] = None) -> None:
        """旧 API ``__init__``：形状适配，规则委托 ng 组件。"""
        self.ng = _ng_store or Store(db_path, role)
        self.db_path, self.role = db_path, self.ng.role
        self.db = self.ng.db
        self.conn = self.ng.db.conn
        self._lock = self.ng.db.lock
        self._retriever = Retriever(self.ng)
        self._mnt = Maintenance(self.ng)
        self._skills = SkillBook(self.ng)
        self._ins = Insights(self.ng)
        self._neg = NegativeMemory(self.ng)

    # ------------------------------------------------------------ 节点
    def add_node(self, node: Node) -> str:
        """旧 API ``add_node``：形状适配，规则委托 ng 组件。"""
        return self.ng.nodes.put(node)

    def get_meta(self, key: Optional[str] = None) -> dict:
        """旧 API ``get_meta``：形状适配，规则委托 ng 组件。"""
        return self.ng.meta.get(key)

    def set_meta(self, key: str, value: str) -> None:
        """旧 API ``set_meta``：形状适配，规则委托 ng 组件。"""
        self.ng.meta.set(key, value)

    def get_node(self, node_id: str) -> Optional[Node]:
        """旧 API ``get_node``：形状适配，规则委托 ng 组件。"""
        return self.ng.nodes.get(node_id)

    def delete_node(self, node_id: str) -> bool:
        """旧 API ``delete_node``：形状适配，规则委托 ng 组件。"""
        layer = self.ng.nodes.layer_of(node_id)
        if layer is None or not LayerPolicy.rule(layer).deletable:
            return False
        try:                                   # #244：SUB 级联删不得带走触及共享层的边
            self.ng.policy.check_node_cascade(self.ng.edges, self.ng.nodes, node_id)
        except LayerViolation:
            return False
        return self.ng.nodes.delete(node_id)

    def update_node_confidence(self, node_id: str, delta: float) -> None:
        """旧 API ``update_node_confidence``：形状适配，规则委托 ng 组件。"""
        n = self.ng.nodes.get(node_id)
        if n is not None:
            self.ng.nodes.update(node_id, confidence=(n.confidence or 0.0) + delta, last_access=now())

    def update_node_importance(self, node_id: str, delta: float) -> None:
        """旧 API ``update_node_importance``：形状适配，规则委托 ng 组件。"""
        n = self.ng.nodes.get(node_id)
        if n is not None:
            self.ng.nodes.update(node_id, importance=(n.importance or 0.0) + delta)

    def increment_access(self, node_id: str) -> None:
        """旧 API ``increment_access``：形状适配，规则委托 ng 组件。"""
        self.ng.nodes.touch([node_id])

    def tag_node(self, node_id: str, tag: str) -> None:
        """旧 API ``tag_node``：形状适配，规则委托 ng 组件。"""
        self.ng.nodes.add_tags(node_id, [tag])

    def query_nodes(self, layer: Optional[MemoryLayer] = None, modality: Optional[str] = None,
                    min_importance: float = 0.0, limit: int = 50) -> List[Node]:
        """旧 API ``query_nodes``：形状适配，规则委托 ng 组件。"""
        return self.ng.nodes.query(layer, modality, min_importance, limit)

    def get_layer_nodes(self, layer: MemoryLayer) -> List[Node]:
        """旧 API ``get_layer_nodes``：形状适配，规则委托 ng 组件。"""
        return self.ng.nodes.query(layer=layer, limit=None)

    def count_layer(self, layer: MemoryLayer) -> int:
        """旧 API ``count_layer``：形状适配，规则委托 ng 组件。"""
        return self.ng.nodes.count(layer)

    def get_nodes_by_tag(self, tag: str, limit: int = 50) -> List[Node]:
        """旧 API ``get_nodes_by_tag``：形状适配，规则委托 ng 组件。"""
        return self.ng.nodes.by_tag(tag, limit)

    def get_nodes_in_range(self, start_ts: float, end_ts: float, layer: Optional[MemoryLayer] = None,
                           limit: int = 50) -> List[Node]:
        """旧 API ``get_nodes_in_range``：形状适配，规则委托 ng 组件。"""
        return self.ng.nodes.in_range(start_ts, end_ts, layer, limit)

    def get_recent_context(self, limit: int = 20) -> List[Node]:
        """旧 API ``get_recent_context``：形状适配，规则委托 ng 组件。"""
        return self.ng.nodes.query(layer=MemoryLayer.CONTEXT, limit=limit, order="written_desc")   # 上游 #259

    def enforce_context_cap(self, max_size: int) -> None:
        """旧 API ``enforce_context_cap``：形状适配，规则委托 ng 组件。"""
        self._mnt.enforce_cap(max_size)

    # ------------------------------------------------------------ 边
    def add_edge(self, edge: Edge) -> str:
        """旧 API ``add_edge``：形状适配，规则委托 ng 组件。"""
        return self.ng.edges.put(edge)

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        """旧 API ``get_edge``：形状适配，规则委托 ng 组件。"""
        return self.ng.edges.get(edge_id)

    def verify_edge(self, edge_id: str, new_confidence: Optional[float] = None) -> None:
        """旧 API ``verify_edge``：形状适配，规则委托 ng 组件。"""
        self.ng.edges.verify(edge_id, new_confidence)

    def get_outgoing_edges(self, node_id: str) -> List[Edge]:
        """旧 API ``get_outgoing_edges``：形状适配，规则委托 ng 组件。"""
        return self.ng.edges.outgoing(node_id)

    def get_incoming_edges(self, node_id: str) -> List[Edge]:
        """旧 API ``get_incoming_edges``：形状适配，规则委托 ng 组件。"""
        return self.ng.edges.incoming(node_id)

    def traverse(self, start_id: str, relation_types: Optional[List[str]] = None, direction: str = "out",
                 max_depth: int = 5, min_importance: float = 0.0, max_nodes: int = 500) -> List[Dict]:
        """旧 API ``traverse``：形状适配，规则委托 ng 组件。"""
        return graphquery.traverse(self.ng, start_id, relation_types, direction, max_depth,
                                   min_importance, max_nodes)

    def subgraph(self, root_id: str, max_depth: int = 3, relation_types: Optional[List[str]] = None,
                 direction: str = "out") -> Dict:
        """旧 API ``subgraph``：形状适配，规则委托 ng 组件。"""
        return graphquery.subgraph(self.ng, root_id, max_depth, relation_types, direction)

    def spatiotemporal_query(self, center_node_id: str, time_radius: float = 300.0,
                             space_metric: Optional[str] = None, space_radius: float = 0.5,
                             max_results: int = 20) -> List[Tuple[Node, float]]:
        """旧 API ``spatiotemporal_query``：形状适配，规则委托 ng 组件。"""
        return graphquery.spatiotemporal(self.ng, center_node_id, time_radius, space_metric,
                                         space_radius, max_results)

    # ------------------------------------------------------------ 因果
    def _adj(self, types: Sequence[str]):
        """旧 API ``_adj``：形状适配，规则委托 ng 组件。"""
        arcs = [(i, s, t) for i, s, t, _, _ in self.ng.edges.topology(list(types))]
        return causal.build_adjacency(arcs)

    def infer_causal_paths(self, start_id: str, end_id: str, max_depth: int = 5,
                           relation_types: Optional[List[str]] = None,
                           max_paths: int = CAUSAL_MAX_PATHS) -> List[List[Edge]]:
        """旧 API ``infer_causal_paths``：形状适配，规则委托 ng 组件。

        ``max_paths``（上游 #327 同名同缺省 1000）：枚举至多这么多条即停（返回前 max_paths 条，不加截断标记，与上游同）。"""
        adj, _ = self._adj(relation_types or ["causal"])
        cap = _pos_int(max_paths, "max_paths")
        paths = causal.paths_between(adj, start_id, end_id, max_depth, max_paths=cap)[:cap]   # 进入节点时判满可多出几条
        edges = self.ng.edges.get_many([e for p in paths for e in p])
        out = [[edges[e] for e in p] for p in paths]
        out.sort(key=lambda p: (len(p), -sum(e.confidence for e in p) / len(p)))
        return out

    def find_cycles(self, max_depth: int = 10, limit: Optional[int] = None,
                    max_cycles: Optional[int] = 100000) -> List[List[Edge]]:
        """环长 ≤ max_depth+1（旧口径）；每条入环边只反序列化一次并跨环共享对象。

        ``limit``（上游 #252 同名）：至多返回这么多条环（先枚举到的）。与上游的差异：``limit=None`` 时上游不设上限，
        ng 仍受 ``max_cycles``（缺省 10 万）硬上限约束（防稠密 SCC 指数爆炸）；两者都给时取较小者。"""
        if limit is not None:
            lim = _pos_int(limit, "limit")
            max_cycles = lim if max_cycles is None else min(lim, max_cycles)
        adj, order = self._adj(("causal", "cyclic"))
        scan = causal.enumerate_cycles(adj, order, max_depth + 1, max_cycles)
        ids = list(set(itertools.chain.from_iterable(scan.cycles)))
        objs: Dict[str, Edge] = {}
        for part in schema.chunks(ids):
            for row in self.conn.execute(f"SELECT * FROM edges WHERE id IN ({schema.placeholders(len(part))})",
                                         tuple(part)).fetchall():
                objs[row[0]] = Edge.from_row(tuple(row))   # STEdge 即 Edge（compat 中的别名）
        return [[objs[e] for e in cyc] for cyc in scan.cycles]

    def has_causal_cycle(self) -> bool:
        """旧 API ``has_causal_cycle``：形状适配，规则委托 ng 组件。"""
        return causal.has_cycle_columns(*self.ng.edges.pair_columns(("causal", "cyclic")))

    def decay_cycle(self, factor: float = 0.02, min_confidence: float = 0.1, now: Optional[float] = None) -> None:
        """旧 API ``decay_cycle``：形状适配，规则委托 ng 组件。

        ``now``（上游 #176 同名同义）：``None`` ⇒ 每次调用 = 一个周期（旧步进语义，行为不变）；给出墙钟时刻 ⇒
        按 ``dt = now − 上次衰减时刻`` 换算等效遗忘比例（每 60 s 一个 ``factor``，见 :func:`lingshu_ng.decay.elapsed_factor`），
        「相同 Δt 下调用 1 次与 60 次结果相同」。首次进入时间模式按一个周期计；时钟回拨 dt 记 0。上次时刻存 engine_meta。"""
        if now is not None:
            factor = elapsed_factor(factor, self._decay_dt(now), DECAY_PERIOD_SECONDS)
        self._mnt.step(factor, min_confidence)

    def _decay_dt(self, t: float) -> float:
        t = require_finite(t, "now")
        last = self.ng.meta.get(LAST_DECAY_META_KEY).get(LAST_DECAY_META_KEY)
        try:
            dt = DECAY_PERIOD_SECONDS if last is None else max(0.0, t - float(last))
        except (TypeError, ValueError):
            _log.warning("engine_meta.%s 不是数值（%r）→ 按一个周期计", LAST_DECAY_META_KEY, last)
            dt = DECAY_PERIOD_SECONDS
        self.ng.meta.set(LAST_DECAY_META_KEY, repr(t))
        return dt

    # ------------------------------------------------------------ 检索
    @staticmethod
    def char_bigram_jaccard(a: str, b: str) -> float:
        """旧 API ``char_bigram_jaccard``：形状适配，规则委托 ng 组件。"""
        if not a or not b:
            return 0.0
        return jaccard(bigrams(a), bigrams(b))

    @staticmethod
    def expand_query_terms(query: str) -> list:
        """旧 API ``expand_query_terms``：形状适配，规则委托 ng 组件。"""
        return expand_terms(query)

    def search_content(self, query: str, layers: Optional[List[MemoryLayer]] = None,
                       limit: int = 20) -> List[Tuple[Node, float]]:
        """旧 API ``search_content``：形状适配，规则委托 ng 组件。"""
        return self._retriever.search(query, layers, limit)

    def semantic_search(self, query: str, provider, limit: int = 10) -> List[Node]:
        """旧 API ``semantic_search``：形状适配，规则委托 ng 组件。"""
        found = self.ng.nodes.get_many(list(provider.search(query, limit)))
        self.ng.nodes.touch(list(found))
        return list(found.values())

    # ------------------------------------------------------------ 盲区（关闭需密钥）
    def add_blindspot(self, code: str, description: str, severity: str = "medium",
                      category: str = "operational", predictability: str = "pending_assessment") -> str:
        """旧 API ``add_blindspot``：形状适配，规则委托 ng 组件。"""
        return self.ng.registry.add_blindspot(code, description, severity, category, predictability)

    def list_blindspots(self, status: Optional[str] = None) -> List[Dict]:
        """旧 API ``list_blindspots``：形状适配，规则委托 ng 组件。"""
        return self.ng.registry.list_blindspots(status)

    def resolve_blindspot(self, blindspot_id: str, designer_key: Optional[str] = None) -> None:
        """旧 API ``resolve_blindspot``：形状适配，规则委托 ng 组件。"""
        self.ng.registry.set_blindspot_status(blindspot_id, "resolved", designer_key)

    def update_blindspot_status(self, blindspot_id: str, status: str,
                                designer_key: Optional[str] = None) -> None:
        """旧 API ``update_blindspot_status``：形状适配，规则委托 ng 组件。"""
        self.ng.registry.set_blindspot_status(blindspot_id, status, designer_key)

    # ------------------------------------------------------------ 技能
    def add_skill(self, name: str, description: str, procedure: str, confidence: float = 0.5) -> str:
        """旧 API ``add_skill``：形状适配，规则委托 ng 组件。"""
        return self._skills.add(name, description, procedure, confidence)

    def search_skills(self, query: str, limit: int = 10) -> List[Dict]:
        """旧 API ``search_skills``：形状适配，规则委托 ng 组件。"""
        return self._skills.search(query, limit)

    def get_skill_by_name(self, name: str) -> Optional[Dict]:
        """按**精确名称**取技能卡，无同名返回 None（上游 #200）。ng 的精确名按规范化键比较（大小写/全半角/首尾空白不敏感）。"""
        return self._skills.by_name(name)

    def count_skills(self) -> int:
        """旧 API ``count_skills``：形状适配，规则委托 ng 组件。"""
        return self._skills.count()

    def update_skill_confidence(self, skill_id: str, delta: float) -> None:
        """旧 API ``update_skill_confidence``：形状适配，规则委托 ng 组件。"""
        self._skills.adjust(skill_id, delta)

    def append_skill_procedure(self, skill_id: str, step: str) -> None:
        """旧 API ``append_skill_procedure``：形状适配，规则委托 ng 组件。"""
        self._skills.append_procedure(skill_id, step)

    # ------------------------------------------------------------ 治理
    def add_promotion_proposal(self, node_id: str, requester: str, reason: str) -> str:
        """旧 API ``add_promotion_proposal``：形状适配，规则委托 ng 组件。"""
        n = self.ng.nodes.get(node_id)
        return self.ng.registry.add_proposal(node_id, requester, reason, n.content if n else "")

    def verify_promotion(self, proposal_id: str, verified_by: str) -> bool:
        """旧 API ``verify_promotion``：形状适配，规则委托 ng 组件。返回是否通过（与上游同形；rel-v1.19 及以前恒为 None）。"""
        p = self.ng.registry.proposal(proposal_id)
        n = self.ng.nodes.get(p["node_id"]) if p else None
        if n is None:
            return False
        return bool(self.ng.registry.verify_proposal(proposal_id, verified_by, n.content or ""))

    def adjudicate_promotion(self, proposal_id: str, adjudicated_by: str, approved: bool,
                             designer_key: Optional[str] = None) -> Optional[str]:
        """store 级终裁（上游同名同签名）：密钥闸 fail-closed（PermissionError）；只有已复核的提案可终裁；
        被提案节点已不存在或内容与复核时不同 ⇒ 不写结构层、返回 None。通过 ⇒ 节点进结构层并返回其 id；
        否决 ⇒ 记 promotion 负记忆。规则与 :meth:`lingshu_ng.engine.MemoryEngine.adjudicate_promotion` 同源。"""
        return adjudicate(self.ng, self._neg, proposal_id, adjudicated_by, approved, designer_key)

    def protect_node(self, node_id: str, reason: str) -> None:
        """旧 API ``protect_node``：形状适配，规则委托 ng 组件。"""
        self.ng.registry.protect(node_id, reason)

    def get_protected_nodes(self) -> List[str]:
        """旧 API ``get_protected_nodes``：形状适配，规则委托 ng 组件。"""
        return self.ng.registry.protected_ids()

    def register_conflict(self, a_id: str, b_id: str,
                          condition_space: Optional[ConditionSpace] = None) -> Optional[Edge]:
        """旧 API ``register_conflict``：形状适配，规则委托 ng 组件。"""
        if self.ng.nodes.get(a_id) is None or self.ng.nodes.get(b_id) is None:
            return None
        import uuid
        e = Edge(id=f"edge_{uuid.uuid4().hex[:12]}", source_id=a_id, target_id=b_id,
                 relation_type=EdgeType.OPPOSITE, confidence=0.3, verified=False,
                 condition_space=condition_space or ConditionSpace.default("冲突检测", "验证单元预筛选"))
        with self.ng.db.tx():
            self.ng.edges.put(e)
            for nid in (a_id, b_id):
                self.ng.nodes.add_tags(nid, ["conflict"])
        return e

    def add_rejected_path(self, path_type: str, description: str, reason: str, evidence: str = "") -> str:
        """旧 API ``add_rejected_path``：形状适配，规则委托 ng 组件。"""
        return self._neg.record(path_type, description, reason, evidence)

    def list_rejected_paths(self, status: Optional[str] = None) -> List[Dict]:
        """旧 API ``list_rejected_paths``：形状适配，规则委托 ng 组件。"""
        return self._neg.list(status)

    def mark_rejected_path_consumed(self, rejected_id: str) -> None:
        """旧 API ``mark_rejected_path_consumed``：形状适配，规则委托 ng 组件。"""
        self._neg.consume(rejected_id)

    def add_verifier_standard(self, name: str, param: str, value: float, reason: str, proposer: str) -> str:
        """旧 API ``add_verifier_standard``：形状适配，规则委托 ng 组件。"""
        return self.ng.registry.add_standard(name, param, value, reason, proposer)

    def list_verifier_standards(self, status: Optional[str] = None) -> List[Dict]:
        """旧 API ``list_verifier_standards``：形状适配，规则委托 ng 组件。"""
        return self.ng.registry.list_standards(status)

    def review_verifier_standard(self, vid: str, reviewer: str, approved: bool) -> bool:
        """旧 API ``review_verifier_standard``：形状适配，规则委托 ng 组件。"""
        return self.ng.registry.step_standard(vid, reviewer, approved, "review") is not None

    def cs_review_verifier_standard(self, vid: str, reviewer: str, approved: bool) -> bool:
        """旧 API ``cs_review_verifier_standard``：形状适配，规则委托 ng 组件。"""
        return self.ng.registry.step_standard(vid, reviewer, approved, "cs_review") is not None

    def adjudicate_verifier_standard(self, vid: str, adjudicator: str, approved: bool,
                                     designer_key: Optional[str] = None) -> Optional[Dict]:
        """旧 API ``adjudicate_verifier_standard``：形状适配，规则委托 ng 组件。"""
        r = self.ng.registry.step_standard(vid, adjudicator, approved, "adjudicate", designer_key)
        return {"id": r["id"], "param": r["param"], "value": r["value"], "status": r["status"]} if r else None

    def list_escalation_points(self, enabled_only: bool = True) -> List[Dict]:
        """旧 API ``list_escalation_points``：形状适配，规则委托 ng 组件。"""
        return self.ng.registry.list_escalations(enabled_only)

    def add_escalation_point(self, code: str, trigger: str, condition: str, action: str,
                             severity: str = "medium") -> str:
        """旧 API ``add_escalation_point``：形状适配，规则委托 ng 组件。"""
        return self.ng.registry.add_escalation(code, trigger, condition, action, severity)

    def set_escalation_enabled(self, escalation_id: str, enabled: bool,
                               designer_key: Optional[str] = None) -> None:
        """旧 API ``set_escalation_enabled``：密钥闸在仓储层；成功后落 action_logs 审计（上游 #130）。"""
        if self.ng.registry.set_escalation_enabled(escalation_id, enabled, designer_key):
            self.ng.meta.log_action("escalation_toggle", f"升级点 {escalation_id} → enabled={bool(enabled)}",
                                    outcome={"escalation_id": escalation_id, "enabled": bool(enabled)})

    # ------------------------------------------------------------ 结构重要性 / 洞察
    def recalc_structural_importance(self, dry_run: bool = True, **kw) -> Dict:
        """旧 API ``recalc_structural_importance``：形状适配，规则委托 ng 组件。"""
        return graphquery.recalc_structural_importance(self.ng, dry_run, **kw)

    def insight_record(self, content: str, conditions: Optional[dict] = None, source: str = "",
                       importance: float = 0.7) -> Dict:
        """旧 API ``insight_record``：形状适配，规则委托 ng 组件。"""
        return self._ins.record(content, conditions, source, importance)

    def insight_verify(self, insight_id: str, level: str = "V2", evidence: object = None) -> Dict:
        """旧 API ``insight_verify``：形状适配，规则委托 ng 组件。"""
        return self._ins.verify(insight_id, level, evidence)

    def insight_report(self, window: Optional[int] = None) -> Dict:
        """旧 API ``insight_report``：形状适配，规则委托 ng 组件。"""
        return self._ins.report(window)

    def insight_window(self, conditions: Optional[dict] = None) -> Dict:
        """旧 API ``insight_window``：形状适配，规则委托 ng 组件。"""
        return self._ins.window(conditions)

    # ------------------------------------------------------------ 审计 / 时间取数 / 自我快照
    def log_action(self, action_type: str, summary: str = "", node_ids: Optional[list] = None,
                   outcome: Optional[dict] = None, context: Optional[dict] = None) -> None:
        """落一条行为审计到 action_logs（上游同名同签名；ng 的日志表有界，最旧的先淘汰）。"""
        self.ng.meta.log_action(action_type, summary, node_ids or (), outcome, context)

    def query_nodes_by_time(self, start_ts: Optional[float] = None, end_ts: Optional[float] = None,
                            limit: Optional[int] = None) -> List[Node]:
        """按 ``temporal_coordinate`` 取节点：两端可省、闭区间、时间**升序**（同刻按 id），过滤与排序都在 SQL（上游 #179）。
        无时间坐标的行不返回。"""
        sql, params = f"{NODE_SELECT} WHERE temporal_coordinate IS NOT NULL", []
        if start_ts is not None:
            sql += " AND temporal_coordinate >= ?"
            params.append(require_finite(start_ts, "start_ts"))
        if end_ts is not None:
            sql += " AND temporal_coordinate <= ?"
            params.append(require_finite(end_ts, "end_ts"))
        sql += " ORDER BY temporal_coordinate ASC, id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return [Node.from_row(tuple(r)) for r in self.ng.db.all(sql, params)]

    def prune_self_snapshots(self, keep: int) -> int:
        """自我快照有界保留（上游 #201）：只留最近 ``keep`` 条，返回删除条数。ng 的快照在独立表 self_snapshots
        （不进 nodes、不参与召回，写入时已按 SNAPSHOT_KEEP 有界），本方法只动该表，SELF 节点与保护名单一律不动。"""
        k = int(keep)
        if k < 0:
            raise ValueError("keep 不能为负")
        with self.ng.db.tx() as c:
            cur = c.execute("DELETE FROM self_snapshots WHERE id NOT IN "
                            "(SELECT id FROM self_snapshots ORDER BY id DESC LIMIT ?)", (k,))
            return cur.rowcount

    # ------------------------------------------------------------ 统计
    def get_stats(self) -> Dict:
        """旧 API ``get_stats``：形状适配，规则委托 ng 组件。"""
        stats = {f"{m.value}_nodes": self.ng.nodes.count(m) for m in MemoryLayer}
        stats["total_edges"] = self.ng.edges.count()
        stats["verified_edges"] = self.ng.edges.count(verified=True)
        return stats

    def close(self) -> None:
        """旧 API ``close``：形状适配，规则委托 ng 组件。"""
        self.ng.close()
