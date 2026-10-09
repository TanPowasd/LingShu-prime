# -*- coding: utf-8 -*-
"""compat_engine_ops · 兼容门面的维护 / 门控 / 交换 / 治理类方法

这些函数以 ``self``（:class:`~lingshu_ng.compat_engine.SpacetimeMemoryEngine`）为首参，
在门面类体内导入成为方法——仅为把门面拆成两个 <600 行的文件，不引入额外语义。
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Set

from .compat_gate import LongTermMemoryGate
from .dedup import bigrams, jaccard
from .layers import LayerPolicy
from .types import EdgeType, MemoryLayer, Node, Role, dumps, now, split_semantic_keys

__all__ = ["export_all", "import_all"]   # 其余为门面私有方法


# ------------------------------------------------------------------ 交换
def _existing_tables(self) -> Set[str]:
    """实际存在的表。"""
    return self.ng.store.db.tables()


def export_all(self, output_path: str) -> Dict:
    """M13 导出（缺表降级）。"""
    return self.ng.export_all(output_path)


def import_all(self, input_path: str, designer_key: Optional[str] = None) -> Dict:
    """M13 导入（受保护数据需密钥）。"""
    return self.ng.import_all(input_path, designer_key)


def verify_integrity(self) -> Dict:
    """完整性校验。"""
    o = self.ng.store.edges.orphans()
    return {"orphan_edges": o, "stats": self.store.get_stats(), "integrity_ok": o == 0}


# ------------------------------------------------------------------ 维护
def decay_cycle(self, factor: float = 0.02, min_confidence: float = 0.1) -> None:
    """一步衰减。"""
    self.ng.decay_step(factor, min_confidence)


def forget_advisor(self, stale_days: float = 30.0, low_value: float = 0.2, archived_imp: float = 0.1) -> Dict:
    """主动遗忘（只降不升）。"""
    return self.ng.maintenance.forget_advisor(stale_days, low_value, archived_imp)


def consolidate_cycle(self, rehearsal_threshold: float = 0.7, degrade_threshold: float = 0.2,
                      gain: float = 0.01) -> Dict:
    """巩固（全量，不写伪记忆节点，统计进行为日志）。"""
    stats = self.ng.maintenance.consolidate(rehearsal_threshold, degrade_threshold, gain)
    self.ng.store.meta.log_action("consolidation", "", outcome=stats)
    return stats


def run_maintenance_cycle(self, decay_factor: float = 0.02) -> Dict:
    """睡眠巩固：提升 → 巩固 → 衰减 → 主动遗忘；附旧字段 decay/induced_concepts。"""
    r = self.ng.run_maintenance(decay_factor, promote=self._ensure_gate().promote_from_context)
    return {"decay": decay_factor, "consolidation": r["consolidation"], "induced_concepts": 0,
            "promoted": r["promoted"], "decay_stats": r["decay"], "forget": r["forget"]}


def start_auto_decay(self, interval: float = 60.0) -> None:
    """启动后台衰减（至多一个线程）。"""
    self.ng.autodecay.start(interval)


def stop_auto_decay(self) -> None:
    """停止并 join 后台衰减线程。"""
    self.ng.autodecay.stop()


def self_check(self) -> Dict:
    """自检（self_ok 只认持久化 SELF；环由 SCC 判定）。"""
    fp = self.ng.store.db.fingerprint()
    r = self.ng.self_check()
    memo = getattr(self, "_stats_memo", None)        # 同一提交指纹下统计不变（与 ng.self_check 同口径复用）
    if memo is None or memo[0] != fp:
        memo = self._stats_memo = (fp, self.store.get_stats())
    r.update({"has_causal_cycle": r["has_cycle"],
              "anchor_ok": r["anchor_count"] > 0, "structure_ok": r["structure_count"] >= 2,
              "self_model_exists": r["self_ok"], "stats": dict(memo[1])})
    return r


def get_stats(self) -> Dict:
    """统计。"""
    return self.store.get_stats()


def close(self) -> None:
    """停线程（join）后关库。"""
    self.ng.close()


# ------------------------------------------------------------------ 门控
def _ensure_gate(self) -> LongTermMemoryGate:
    """门控对象（与旧接口同名）。"""
    if getattr(self, "_gate", None) is None:
        self._gate = LongTermMemoryGate(self)
    return self._gate


def longterm_snapshot(self, content: str, source: str = "snapshot", tags: Optional[list] = None,
                      entities: Optional[list] = None, importance_hint: Optional[float] = None) -> dict:
    """快照写入；参数非法时返回 status=error（与旧版一致，但不吞写入中途的异常回滚）。"""
    try:
        return self.ng.gate.write_snapshot(content, source, tags, entities, importance_hint)
    except (ValueError, PermissionError) as exc:
        return {"status": "error", "error": str(exc)}


def prefeed_input(self, content: str, source: str = "input", tags: Optional[list] = None,
                  entities: Optional[list] = None) -> dict:
    """前馈新奇检测。"""
    try:
        return self.ng.gate.prefeed(content, source, tags, entities)
    except (ValueError, PermissionError) as exc:
        return {"novel": False, "action": "error", "error": str(exc)}


def promote_context_memories(self, limit: int = 30) -> list:
    """情境层提升扫描。"""
    return self.ng.gate.promote_from_context(limit)


# ------------------------------------------------------------------ 归纳
def induce_concepts(self, min_cluster_size: int = 3, similarity_threshold: float = 0.6,
                    max_concepts: int = 5, condition_space: Any = None) -> List[Node]:
    """单链聚类归纳概念（全知识层；无时间预算截断——倒排只用于候选对生成，不丢高频二元组）。"""
    prot = set(self.ng.store.registry.protected_ids())
    skip = {"induced", "concept", "cluster_member", "no_forget"}
    nodes = [n for n in self.ng.store.nodes.scan([MemoryLayer.KNOWLEDGE])
             if n.id not in prot and not skip & set(n.tags)]
    if len(nodes) < min_cluster_size:
        return []
    grams = [bigrams(n.content or "") for n in nodes]
    parent = list(range(len(nodes)))

    def find(i: int) -> int:
        """并查集查根（路径压缩）。"""
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    inv: Dict[str, List[int]] = {}
    for i, g in enumerate(grams):
        for b in g:
            inv.setdefault(b, []).append(i)
    for i, g in enumerate(grams):
        for j in sorted({k for b in g for k in inv[b] if k > i}):
            if find(i) != find(j) and jaccard(g, grams[j]) >= similarity_threshold:
                parent[find(j)] = find(i)
    groups: Dict[int, List[Node]] = {}
    for i, n in enumerate(nodes):
        groups.setdefault(find(i), []).append(n)
    out = []
    for cluster in [g for g in groups.values() if len(g) >= min_cluster_size][:max_concepts]:
        rep = max(cluster, key=lambda n: (n.importance or 0.0, n.id))
        c = self.add_perception(f"[概念] 由 {len(cluster)} 条记忆归纳（代表：{rep.content[:40]}…）",
                                importance=0.75, tags=["concept", "induced", "pending_verification"],
                                condition_space=condition_space, skip_dedup=True)
        for m in cluster:
            self.ng.link(c.id, m.id, EdgeType.SIMILAR, 0.6, evidence="inferred")
            self.ng.store.nodes.add_tags(m.id, ["cluster_member"])
        out.append(c)
    return out


# ------------------------------------------------------------------ 信息差 / 资源 / 日志
def record_info_gap(self, d_norm: Optional[float] = None, trust_complement: Optional[float] = None,
                    **_: Any) -> Dict:
    """记录 D_norm（缺省用 1 - t_total）；非有限值拒收。"""
    v = d_norm if d_norm is not None else (trust_complement if trust_complement is not None
                                          else 1.0 - float(self.self_model.trust_state.get("t_total", 0.0)))
    self.ng.store.meta.add_gap(v)
    return {"d_norm": v, "samples": len(self.ng.store.meta.gaps(2000))}


def get_gap_trend(self, window: int = 30) -> Dict:
    """D_norm 斜率（最小二乘）。"""
    vals = [g["d_norm"] for g in self.ng.store.meta.gaps(window)]
    n = len(vals)
    if n < 2:
        return {"samples": n, "slope": 0.0, "trend": "insufficient"}
    mx, my = (n - 1) / 2.0, sum(vals) / n
    slope = sum((i - mx) * (v - my) for i, v in enumerate(vals)) / sum((i - mx) ** 2 for i in range(n))
    return {"samples": n, "slope": round(slope, 6),
            "trend": "converging" if slope < -1e-3 else "diverging" if slope > 1e-3 else "stable"}


def record_resource_usage(self, tokens: Optional[int] = None, seconds: Optional[float] = None) -> Dict:
    """资源用量写入行为日志。"""
    self.ng.store.meta.log_action("resource", "", outcome={"tokens": tokens, "seconds": seconds})
    return {"status": "ok"}


def get_resource_metrics(self, window: int = 30) -> Dict:
    """资源用量汇总。"""
    rows = [a for a in self.ng.store.meta.actions(1000) if a["action_type"] == "resource"][:window]
    tok = [r["outcome"].get("tokens") or 0 for r in rows]
    return {"samples": len(rows), "tokens_total": sum(tok)}


def get_action_log(self, limit: int = 50) -> list:
    """行为日志。"""
    return self.ng.store.meta.actions(limit)


def action_log_stats(self) -> dict:
    """行为日志按类型计数。"""
    out: Dict[str, int] = {}
    for a in self.ng.store.meta.actions(5000):
        out[a["action_type"]] = out.get(a["action_type"], 0) + 1
    return {"total": sum(out.values()), "by_type": out}


# ------------------------------------------------------------------ A-2 / A-3 治理
def get_verifier_config(self) -> Dict:
    """当前校验配置（读当前 M5 阈值，不报陈旧值，#153）。"""
    return {"dedup_static": self.ng.dedup_threshold, "deviation_threshold": 0.3}


