# -*- coding: utf-8 -*-
"""compat_engine · 旧 ``SpacetimeMemoryEngine`` 的兼容门面

形状与旧类一致（构造签名、方法名、返回 STNode/dict/list 的形态），行为委托给
:class:`lingshu_ng.engine.MemoryEngine`。世界模型外观 13 个方法在 :mod:`lingshu_ng.compat_world`
（委托 lingshu_ng.world 或返回旧版「组件不可导入」状态）；仓外器官组件集中在
:mod:`lingshu_ng.compat_stubs`，返回与旧版「组件未装配」一致的状态字典。

不变量：门面方法不直接写 SQL；所有写入都经 ng 组件（因而受 LayerPolicy 约束）。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .compat_stubs import StubsMixin
from .compat_world import WorldFacade
from .compat_world_sim import WorldSimFacade
from .compat_frame import FrameMixin
from .decay import elapsed_factor
from .engine import MemoryEngine
from .graphquery import timeline as _timeline
from .scheduler import AutoDecay
from .types import ConditionSpace, Edge, EdgeType, MemoryLayer, Node, Role, dumps, now

from .exchange import TABLES as _EXPORT_TABLES

__all__ = ["SpacetimeMemoryEngine"]

_SCREEN_RE = re.compile(r"\[[^\]]*?((?:[A-Za-z]:[\\/]|/)[^\]]+\.(?:png|bmp|jpg))\]")


class SpacetimeMemoryEngine(WorldFacade, WorldSimFacade, FrameMixin, StubsMixin):
    """旧引擎门面（PRIMARY/SUB 角色、:memory: 默认库）。"""

    #: 全库备份表清单 = ng 实际导出清单（exchange.TABLES，含 #270 的 OBS 持久化表）；
    #: 旧契约「产物键集 ⊆ M13_TABLES、tables 计数 = 清单长度 − skipped」据此成立。
    M13_TABLES = _EXPORT_TABLES
    #: 旧内存复用 tracker 的轮数上界（上游 #208）。ng 不在内存持有 tracker（复用观测只落库、由唯一索引
    #: 去重），``_reuse_tracker`` 恒为空，上界自然成立。
    REUSE_TRACKER_ROUNDS = 64
    #: self_check 环枚举上限（= MemoryEngine.self_check 的 cycle_budget；超限 cycles_truncated=True，上游 #215）
    SELF_CHECK_CYCLE_LIMIT = 256
    ANCHOR_KINDS = ("pre_access_stance", "introspection", "external_calibration")
    META_BLINDSPOT_DEFINITION = "对人类造成文明级别的重大负面影响"
    RECURSION_LIMIT = 3

    def __init__(self, db_path: str = ":memory:", identity: str = "协议实例",
                 role: Role = Role.PRIMARY) -> None:
        """内部辅助函数。"""
        from .compat import LayeredStore
        self.ng = MemoryEngine(db_path, identity, role)
        self.store = LayeredStore(db_path, role, _ng_store=self.ng.store)
        self.role = self.ng.store.role
        self._body_registry: Any = None
        self._body_error = "身体层未装配（ng 不内置设备注册表）"
        self._event_queue: List[Dict] = []
        self._lifecycle: Any = None
        self._embedding_provider: Any = None
        # 后台衰减经仓储门面 store.decay_cycle（与旧引擎同一入口；规则同 ng Maintenance.step）
        self.ng.autodecay = AutoDecay(lambda el: self.store.decay_cycle(elapsed_factor(0.02, el, 60.0)))
        if not self.ng.store.registry.list_escalations(enabled_only=False):
            self._seed_escalation_points()
        self.migrate_v17_coordinates()          # D-003 旧库坐标字段分离（旧 v1.7 构造期迁移）

    # ------------------------------------------------------------ 只读属性
    @property
    def self_model(self):
        """当前自我模型（持久化于 SELF 核心节点）。"""
        return self.ng.self_store.model

    @property
    def _interaction_count(self) -> int:
        """交互轮次（飞轮记账口径）。"""
        return self.ng.round

    @_interaction_count.setter
    def _interaction_count(self, v: int) -> None:
        """允许旧调用方推进轮次。"""
        self.ng.round = int(v)

    @property
    def _reuse_tracker(self) -> Dict:
        """ng 不持有内存复用 tracker（复用观测只落库，由唯一索引去重，#208）——恒为空。"""
        return {}

    @property
    def _session_id(self) -> str:
        """内部辅助函数。"""
        return self.ng.session_id

    def _node(self, node_id: Optional[str]) -> Optional[Node]:
        """内部辅助函数。"""
        return self.ng.store.nodes.get(node_id) if node_id else None

    def _written(self, r: Any) -> Optional[Node]:
        """写入回执 → 节点：新建且仍在库（layer 非空）时按刚落库的行还原（免回读），否则回读。"""
        if r.action == "created" and r.layer is not None and r.node_id:
            n = self.ng.store.nodes.fresh(r.node_id)
            if n is not None:
                return n
        return self._node(r.node_id)

    # ------------------------------------------------------------ 写入
    def add_perception(self, content: str, modality: str = "text",
                       spatial_coordinates: Optional[Dict[str, float]] = None,
                       condition_space: Optional[ConditionSpace] = None, importance: float = 0.5,
                       tags: Optional[List[str]] = None, entities: Optional[List[str]] = None,
                       skip_dedup: bool = False) -> Node:
        """知识层写入（M5 去重命中时返回被合并的既有节点）。"""
        r = self.ng.perceive(content, modality, spatial_coordinates, condition_space, importance,
                             tags, entities, skip_dedup)
        return self._written(r)

    def set_anchor(self, content: str, importance: float = 1.0,
                   condition_space: Optional[ConditionSpace] = None) -> Node:
        """锚点层写入（仅 PRIMARY）。"""
        return self._written(self.ng.add_shared(MemoryLayer.ANCHOR, content, importance, condition_space))

    def add_structure_node(self, content: str, importance: float = 0.8,
                           condition_space: Optional[ConditionSpace] = None) -> Node:
        """结构层写入（仅 PRIMARY）。"""
        return self._written(self.ng.add_shared(MemoryLayer.STRUCTURE, content, importance,
                                                condition_space))

    def get_anchors(self) -> List[Node]:
        """全部锚点（整层，不截断）。"""
        return self.store.get_layer_nodes(MemoryLayer.ANCHOR)

    def add_context(self, content: str, importance: float = 0.4,
                    condition_space: Optional[ConditionSpace] = None,
                    tags: Optional[List[str]] = None) -> Node:
        """情境层写入（持久化 FIFO 上限）。"""
        return self._written(self.ng.add_context(content, importance, condition_space, tags))

    def get_recent_context(self, limit: int = 20) -> List[Node]:
        """最近情境节点。"""
        return self.store.get_recent_context(limit)

    def set_context_cap(self, max_size: int) -> None:
        """设置并持久化情境层容量上限（上游 #246：浮点整值归一为 int；非整数/布尔/None/字符串在配置点即报错）。"""
        self.ng.maintenance.set_context_cap(max_size)

    @property
    def _context_max(self) -> int:
        """当前生效的情境层容量上限（库内持久值，同库多实例共享）。"""
        return self.ng.maintenance.context_cap()

    @property
    def _decay_thread(self):
        """后台衰减线程（未启动为 None）。"""
        return self.ng.autodecay._thread

    @property
    def _running(self) -> bool:
        """后台衰减是否在运行。"""
        return self.ng.autodecay.running

    def set_dedup_config(self, static_threshold: float = 0.85, window: int = 30) -> None:
        """M5 阈值（钳到 [0.5, 0.95]）；window 在 ng 中无意义（无动态死区）。"""
        from .dedup import clamp_threshold
        self.ng.dedup_threshold = clamp_threshold(float(static_threshold))

    def add_edge(self, source_id: str, target_id: str, relation_type: Any = EdgeType.CAUSAL,
                 confidence: float = 0.5, condition_space: Optional[ConditionSpace] = None,
                 source_evidence: str = "extracted") -> Edge:
        """建边（relation_type 可为枚举或字符串）。"""
        return self.ng.link(source_id, target_id, relation_type, confidence, condition_space, source_evidence)

    def verify_edge(self, edge_id: str, new_confidence: Optional[float] = None) -> None:
        """复核边。"""
        self.ng.store.edges.verify(edge_id, new_confidence)

    def register_conflict(self, a_id: str, b_id: str) -> Optional[Edge]:
        """矛盾登记。"""
        return self.ng.register_conflict(a_id, b_id)

    def protect_node(self, node_id: str, reason: str) -> None:
        """不可遗忘保护。"""
        self.ng.protect(node_id, reason)

    def get_protected_nodes(self) -> List[str]:
        """保护名单。"""
        return self.store.get_protected_nodes()

    # ------------------------------------------------------------ 查询
    def spatiotemporal_query(self, node_id: str, time_radius: float = 300.0, space_metric: Optional[str] = None,
                             space_radius: float = 0.5, max_results: int = 20) -> List[Tuple[Node, float]]:
        """时空邻域。"""
        return self.store.spatiotemporal_query(node_id, time_radius, space_metric, space_radius, max_results)

    def reason_causal(self, start_id: str, end_id: Optional[str] = None, max_depth: int = 5,
                      relation_types: Optional[List[str]] = None, importance_weighted: bool = False,
                      include_subgraph: bool = False) -> list:
        """因果链/路径；可按节点 importance 均值排序、可附尾节点子图。"""
        if end_id:
            paths: list = self.store.infer_causal_paths(start_id, end_id, max_depth, relation_types)
        else:
            paths = self.ng.reason_causal(start_id, None, max_depth, relation_types)
        if importance_weighted and paths:
            nodes = self.ng.store.nodes.get_many([e.source_id for p in paths for e in p] +
                                                 [p[-1].target_id for p in paths])

            def mean(p: list) -> float:
                """路径节点 importance 均值。"""
                ids = [e.source_id for e in p] + [p[-1].target_id]
                vals = [(nodes[i].importance if i in nodes else 0.5) or 0.0 for i in ids]
                return sum(vals) / len(vals)
            paths.sort(key=lambda p: (-mean(p), len(p)))
        if include_subgraph:
            return [{"path": p, "subgraph": self.store.subgraph(p[-1].target_id if p else start_id, 2)}
                    for p in paths]
        return paths

    def search_content(self, query: str, layers: Optional[List[MemoryLayer]] = None,
                       limit: int = 20) -> List[Tuple[Node, float]]:
        """内容检索（并记飞轮复用）。"""
        return self.ng.search(query, layers, limit)

    def semantic_search(self, query: str, limit: int = 10) -> List[Tuple[Node, float]]:
        """无语义提供者时退化为内容检索（与旧版一致）。"""
        return self.ng.search(query, limit=limit)

    def set_embedding_provider(self, provider: Any) -> None:
        """注入嵌入提供者（M1 · D-005）：转给 ng 引擎作为可选第二路召回（lingshu_ng.semindex）。"""
        self._embedding_provider = provider
        self.ng.set_embedding_provider(provider)

    def recall(self, context_content: str, limit: int = 10) -> List[Tuple[Node, float]]:
        """组合召回（内容/重要度/置信度/近因）。"""
        return self.ng.recall(context_content, limit)["hits"]

    def traverse(self, start_id: str, relation_types: Optional[List[str]] = None, direction: str = "out",
                 max_depth: int = 5, min_importance: float = 0.0, max_nodes: int = 500) -> List[Dict]:
        """有界遍历。"""
        return self.store.traverse(start_id, relation_types, direction, max_depth, min_importance, max_nodes)

    def subgraph(self, root_id: str, max_depth: int = 3, relation_types: Optional[List[str]] = None) -> Dict:
        """子图。"""
        return self.store.subgraph(root_id, max_depth, relation_types)

    def what_happened_at(self, timestamp: float, tolerance: float = 60.0, limit: int = 20) -> list:
        """时间点附近（全库时间索引，不截 importance 前 500）。"""
        ns = self.ng.store.nodes.in_range(timestamp - tolerance, timestamp + tolerance, limit=None)
        res = sorted(((n, abs(n.temporal_coordinate - timestamp)) for n in ns), key=lambda x: (x[1], x[0].id))
        return res[:limit]

    def timeline(self, node_id: str, direction: str = "forward", max_depth: int = 20) -> List[Node]:
        """时间线。"""
        return _timeline(self.ng.store, node_id, direction, max_depth)

    def get_timeline(self, start_ts: Optional[float] = None, end_ts: Optional[float] = None,
                     layer: Optional[MemoryLayer] = None, limit: int = 50) -> List[Node]:
        """时间范围。"""
        return self.ng.store.nodes.in_range(start_ts or 0.0, end_ts if end_ts is not None else now() + 1,
                                            layer, limit)

    def session_summary(self, window_seconds: float = 3600.0, limit: int = 10) -> List[Dict]:
        """按时间窗分组的叙事压缩（全库，按时间序）。"""
        nodes = [n for n in self.ng.store.nodes.scan() if n.layer != MemoryLayer.SELF]
        nodes.sort(key=lambda n: (n.temporal_coordinate or 0.0, n.id))
        groups: List[Tuple[float, List[Node]]] = []
        for n in nodes:
            if groups and (n.temporal_coordinate or 0.0) - groups[-1][0] <= window_seconds:
                groups[-1][1].append(n)
            else:
                groups.append((n.temporal_coordinate or 0.0, [n]))
        return [{"window_start": s, "count": len(g), "layers": sorted({n.layer.value for n in g}),
                 "top": [n.content[:40] for n in sorted(g, key=lambda n: -(n.importance or 0))[:3]]}
                for s, g in groups[-limit:]]

    # ------------------------------------------------------------ 自我 / 信任
    def update_self(self, updates: Dict, link_to_node_id: Optional[str] = None) -> Optional[Node]:
        """白名单修改 SELF（就地更新 + 快照表）；可建自我→经历边。返回 SELF 当前节点（旧契约）。"""
        self.ng.self_store.update(updates or {})
        if link_to_node_id:
            self.ng.self_store.link(link_to_node_id)
        return self._node("self_core")

    #: 旧名：SELF 层「单一当前节点」的固定 id（上游 #201）；ng 的核心自我节点即此节点。
    SELF_CURRENT_ID = "self_core"

    def record_value_change(self, value: str, trigger: str, replaces: Optional[str] = None,
                            link_to_node_id: Optional[str] = None) -> bool:
        """价值观修正的引擎入口（上游 #212）：按条修正，发生变化时落快照；返回是否变化。"""
        changed = self.ng.self_store.model.record_value_change(value, trigger, replaces)
        if changed and link_to_node_id:
            self.ng.self_store.link(link_to_node_id)
        return changed

    def get_self_model(self):
        """自我模型。"""
        return self.ng.self_store.model

    def update_trust_state(self, t_total: float, round_no: int, p_trust: Optional[float] = None,
                           p_gap: Optional[float] = None) -> Optional[Node]:
        """记录信任状态（值域校验），返回 SELF 核心节点。"""
        self.ng.self_store.update_trust(t_total, round_no, p_trust, p_gap)
        return self._node("self_core")

    def apply_value_candidate(self, candidate_id: str, new_value: Optional[str] = None) -> bool:
        """价值观按条新增（ng：无候选池组件，直接以 new_value 新增）。"""
        if not new_value:
            return False
        self.ng.self_store.change_value(new_value, f"candidate:{candidate_id}")
        return True

    # ------------------------------------------------------------ 盲区
    def register_blindspot(self, code: str, description: str, severity: str = "medium",
                           category: str = "operational", predictability: str = "pending_assessment") -> str:
        """登记盲区（元盲区零记录）。"""
        return self.ng.register_blindspot(code, description, severity, category, predictability)

    def list_blindspots(self, status: Optional[str] = None) -> List[Dict]:
        """列盲区。"""
        return self.store.list_blindspots(status)

    def get_open_blindspots(self) -> List[Dict]:
        """开放盲区。"""
        return self.store.list_blindspots("open")

    def resolve_blindspot(self, blindspot_id: str, resolved: bool = True, note: str = "",
                          designer_key: Optional[str] = None) -> bool:
        """关闭盲区（需设计者密钥，校验在 store 层）。"""
        if not resolved:
            from .governance import require_designer
            require_designer(designer_key, "盲区闭环")
            return False
        self.ng.store.registry.set_blindspot_status(blindspot_id, "resolved", designer_key)
        return True

    # ------------------------------------------------------------ 固化流水线
    def propose_promotion(self, node_id: str, requester: str, reason: str,
                          override_rejected_id: Optional[str] = None) -> str:
        """晋升提案（被否决过的同内容需显式 override）。"""
        return self.ng.propose_promotion(node_id, requester, reason, override_rejected_id)

    def verify_promotion(self, proposal_id: str, verified_by: str) -> None:
        """复核。"""
        self.ng.verify_promotion(proposal_id, verified_by)

    def adjudicate_promotion(self, proposal_id: str, adjudicated_by: str, approved: bool,
                             designer_key: Optional[str] = None) -> bool:
        """终裁（需密钥）。"""
        return self.ng.adjudicate_promotion(proposal_id, adjudicated_by, approved, designer_key) is not None

    def register_external_anchor(self, kind: str, content: str,
                                 condition_space: Optional[ConditionSpace] = None,
                                 designer_key: Optional[str] = None) -> Node:
        """外部锚点（接入前立场 / 自省记录 / 外部校准输入），上游 #109 的授权闸口径：
        无/错设计者密钥 ⇒ PermissionError（fail-closed，零落库，不静默降级到知识层）；
        密钥有效 ⇒ PRIMARY 写结构层（confidence=1.0、不可删），SUB 写知识层副本。"""
        from .governance import require_designer
        require_designer(designer_key, "外部锚点写入")
        if kind not in self.ANCHOR_KINDS:
            raise ValueError(f"未知锚点类型: {kind}")
        cs = condition_space or ConditionSpace(f"外部锚点:{kind}", "外部校准输入", (0.0, float("inf")),
                                               "方向性自检参照")
        text = f"[{kind}] {content}"
        if self.ng.store.policy.is_primary:
            return self._node(self.ng.add_shared(MemoryLayer.STRUCTURE, text, 0.9, cs).node_id)
        r = self.ng.perceive(text, modality="anchor", condition_space=cs, importance=0.9,
                             tags=["external_anchor", kind], skip_dedup=True, confidence=0.8, prefix="ext")
        return self._node(r.node_id)

    # ------------------------------------------------------------ 技能 / 负记忆
    def store_skill(self, name: str, description: str, procedure: str, confidence: float = 0.5) -> str:
        """登记技能。"""
        return self.ng.skills.add(name, description, procedure, confidence)

    def recall_skill(self, query: str, limit: int = 10) -> List[Dict]:
        """检索技能。"""
        return self.ng.skills.search(query, limit)

    def update_skill_confidence(self, skill_id: str, delta: float) -> None:
        """记成败（delta 符号）。"""
        self.ng.skills.adjust(skill_id, delta)

    def record_action_sequence(self, actions: List[str], outcome: str, success: bool,
                               skill_hint: Optional[str] = None) -> Optional[Node]:
        """操作序列闭环。"""
        return self._node(self.ng.record_action_sequence(actions, outcome, success, skill_hint).node_id)

    def register_rejected_path(self, path_type: str, description: str, reason: str, evidence: str = "") -> str:
        """登记负记忆。"""
        return self.ng.negative.record(path_type, description, reason, evidence)

    def list_rejected_paths(self, status: Optional[str] = None) -> List[Dict]:
        """列负记忆。"""
        return self.ng.negative.list(status)

    def find_rejected_paths(self, query: str, limit: int = 10) -> List[Dict]:
        """相似负记忆。"""
        return self.ng.negative.find(query, limit)

    def mark_rejected_path_consumed(self, rejected_id: str) -> None:
        """标记消费。"""
        self.ng.negative.consume(rejected_id)

    def consolidate_learning_result(self, record: Dict) -> Optional[Node]:
        """学习结果固化（知识层 + 实体链接）。"""
        if not record or not record.get("summary"):
            return None
        ents = list(record.get("entities", []))
        return self.add_perception(f"[learning] {record['summary']}", importance=0.8,
                                   tags=["learning_result"] + [f"ent:{e}" for e in ents], entities=ents)

    # ------------------------------------------------------------ 飞轮 / 事件
    def _note_reuse(self, node_ids: List[str]) -> None:
        """内部辅助函数。"""
        self.ng._note_reuse(node_ids)

    def notify_event(self, event_type: str, payload: Optional[Dict] = None) -> None:
        """事件标记（3 秒内同类合并）。"""
        t = now()
        for ev in self._event_queue:
            if ev["type"] == event_type and t - ev["ts"] < 3.0:
                ev["count"] += 1
                return
        self._event_queue.append({"type": event_type, "payload": payload or {}, "ts": t, "count": 1})

    def consume_events(self) -> Dict:
        """消费事件：先判生命周期暂停（暂停期间队列原样保留，恢复后再消费，#54），再取走清空。"""
        if self._lifecycle is not None and getattr(self._lifecycle, "state", None) == "paused":
            return {"status": "paused", "consumed": 0, "pending": len(self._event_queue),
                    "note": "P0 危机期间暂停非 P0 处理；事件保留至恢复"}
        n = len(self._event_queue)
        self._event_queue = []
        return {"status": "ok", "consumed": n, "pending": 0}

    # ------------------------------------------------------------ 视觉对照（身体层外接）
    def visual_check(self, reference: Optional[str] = None, threshold: float = 0.1,
                     remember: bool = True) -> dict:
        """预期（最近屏幕状态）vs 实际；对照结果回写为新的「过去」。"""
        body = self._body_registry
        if body is None:
            return {"status": "body_not_ready", "error": self._body_error}
        expected = reference or self._latest_screen()
        if not expected:
            shot = body.invoke("screen", "capture", {})
            if not shot.ok or not shot.data.get("path"):
                return {"status": "error", "error": shot.error or "截图失败"}
            if remember:
                self._remember_screen_state(shot.data["path"], "baseline 建立")
            return {"status": "ok", "established": True, "baseline": shot.data["path"],
                    "note": "无历史预期，已建立基线（下次可对照）"}
        diff = body.invoke("screen", "diff", {"reference": expected, "threshold": threshold})
        if not diff.ok:
            return {"status": "error", "error": diff.error}
        result = diff.to_dict()
        cur = body.invoke("screen", "capture", {})
        changed = result.get("data", {}).get("changed", False)
        if remember and cur.ok and cur.data.get("path"):
            self._remember_screen_state(cur.data["path"], f"对照{'有变化' if changed else '无变化'} "
                                        f"比例={result.get('data', {}).get('change_ratio')}", changed)
        return {"status": "ok", "expected": expected, "consistent": not changed, **result}

    def _latest_screen(self) -> Optional[str]:
        """内部辅助函数。"""
        nodes = self.ng.store.nodes.by_tag("screen_state", limit=None)
        for n in sorted(nodes, key=lambda n: (n.temporal_coordinate or 0.0, n.created_at or 0.0), reverse=True):
            m = _SCREEN_RE.search(n.content or "")
            if m and os.path.exists(m.group(1)):
                return m.group(1)
        return None

    def _remember_screen_state(self, image_path: str, note: str, changed: Optional[bool] = None) -> None:
        """内部辅助函数。"""
        text = f"[屏幕状态 {image_path}] {note}" + (f" 变化={changed}" if changed is not None else "")
        self.ng.perceive(text, importance=0.5, tags=["screen_state"], skip_dedup=True)

    def voice_session_log(self, turn: dict) -> str:
        """语音会话沉淀。"""
        text = (f"[语音会话] 用户: {str(turn.get('user', ''))[:80]} | "
                f"灵枢: {str(turn.get('assistant', ''))[:80]}")
        return self.ng.perceive(text, importance=0.5, tags=["voice_session", "conversation"]).node_id

    from .compat_engine_ops import (  # noqa: E402  维护/门控/交换/治理类方法
        _existing_tables, export_all, import_all, verify_integrity, decay_cycle, forget_advisor,
        consolidate_cycle, run_maintenance_cycle, start_auto_decay, stop_auto_decay, self_check,
        get_stats, close, longterm_snapshot, prefeed_input, promote_context_memories, _ensure_gate,
        induce_concepts, record_info_gap, get_gap_trend, record_resource_usage, get_resource_metrics,
        get_action_log, action_log_stats, get_verifier_config, propose_verifier_standard,
        review_verifier_standard, cs_review_verifier_standard, adjudicate_verifier_standard,
        list_verifier_standards, _seed_escalation_points, list_escalation_points, add_escalation_point,
        set_escalation_enabled, check_escalation, check_recursion_depth, get_entity_context, subgraph_replace,
        recursive_reflect, prepare_shared_sync, migrate_v17_coordinates)
