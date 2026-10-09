# -*- coding: utf-8 -*-
"""compat · 旧 ``lingshu.core.core`` 的兼容门面（同名同签名）

用途：让旧调用方（含 tests/ 下的 core 测试）在 ``LINGSHU_IMPL=ng`` 时零改动跑在 ng 上。
本模块只做**形状适配**（旧返回类型 / 旧参数名 / 旧异常类型），一切规则都委托给 ng 组件，
所以旧 API 上同样享有 ng 的不变量（层守卫、精确标签、值域校验……）。

与旧版行为**有意不同**之处（旧行为即缺陷，详见 REWRITE_REPORT_core.md 兼容性矩阵）：
  * 衰减跳过受保护/钉住节点与 OPPOSITE 边；store 层关闭盲区需设计者密钥；
  * ``get_layer_nodes`` 返回整层（不截 50 条）；``get_nodes_by_tag`` 精确匹配；
  * ``update_self`` 就地更新单个 SELF 节点（不再每次新建快照节点）。
"""
from __future__ import annotations

import itertools
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

STNode = Node
STEdge = Edge

__all__ = ["ConditionSpace", "NodeType", "EdgeType", "MemoryLayer", "Role", "STNode", "STEdge",
           "CausalChain", "SelfModel", "LayeredStore", "SpacetimeMemoryEngine", "cred_step",
           "designer_key_configured", "verify_designer"]


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
                           relation_types: Optional[List[str]] = None) -> List[List[Edge]]:
        """旧 API ``infer_causal_paths``：形状适配，规则委托 ng 组件。"""
        adj, _ = self._adj(relation_types or ["causal"])
        paths = causal.paths_between(adj, start_id, end_id, max_depth)
        edges = self.ng.edges.get_many([e for p in paths for e in p])
        out = [[edges[e] for e in p] for p in paths]
        out.sort(key=lambda p: (len(p), -sum(e.confidence for e in p) / len(p)))
        return out

    def find_cycles(self, max_depth: int = 10, max_cycles: Optional[int] = 100000) -> List[List[Edge]]:
        """环长 ≤ max_depth+1（旧口径）；每条入环边只反序列化一次并跨环共享对象。"""
        adj, order = self._adj(("causal", "cyclic"))
        scan = causal.enumerate_cycles(adj, order, max_depth + 1, max_cycles)
        ids = list(set(itertools.chain.from_iterable(scan.cycles)))
        objs: Dict[str, Edge] = {}
        for part in schema.chunks(ids):
            for row in self.conn.execute(f"SELECT * FROM edges WHERE id IN ({schema.placeholders(len(part))})",
                                         tuple(part)).fetchall():
                objs[row[0]] = STEdge.from_row(tuple(row))
        return [[objs[e] for e in cyc] for cyc in scan.cycles]

    def has_causal_cycle(self) -> bool:
        """旧 API ``has_causal_cycle``：形状适配，规则委托 ng 组件。"""
        return causal.has_cycle_pairs(self.ng.edges.pairs(("causal", "cyclic")))

    def decay_cycle(self, factor: float = 0.02, min_confidence: float = 0.1) -> None:
        """旧 API ``decay_cycle``：形状适配，规则委托 ng 组件。"""
        self._mnt.step(factor, min_confidence)

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

    def verify_promotion(self, proposal_id: str, verified_by: str) -> None:
        """旧 API ``verify_promotion``：形状适配，规则委托 ng 组件。"""
        p = self.ng.registry.proposal(proposal_id)
        n = self.ng.nodes.get(p["node_id"]) if p else None
        if n is not None:
            self.ng.registry.verify_proposal(proposal_id, verified_by, n.content or "")

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


from .compat_txguard import _loads_tags, _store_tx_guard  # noqa: E402,F401  旧模块级辅助名（#184/#267）
from .compat_engine import SpacetimeMemoryEngine  # noqa: E402  （门面类在独立模块，避免本文件超长）