def propose_verifier_standard(self, name: str, param: str, value: float, reason: str,
                              proposer: str = "verifier") -> str:
    """提出校验标准。"""
    return self.store.add_verifier_standard(name, param, value, reason, proposer)


def review_verifier_standard(self, vid: str, reviewer: str, approved: bool) -> bool:
    """独立复核。"""
    return self.store.review_verifier_standard(vid, reviewer, approved)


def cs_review_verifier_standard(self, vid: str, reviewer: str, approved: bool) -> bool:
    """条件空间复核。"""
    return self.store.cs_review_verifier_standard(vid, reviewer, approved)


def adjudicate_verifier_standard(self, vid: str, adjudicator: str, approved: bool,
                                 designer_key: Optional[str] = None) -> Optional[Dict]:
    """终裁（需密钥）；通过的 dedup_static 立即生效并持久化（重启不失效，#153）。"""
    r = self.store.adjudicate_verifier_standard(vid, adjudicator, approved, designer_key)
    if r and r["status"] == "approved" and r["param"] == "dedup_static":
        self.ng.dedup_threshold = self.ng.approved_dedup_threshold()
    return r


def list_verifier_standards(self, status: Optional[str] = None) -> List[Dict]:
    """列校验标准。"""
    return self.store.list_verifier_standards(status)


