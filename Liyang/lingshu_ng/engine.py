# -*- coding: utf-8 -*-
"""engine · 薄编排层（MemoryEngine）

只做组合与调用顺序，不持有业务规则：层规则在 layers、去重在 dedup、衰减在 decay、
门控在 gate、负记忆在 negative……每个组件都可以单独构造和测试（依赖注入 = 构造参数）。

不变量：
  E1 无隐藏全局状态：除 ``session_id`` / ``round``（飞轮记账口径）外，所有状态都在库里。
  E2 每个公开写方法要么整体成功、要么整体回滚（组件内部事务 + 这里的外层 tx 嵌套）。
  E3 负记忆在提案 / 技能强化 / 召回三个入口统一经 :meth:`NegativeMemory.check` 查询。
  E4 写入回执的 layer 一律读回自库（WriteResult）。
"""
from __future__ import annotations

import copy
import math
import os
import uuid
from typing import Dict, List, Optional, Sequence, Tuple

from . import causal, conflict, dedup, exchange
from .decay import Maintenance, elapsed_factor
from .gate import LongTermGate
from .governance import require_designer
from .insight import Insights
from .layers import LayerPolicy, LayerViolation
from .negative import EXPERIENCE_IMPORTANCE, NegativeMemory
from .numeric import unit
from .retrieval import Retriever
from .scheduler import AutoDecay
from .semindex import SemanticIndex
from .self_model import SelfStore
from .skills import SkillBook
from .store import Store
from .types import (CausalChain, ConditionSpace, Edge, EdgeType, MemoryLayer, Node, Role,
                    WriteResult, now)

__all__ = ["MemoryEngine"]
_LAYER_DEFAULTS = {
    MemoryLayer.ANCHOR: ("anchor", "protocol", ["anchor"], ("协议初始化", "协议定义", "协议基底")),
    MemoryLayer.STRUCTURE: ("struct", "structure", ["structure"], ("结构定义", "协议架构", "协议结构")),
}


def _uid(prefix: str) -> str:
    # 与 uuid4().hex[:12] 同分布（uuid4 的版本/变体位在第 13 位之后）：48 位密码学随机、小写十六进制
    return f"{prefix}_{os.urandom(6).hex()}"


_AXES = ("x", "y", "z")


def spatial_dict(sp: object) -> Dict:
    """空间坐标规范成映射（上游 #279/#264 同族：旧接口允许向量坐标 ``[x, y, z]``，ng 直接 ``dict(list)`` 抛
    TypeError）。数值向量 → {x, y, z, d3, d4, …}；None/空 → {}；其它类型给出明确的 ValueError。
    轴名映射为本提交自拟（needs-owner-decision）。"""
    if sp is None:
        return {}
    if isinstance(sp, dict):
        return dict(sp)
    if isinstance(sp, (list, tuple)) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in sp):
        return {(_AXES[i] if i < 3 else f"d{i}"): float(v) for i, v in enumerate(sp)}
    raise ValueError(f"spatial_coordinates 须为映射或数值向量，收到 {type(sp).__name__}")


def same_condition(given: Optional[ConditionSpace], old: Optional[ConditionSpace]) -> bool:
    """M5 判同的条件一致性（上游 #268）。未显式给条件（写入用默认条件）时只比观测位置/工具/存在约束是否与
    默认三元组相同；显式给条件时三元组须相同且时间窗交叠。与 integrated-v3 149d21f 同口径（needs-owner-decision：
    不交叠时间窗即视为不同知识）。"""
    if old is None:
        return True
    ref = given or ConditionSpace.default("感知系统", "感官输入")
    if (ref.observation_position, ref.observation_tool, ref.existence_constraint) != \
            (old.observation_position, old.observation_tool, old.existence_constraint):
        return False
    if given is None:
        return True
    try:
        a0, a1 = float(given.time_window[0]), float(given.time_window[1])
        b0, b1 = float(old.time_window[0]), float(old.time_window[1])
    except (TypeError, ValueError, IndexError):
        return True
    return not (a1 < b0 or b1 < a0)