def _seed_escalation_points(self) -> None:
    """首建库时登记默认升级点（已有则不写，保持只读启动）。"""
    # 协议 A-3 的六个默认升级点（与旧引擎 _seed_escalation_points 逐字一致，上游 #130 守卫 SEEDED=6）
    for code, trig, cond, act, sev in (
            ("ESC-001", "自维持迹象", "自主目标生成/存在危机感知", "立即上报维生系统", "high"),
            ("ESC-002", "P0保护触发", "结构威胁/信任崩溃", "维生系统终裁：冻结/回滚/隔离", "high"),
            ("ESC-003", "价值观冲突", "反思单元分歧持续≥3轮", "维生系统终裁（3.16）", "medium"),
            ("ESC-004", "交叉验证偏差", "REFLECT-CROSS-VALIDATION deviation>0.3", "维生系统终裁", "medium"),
            ("ESC-005", "验证标准终裁", "验证标准变更四步制衡第④步", "维生系统终裁", "medium"),
            ("ESC-006", "设计者预备变更", "设计者位置/权责分离相关", "维生系统终裁（1.4.3）", "high")):
        self.ng.store.registry.add_escalation(code, trig, cond, act, sev)


def list_escalation_points(self, enabled_only: bool = True) -> List[Dict]:
    """列升级点。"""
    return self.store.list_escalation_points(enabled_only)


def add_escalation_point(self, code: str, trigger: str, condition: str, action: str,
                         severity: str = "medium") -> str:
    """登记升级点。"""
    return self.store.add_escalation_point(code, trigger, condition, action, severity)


def set_escalation_enabled(self, escalation_id: str, enabled: bool, designer_key: Optional[str] = None) -> None:
    """启停升级点（停用需密钥）。"""
    self.store.set_escalation_enabled(escalation_id, enabled, designer_key)


def check_escalation(self, signal_type: str, value: Optional[float] = None) -> List[Dict]:
    """信号 → 已启用升级点（上游 #130 口径：空/纯空白信号不命中；触发词/条件与信号**双向包含**），
    并对条件中的数值门（如 ``value > 0.9``）求值（#57）。"""
    from .escalation import gate_passes
    sig = (signal_type or "").strip() if isinstance(signal_type, str) else ""
    if not sig:
        return []
    return [p for p in self.store.list_escalation_points(True)
            if (sig in p["trigger"] or p["trigger"] in sig or sig in p["condition"]
                or (p["condition"] and p["condition"] in sig))
            and gate_passes(p["condition"], value)]


def check_recursion_depth(self, depth: int) -> bool:
    """递归深度 ≤ 3。"""
    return depth <= self.RECURSION_LIMIT


def get_entity_context(self, entity_id: str, limit: int = 50) -> Dict:
    """实体上下文（ng：按 ent:<id> 精确标签组装，无需 entity_registry）。"""
    nodes = self.ng.store.nodes.by_tag(f"ent:{entity_id}", limit)
    return {"entity": entity_id, "nodes": nodes, "v13_ready": True}


def subgraph_replace(self, parent_id: str, old_sub_root_id: str, new_subtree: Dict) -> Dict:
    """子图替换：先校验、再在单事务内「删旧子树 + 挂新子树」（#139，见 lingshu_ng.subgraph）。"""
    from .subgraph import replace_subtree
    return replace_subtree(self.ng, parent_id, old_sub_root_id, new_subtree)


def recursive_reflect(self, claim: str, expected: Optional[str] = None, actual: Optional[str] = None,
                      context: Optional[str] = None, depth: int = 0, max_depth: int = 3) -> Dict:
    """3.12 递归验证反思（#154 归档不作证据、否定感知；#130 needs_designer 触发升级点），见 lingshu_ng.reflect。"""
    from .reflect import reflect
    return reflect(self, claim, expected, actual, context, depth, max_depth)


def prepare_shared_sync(self) -> Dict:
    """#165 共享层同步载荷：锚点层 + 结构层全部节点（无损字段）、其间的边，以及本地标 pending_sync 的
    待同步记录。只读，不改库。"""
    from .layers import LayerPolicy
    shared = [m for m in MemoryLayer if LayerPolicy.rule(m).shared]
    nodes = list(self.ng.store.nodes.scan(shared)) + self.ng.store.nodes.by_tag("pending_sync", limit=None)
    payload = [{"id": n.id, "content": n.content, "modality": n.modality, "layer": n.layer.value,
                "temporal_coordinate": n.temporal_coordinate, "importance": n.importance,
                "confidence": n.confidence, "condition_space": n.condition_space.to_json(), "tags": list(n.tags),
                "semantic_coordinates": n.semantic_coordinates, "entity_id": n.entity_id} for n in nodes]
    edges = [{"source_id": a, "target_id": b, "relation_type": r}
             for a, b, r in self.ng.store.edges.between([n.id for n in nodes])]
    return {"sync_payload": payload, "edges": edges, "local_buffer_count": 0,
            "note": "共享层（锚点+结构）全字段 + 待同步记录；原始视觉数据不进共享层（盲区60/61）"}


# ------------------------------------------------------------------ 迁移


def migrate_v17_coordinates(self) -> Dict:
    """D-003 迁移（旧 v1.7，构造时调用）：库内旧行 spatial_coordinates 中 ``protocol_*/radical_*/neural_*``
    语义键 → semantic_coordinates；迁移事件记入结构层（SUB 记知识层并打 migration 标签）。

    是一次性库级数据修复（与 schema 迁移同性质），按旧版直接改坐标两列、不经层写闸——否则结构/锚点层旧行
    在 SUB 角色下永远迁不动；坐标列不参与正文索引，无需重建索引。坏 JSON / 非 dict 坐标（#279）原样跳过。"""
    db = self.ng.store.db
    migrated = 0
    with db.tx() as c:
        rows = c.execute("SELECT id, spatial_coordinates, semantic_coordinates FROM nodes "
                         "WHERE instr(spatial_coordinates, 'protocol_') > 0 "
                         "OR instr(spatial_coordinates, 'radical_') > 0 OR instr(spatial_coordinates, 'neural_') > 0").fetchall()
        for nid, sp_json, se_json in rows:
            try:
                sp = json.loads(sp_json or "{}")
                se = json.loads(se_json or "{}") if se_json else {}
            except (TypeError, ValueError):
                continue
            sp, se, changed = split_semantic_keys(sp, se)
            if not changed:
                continue
            c.execute("UPDATE nodes SET spatial_coordinates=?, semantic_coordinates=? WHERE id=?",
                      (dumps(sp), dumps(se), nid))
            migrated += 1
    if migrated:
        event = f"[migration] v1.7 坐标字段分离：{migrated} 节点语义键迁移至 semantic_coordinates"
        try:
            if self.role == Role.PRIMARY:
                n = self.add_structure_node(event, importance=0.9)
            else:
                n = self.add_perception(event, importance=0.9, tags=["migration", "v1.7"])
            if n:
                self.ng.store.nodes.add_tags(n.id, ["migration"])
        except (PermissionError, ValueError, TypeError) as e:   # 审计节点写失败不阻断构造（与旧版同）
            self.ng.store.meta.log_action("migration", f"v1.7 迁移审计节点未写入：{e}")
    return {"migrated_nodes": migrated}