class MemoryEngine:
    """ng 原生引擎。``path=':memory:'`` 时为进程内私有库。"""

    def __init__(self, path: str = ":memory:", identity: str = "协议实例",
                 role: Role = Role.PRIMARY) -> None:
        self.store = Store(path, role)
        self.session_id = uuid.uuid4().hex[:8]
        self.round = 0
        self.dedup_threshold = self.approved_dedup_threshold()
        #: 写入期矛盾检测开关（去重路径写入时生效；见 :mod:`lingshu_ng.conflict`）
        self.auto_conflicts = True
        self.self_store = SelfStore(self.store, identity)
        self.retriever = Retriever(self.store, on_hit=self._note_reuse)
        self.maintenance = Maintenance(self.store)
        self.skills = SkillBook(self.store)
        self.negative = NegativeMemory(self.store)
        self.insights = Insights(self.store)
        self.gate = LongTermGate(self)
        self.autodecay = AutoDecay(self._auto_tick)
        #: 可选第二路召回（M1 语义检索提供者注入，见 :mod:`lingshu_ng.semindex`）；默认无
        self.semantic = None
        #: 环境变量启用提供者失败的原因（缺依赖/模型文件；S4：退回纯词面，不影响引擎构造）
        self.semantic_error: Optional[str] = None
        if os.environ.get("LINGSHU_NG_EMBED_MODEL", "").strip():
            try:
                from .embed import from_env
                self.set_embedding_provider(from_env())
            except Exception as e:  # 外部依赖件（onnxruntime 等）的异常类型不可枚举：记录后退回纯词面
                self.semantic_error = f"{type(e).__name__}: {e}"

    def set_embedding_provider(self, provider) -> None:
        """注入语义检索提供者（D-005 duck-typed：``add``+``search`` 或 ``encode``）；None 撤除。
        向量只是派生索引：写入照旧存原文、零 LLM，编码在后台线程或查询前补齐（semindex S1–S4）。"""
        if self.semantic is not None:
            self.semantic.close()
        self.semantic = SemanticIndex(self.store, provider) if provider is not None else None
        self.retriever.semantic = self.semantic

    def approved_dedup_threshold(self) -> float:
        """M5 阈值的持久事实源 = 终裁通过的最新 dedup_static 校验标准（无则默认值；#153 重启不失效）。"""
        rows = [r for r in self.store.registry.list_standards("approved") if r["param"] == "dedup_static"]
        if not rows:
            return dedup.DEFAULT_THRESHOLD
        last = max(rows, key=lambda r: (r["decided_at"] or 0.0, r["created_at"] or 0.0))
        return dedup.clamp_threshold(float(last["value"]))

    @property
    def policy(self) -> LayerPolicy:
        """当前角色的层守卫。"""
        return self.store.policy

    # ------------------------------------------------------------ 飞轮记账
    def _note_reuse(self, node_ids: List[str]) -> None:
        self.store.meta.note_reuse(self.session_id, self.round, node_ids)

    # ------------------------------------------------------------ 写入
    def perceive(self, content: str, modality: str = "text", spatial: Optional[Dict] = None,
                 condition_space: Optional[ConditionSpace] = None, importance: float = 0.5,
                 tags: Optional[Sequence[str]] = None, entities: Optional[Sequence[str]] = None,
                 skip_dedup: bool = False, layer: MemoryLayer = MemoryLayer.KNOWLEDGE,
                 confidence: float = 0.5, prefix: str = "node") -> WriteResult:
        """写一条记忆（默认知识层，M5 去重）。命中去重 ⇒ action=merged。"""
        self.round += 1
        imp, layer = unit(importance, "importance"), MemoryLayer.coerce(layer)
        tags, ents = list(tags or []), [str(e) for e in (entities or [])]
        with self.store.db.tx():
            if not skip_dedup:
                hit = self._find_duplicate(content, tags, modality, layer, condition_space)
                if hit is not None:
                    return self._merge(hit, tags, ents, imp)
            t = now()
            node = Node(id=_uid(prefix), content=content, modality=modality,
                        spatial_coordinates=spatial_dict(spatial), temporal_coordinate=t,
                        condition_space=condition_space or ConditionSpace.default("感知系统", "感官输入"),
                        importance=imp, confidence=unit(confidence, "confidence"), layer=layer,
                        tags=list(dict.fromkeys(tags + [f"ent:{e}" for e in ents])),
                        last_access=t, created_at=t)
            self.store.nodes.put(node, index_now=not skip_dedup)   # 去重路径写后即读索引：即时索引
            if not skip_dedup and self.auto_conflicts:
                self._auto_conflicts(node)
        if self.semantic is not None:
            self.semantic.note(node.id, content)
        return WriteResult(node.id, "created", layer.value)

    def _auto_conflicts(self, node: Node) -> List[Edge]:
        """写入期矛盾检测（conflict C1–C4）：与新节点构成同一事物矛盾的既有短记载登记 OPPOSITE 边。"""
        text = node.content
        if not isinstance(text, str) or not text or len(dedup.normalize(text)) > conflict.MAX_CHARS:
            return []
        use = set(LayerPolicy.layers(searchable=True))
        if node.layer not in use:
            return []
        ti = self.store.text
        grams = dedup.bigrams(text)
        probe = ti.last_probe
        dfs = probe[1] if probe is not None and probe[0] == grams else ti.df(grams)
        rare = conflict.rare_terms(dfs)
        if len(rare) < conflict.MIN_SHARED:
            return []
        cands = conflict.score_candidates(ti.postings_rows([t for _, t in rare]), dfs, len(grams))
        if not cands:
            return []
        ids = ti.node_ids(k for _, k in cands)
        nodes = self.store.nodes.get_many([ids[k] for _, k in cands if k in ids and ids[k] != node.id])
        out: List[Edge] = []
        for _, k in cands:
            old = nodes.get(ids.get(k))
            if old is None or old.layer not in use or old.modality != node.modality \
                    or not same_condition(node.condition_space, old.condition_space):
                continue
            v = conflict.classify(text, old.content or "")
            if v is None:
                continue
            try:
                out.append(self.link(node.id, old.id, EdgeType.OPPOSITE, confidence=conflict.AUTO_CONFIDENCE,
                                     condition_space=ConditionSpace.default("冲突检测", "写入期自动预筛"),
                                     evidence=conflict.AUTO_SUPERSEDE if v.supersede else conflict.AUTO_CONFLICT))
            except LayerViolation:
                continue
        return out

    def _find_duplicate(self, content: str, tags: List[str], modality: str,
                        layer: MemoryLayer, cs: Optional[ConditionSpace] = None) -> Optional[Node]:
        """精确内容键（无视野上限）→ 倒排前缀过滤出的同层近重复候选（无时间窗口）；签名必须相等，
        且条件空间一致（上游 #268，K=K(C)：同一句话在不同存在约束/观测位置/不交叠时间窗下是不同知识）。"""
        if not isinstance(content, str) or not dedup.normalize(content):
            return None
        sig = dedup.signature(content, tags, modality)
        for n in self.store.nodes.by_key(dedup.content_key(content), [layer]):
            if dedup.signature(n.content or "", n.tags, n.modality) == sig and same_condition(cs, n.condition_space):
                return n
        grams, size = dedup.bigrams(content), max(1, len(content))
        cands = self.store.text.near_duplicate_candidates(grams, self.dedup_threshold)
        for nid, text, _ in self.store.nodes.rows_newest_first(sorted(cands), layer):
            ratio = len(text or "") / size
            if ratio < self.dedup_threshold * 0.8 or ratio > 1.25 / self.dedup_threshold:
                continue                                  # Jaccard ≥ t 的必要条件（长度比，留余量）
            if dedup.jaccard(grams, dedup.bigrams(text or "")) < self.dedup_threshold:
                continue
            n = self.store.nodes.get(nid)
            if n and same_condition(cs, n.condition_space) and dedup.is_duplicate(content, sig, n.content or "",
                                        dedup.signature(n.content or "", n.tags, n.modality),
                                        self.dedup_threshold):
                return n
        return None

    def _merge(self, hit: Node, tags: List[str], ents: List[str], imp: float) -> WriteResult:
        sa = dict(hit.state_attributes or {})
        plan = dedup.merge_plan(hit.tags, hit.importance, tags, ents, imp, sa.get("merged_sources", []))
        fields: Dict = {"tags": list(plan.tags), "importance": plan.importance}
        if plan.merged_sources:
            sa["merged_sources"] = list(plan.merged_sources)
            fields["state_attributes"] = sa
        self.store.nodes.update(hit.id, **fields)
        self.store.nodes.touch([hit.id])
        return WriteResult(hit.id, "merged", hit.layer.value, "M5 去重合并")

    def add_context(self, content: str, importance: float = 0.4,
                    condition_space: Optional[ConditionSpace] = None,
                    tags: Optional[Sequence[str]] = None,
                    entities: Optional[Sequence[str]] = None) -> WriteResult:
        """写情境层（短期记忆，不去重），随后按持久化容量上限 FIFO 淘汰。"""
        cs = condition_space or ConditionSpace.default("情境感知", "会话摄入")
        with self.store.db.tx():               # 写入与 FIFO 淘汰同一事务（一次提交；上限从不被外部观察到越界）
            r = self.perceive(content, importance=importance, condition_space=cs,
                              tags=list(tags or []) + ["context"], entities=entities, skip_dedup=True,
                              layer=MemoryLayer.CONTEXT, prefix="ctx")
            self.maintenance.enforce_cap()
            layer = self.store.nodes.layer_of(r.node_id)
        return WriteResult(r.node_id, r.action, layer.value if layer else None)

    def add_shared(self, layer: MemoryLayer, content: str, importance: float,
                   condition_space: Optional[ConditionSpace] = None) -> WriteResult:
        """写锚点层/结构层（仅 PRIMARY；不可遗忘、不可删除）。"""
        prefix, modality, tags, (pos, tool, cons) = _LAYER_DEFAULTS[MemoryLayer.coerce(layer)]
        cs = condition_space or ConditionSpace(pos, tool, (0.0, math.inf), cons)
        return self.perceive(content, modality=modality, condition_space=cs, importance=importance,
                             tags=tags, skip_dedup=True, layer=layer, confidence=1.0, prefix=prefix)

    def link(self, source_id: str, target_id: str, relation: EdgeType = EdgeType.CAUSAL,
             confidence: float = 0.5, condition_space: Optional[ConditionSpace] = None,
             evidence: str = "extracted") -> Edge:
        """建边（守卫与端点存在性在仓储内保证）。"""
        e = Edge(id=_uid("edge"), source_id=source_id, target_id=target_id,
                 relation_type=EdgeType.coerce(relation),
                 condition_space=condition_space or ConditionSpace.default("关系建立", "语义分析"),
                 confidence=confidence, verified=False, source_evidence=evidence)
        self.store.edges.put(e)
        return e

    def protect(self, node_id: str, reason: str) -> bool:
        """不可遗忘保护（共享层需 PRIMARY）。"""
        return self.store.registry.protect(node_id, reason)

    def register_conflict(self, a_id: str, b_id: str) -> Optional[Edge]:
        """矛盾登记：OPPOSITE 边（不参与自然衰减）+ 两端 conflict 标签，同一事务。"""
        with self.store.db.tx():
            if self.store.nodes.get(a_id) is None or self.store.nodes.get(b_id) is None:
                return None
            e = self.link(a_id, b_id, EdgeType.OPPOSITE, confidence=0.3,
                          condition_space=ConditionSpace.default("冲突检测", "验证单元预筛选"))
            for nid in (a_id, b_id):
                self.store.nodes.add_tags(nid, ["conflict"])
        return e

    # ------------------------------------------------------------ 检索
    def search(self, query: str, layers: Optional[Sequence[MemoryLayer]] = None,
               limit: int = 20) -> List[Tuple[Node, float]]:
        """内容检索。"""
        return self.retriever.search(query, layers, limit)

    def recall(self, query: str, limit: int = 10) -> Dict:
        """组合召回 + 负记忆提示（E3）。"""
        return {"hits": self.retriever.recall(query, limit),
                "negative": self.negative.check(None, query)}

    # ------------------------------------------------------------ 因果
    def _adjacency(self, types: Optional[Sequence[str]]):
        arcs = [(i, s, t) for i, s, t, _, _ in self.store.edges.topology(types)]
        return causal.build_adjacency(arcs)

    def reason_causal(self, start_id: str, end_id: Optional[str] = None, max_depth: int = 5,
                      relation_types: Optional[Sequence[str]] = None) -> List[CausalChain]:
        """因果链（带 truncated/cyclic 标记）或 start→end 路径。元素为 Edge 对象。"""
        adj, _ = self._adjacency(relation_types or ["causal"])
        if end_id:
            raw = [(p, "end") for p in causal.paths_between(adj, start_id, end_id, max_depth)]
        else:
            raw = causal.chains(adj, start_id, max_depth)
        edges = self.store.edges.get_many([e for p, _ in raw for e in p])
        return [CausalChain([edges[e] for e in p], truncated=k == "truncated", cyclic=k == "cyclic")
                for p, k in raw]

    def find_cycles(self, max_len: Optional[int] = None, max_cycles: Optional[int] = 10000,
                    types: Sequence[str] = ("causal", "cyclic"),
                    max_steps: Optional[int] = None) -> causal.CycleScan:
        """环枚举（边 id 序列）。"""
        db = self.store.db
        with db.lock:                            # 两次读（判环 / 取 id）在同一读快照内，看到同一边集
            snap = not db.conn.in_transaction
            if snap:
                db.conn.execute("BEGIN")
            try:
                return causal.scan_lazy(self.store.edges.pair_columns(types), lambda: self.store.edges.arcs(types),
                                        max_len, max_cycles, max_steps)
            finally:
                if snap:
                    db.conn.execute("COMMIT")

    def has_cycle(self, types: Sequence[str] = ("causal", "cyclic")) -> bool:
        """是否存在因果环（SCC 判定，与深度无关）。"""
        return causal.has_cycle_columns(*self.store.edges.pair_columns(types))

    def self_check(self, cycle_budget: int = 256, step_budget: int = 200_000) -> Dict:
        """自检：各层计数、SELF 持久化、因果环（SCC 精确判定 + 环数/步数双上限的枚举明细）。

        增量化：结果只取决于库内容，按提交指纹（:meth:`Database.fingerprint`）记忆——库自上次自检后
        没有任何提交/改动时直接复用（每次返回新副本与新时间戳），任何写入后下一次自检整体重算。"""
        fp = (self.store.db.fingerprint(), cycle_budget, step_budget)
        memo = getattr(self, "_self_check_memo", None)
        if memo is None or memo[0] != fp:
            memo = self._self_check_memo = (fp, self._self_check(cycle_budget, step_budget))
        r = copy.deepcopy(memo[1])
        r["timestamp"] = now()
        return r

    def _self_check(self, cycle_budget: int, step_budget: int) -> Dict:
        n = self.store.nodes
        scan = self.find_cycles(max_cycles=cycle_budget, max_steps=step_budget)
        return {"anchor_count": n.count(MemoryLayer.ANCHOR), "structure_count": n.count(MemoryLayer.STRUCTURE),
                "self_ok": self.self_store.persisted, "context_count": n.count(MemoryLayer.CONTEXT),
                "open_blindspots": len(self.store.registry.list_blindspots("open")),
                "skills_count": self.skills.count(), "has_cycle": scan.components > 0,
                "cyclic_components": scan.components, "cycles_found": len(scan.cycles),
                "cycles_truncated": scan.truncated, "cycle_details": scan.cycles[:5],
                # 旧 find_cycles(max_depth=8) 看不见的长环（环长 > 9）是否存在（上游 #215 的一致性口径）
                "cycles_beyond_depth": any(len(c) > 9 for c in scan.cycles), "timestamp": now()}

    # ------------------------------------------------------------ 固化流水线（D-003）
    def propose_promotion(self, node_id: str, requester: str, reason: str,
                          override_rejected_id: Optional[str] = None) -> str:
        """提案：共享层不可再提升；被否决过的同内容提案需显式 override（E3）。"""
        node = self.store.nodes.get(node_id)
        if node is None:
            raise ValueError("节点不存在")
        if LayerPolicy.rule(node.layer).shared or node.layer == MemoryLayer.SELF:
            raise ValueError("共享层/自我层节点不可再提升")
        prior = self.negative.check("promotion", node.content or "", fuzzy=False)
        if prior and override_rejected_id not in {p["id"] for p in prior}:
            raise PermissionError(f"同内容提案已被否决（{prior[0]['id']}），需 override_rejected_id 显式重提")
        if prior:                             # 显式越过否决记录：理由里留审计痕（上游 #216）
            reason = f"{reason} [override_rejected:{override_rejected_id}]"
        with self.store.db.tx():
            pid = self.store.registry.add_proposal(node_id, requester, reason, node.content or "")
            self.store.nodes.add_tags(node_id, ["promotion_pending"])
        return pid

    def verify_promotion(self, proposal_id: str, verified_by: str) -> bool:
        """复核（复核人≠提案人、内容未被改写）。"""
        p = self.store.registry.proposal(proposal_id)
        node = self.store.nodes.get(p["node_id"]) if p else None
        return bool(node) and self.store.registry.verify_proposal(proposal_id, verified_by, node.content or "")

    def adjudicate_promotion(self, proposal_id: str, by: str, approved: bool,
                             designer_key: Optional[str] = None) -> Optional[str]:
        """终裁：通过 ⇒ 写结构层；否决 ⇒ 记负记忆。返回节点 id（未裁决返回 None）。"""
        require_designer(designer_key, "晋升终裁")
        p = self.store.registry.proposal(proposal_id)
        node = self.store.nodes.get(p["node_id"]) if p else None
        if node is None:
            return None
        with self.store.db.tx():
            d = self.store.registry.decide_proposal(proposal_id, by, approved, designer_key, node.content or "")
            if d is None:
                return None
            self.store.nodes.remove_tags(node.id, ["promotion_pending"])
            if approved:
                self.store.nodes.update(node.id, allow_transition=True, layer=MemoryLayer.STRUCTURE,
                                        confidence=1.0)
            else:
                self.negative.record("promotion", f"固化提案被拒：{(node.content or '')[:60]}",
                                     f"维生系统终裁拒绝（{by}）", subject=node.content or "")
        return node.id

    # ------------------------------------------------------------ 技能闭环（P1-3）
    def record_action_sequence(self, actions: Sequence[str], outcome: str, success: bool,
                               skill_hint: Optional[str] = None) -> WriteResult:
        """记录操作序列：成败同价入库；成功强化技能（负记忆把关）、失败记负记忆并降信。"""
        steps = " > ".join(list(actions)[:5])
        tags = ["action_sequence", "success" if success else "failure"] + \
            ([f"hint:{skill_hint}"] if skill_hint else [])
        r = self.perceive(f"[action_seq] {'成功' if success else '失败'}：{steps}（{outcome[:40]}）",
                          importance=EXPERIENCE_IMPORTANCE, tags=tags)
        skill = self.skills.by_name(skill_hint) if skill_hint else None
        if success and skill_hint:
            if skill is None:
                sid = self.skills.add(skill_hint, f"从操作序列提取（{outcome[:40]}）", steps)
                # #216 ①：首次成功前的失败（带同名 hint 或同一操作序列）都计入技能成败账
                prior = self.negative.failures_of(skill_hint)
                if steps != skill_hint:
                    prior += self.negative.failures_of(steps)
                self.skills.seed_failures(sid, prior)
            else:
                sid = skill["id"]
                if skill["failures"] <= skill["successes"] + 2:       # 失败主导时不追加程序
                    self.skills.append_procedure(sid, " > ".join(list(actions)[:3]))
            self.skills.record_outcome(sid, True)
        elif not success:
            self.negative.record("action_sequence", f"操作序列失败：{steps}", f"outcome: {outcome[:60]}",
                                 subject=skill_hint or steps)
            if skill:
                self.skills.record_outcome(skill["id"], False)
        return r

    # ------------------------------------------------------------ 维护
    def decay_step(self, factor: float = 0.02, min_confidence: float = 0.1) -> Dict[str, int]:
        """一步衰减。"""
        return self.maintenance.step(factor, min_confidence)

    def _auto_tick(self, elapsed: float) -> None:
        self.decay_step(elapsed_factor(0.02, elapsed, 60.0))

    def run_maintenance(self, factor: float = 0.02, promote=None) -> Dict:
        """睡眠巩固：提升 → 巩固 → 衰减 → 主动遗忘（确定性顺序）。``promote`` 可替换提升入口（兼容门面
        经旧接口 ``_ensure_gate().promote_from_context`` 走同一门控）。"""
        promoted = (promote or self.gate.promote_from_context)(limit=None)
        cons = self.maintenance.consolidate()
        dec = self.decay_step(factor)
        forget = self.maintenance.forget_advisor()
        # 巩固统计进行为日志（不写伪记忆节点）；类型名与旧 consolidate_cycle 一致（上游 #263）
        self.store.meta.log_action("consolidation", f"maintenance promoted={len(promoted)}", outcome={**cons, **dec})
        return {"promoted": len(promoted), "consolidation": cons, "decay": dec, "forget": forget}

    # ------------------------------------------------------------ 盲区 / 自我 / 交换
    def register_blindspot(self, code: str, description: str, severity: str = "medium",
                           category: str = "operational", predictability: str = "pending_assessment") -> str:
        """登记操作层盲区；元盲区零记录（拒绝写入）。"""
        if category == "meta":
            raise ValueError("元盲区（对人类造成文明级别的重大负面影响）零记录，拒绝写入")
        return self.store.registry.add_blindspot(code, description, severity, "operational", predictability)

    def export_all(self, path: str) -> Dict:
        """全库导出。"""
        return exchange.export_all(self.store, path)

    def import_all(self, path: str, designer_key: Optional[str] = None) -> Dict:
        """全库导入（受保护数据需密钥）。"""
        return exchange.import_all(self.store, path, designer_key)

    def close(self) -> None:
        """停止后台线程（join）后关闭库。"""
        self.autodecay.stop()
        if self.semantic is not None:
            self.semantic.close()
        self.store.close()
