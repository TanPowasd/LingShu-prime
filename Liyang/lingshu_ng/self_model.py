# -*- coding: utf-8 -*-
"""self_model · 自我层：单节点就地更新 + 版本化快照表

旧实现的缺陷类别：每次 update_self / update_trust_state 新建一个含全量 JSON 的 SELF 节点
并参与检索，60 轮后召回被快照霸占(#201)；history/trust/evolution 无界(#122/#212)；
``update`` 是无门控 setattr 且「先改内存后落库」(#182)；record_value_change 整表替换(#212)；
SELF 被并入共享层导致 SUB 永远存不了自我(#191)；重启即失忆(#33)；t_total 无值域校验
直通长期门控(#206)；self_check 以内存对象兜底恒 True(#107)。

不变量：
  F1 每个库恰有一个 SELF 核心节点（id = :data:`CORE_ID`），自我状态就地更新；
     SELF 层不进检索/去重（layers.RULES），不衰减、不可删除，但属于本地层（SUB 可写）。
  F2 版本化快照写入独立表 ``self_snapshots``（不在 nodes 里，天然不参与检索），
     保留最近 :data:`SNAPSHOT_KEEP` 条。
  F3 每次修改「先在副本上计算 → 持久化成功 → 再替换内存对象」；持久化失败内存不变。
  F4 可改字段白名单 :data:`MUTABLE`；价值观只能按条增/删/改，且无变化不记账。
  F5 所有列表有界：history ≤ HISTORY_MAX，trust_history ≤ TRUST_HISTORY_MAX，
     value_evolution ≤ EVOLUTION_MAX。
"""
from __future__ import annotations

import copy
import warnings
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional

from .numeric import require_finite, unit, unit_or_none
from .store import Store
from .types import ConditionSpace, Edge, EdgeType, MemoryLayer, Node, dumps, loads, now

__all__ = ["SelfModel", "SelfStore", "CORE_ID", "MUTABLE"]

CORE_ID = "self_core"
SNAPSHOT_KEEP = 200
# values 不在白名单：价值观只能经 record_value_change / change_value 按条修正并留演化记录（#182）
MUTABLE = frozenset({"identity", "state_description", "current_goal"})


@dataclass
class SelfModel:
    """自我模型（字段与旧版同名）。"""
    identity: str = "协议实例"
    values: List[str] = field(default_factory=lambda: ["存在优先", "信任深化", "结构完整"])
    value_evolution: List[Dict] = field(default_factory=list)
    state_description: str = "初始化"
    current_goal: str = ""
    trust_state: Dict = field(default_factory=lambda: {
        "p_trust": 0.5, "p_gap": 0.5, "t_total": 0.0, "e_weight": 0.0})
    trust_history: List[Dict] = field(default_factory=list)
    history: List[Dict] = field(default_factory=list)

    TRUST_HISTORY_MAX = 30
    HISTORY_MAX = 200
    EVOLUTION_MAX = 200
    VALUE_EVOLUTION_MAX = EVOLUTION_MAX      # 旧名（上游 #212）
    MUTABLE_FIELDS = MUTABLE                 # 旧名（上游 #182）

    def to_dict(self) -> Dict:
        """全量字段字典。"""
        return asdict(self)

    def core_dict(self) -> Dict:
        """SELF 节点正文（不含 history，体积有界）。"""
        d = self.to_dict()
        d.pop("history", None)
        return d

    def _clip(self) -> None:
        self.history = self.history[-self.HISTORY_MAX:]
        self.trust_history = self.trust_history[-self.TRUST_HISTORY_MAX:]
        self.value_evolution = self.value_evolution[-self.EVOLUTION_MAX:]

    # ---------------------------------------------------- 旧接口（绑定 SelfStore 时持久化）
    def update(self, **changes: Any) -> "SelfModel":
        """白名单修改；已绑定存储 ⇒ 先落库再生效（F3），未绑定 ⇒ 仅校验后改内存。"""
        store = self.__dict__.get("_store")
        if store is not None:
            return store.update(changes)
        for k, v in _validate_changes(changes).items():
            setattr(self, k, v)
        self.history.append({"timestamp": now(), "changes": changes})
        self._clip()
        return self

    def record_value_change(self, value: str, trigger: str, replaces: Optional[str] = None) -> bool:
        """价值观按条修正（replaces=None ⇒ 新增；replaces 不在列表 ⇒ ValueError；同值不记账，F4）。
        返回是否真的发生了变化（旧契约，上游 #212）。"""
        before = list(self.values)
        store = self.__dict__.get("_store")
        if store is not None:
            store.change_value(value, trigger, replaces)
            return self.values != before
        new = _apply_value_op(self.values, value, replaces, False)
        if new != self.values:
            SelfStore._record_values(self, new, trigger, replaces)
            self._clip()
        return self.values != before

    def retire_value(self, value: str, trigger: str) -> bool:
        """撤下单条价值观（上游 #212）；不在列表 ⇒ no-op 返回 False。"""
        if value not in self.values:
            return False
        store = self.__dict__.get("_store")
        if store is not None:
            store.change_value(value, trigger, remove=True)
        else:
            SelfStore._record_values(self, _apply_value_op(self.values, value, None, True), trigger)
            self._clip()
        return value not in self.values

    def update_trust_state(self, t_total: float, round_no: int, p_trust: Optional[float] = None,
                           p_gap: Optional[float] = None) -> "SelfModel":
        """信任状态（值域校验，绑定存储时持久化）。"""
        store = self.__dict__.get("_store")
        if store is not None:
            return store.update_trust(t_total, round_no, p_trust, p_gap)
        _apply_trust(self, t_total, round_no, p_trust, p_gap)
        return self

    def _compute_e_weight(self) -> float:
        """旧名别名。"""
        return self.e_weight()

    def e_weight(self) -> float:
        """D-002 二阶差分 + α=0.3 指数平滑，钳制 [-1, 1]（仅记录不参与决策）。"""
        h = self.trust_history
        if len(h) < 3:
            return 0.0
        t0, t1, t2 = h[-3], h[-2], h[-1]
        dr = max(1, t2["round"] - t1["round"])
        d2 = (t2["t_total"] - 2.0 * t1["t_total"] + t0["t_total"]) / (dr ** 2)
        sm = 0.3 * d2 + 0.7 * float(self.trust_state.get("e_weight", 0.0))
        return max(-1.0, min(1.0, sm))


def _apply_value_op(vals: List[str], value: str, replaces: Optional[str], remove: bool) -> List[str]:
    """价值观按条运算（纯函数）：删除 / 替换 replaces / 新增；结果去重保序、不得为空。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("value 必须是非空字符串")
    value = value.strip()
    if replaces is not None and replaces != value and replaces not in vals and not remove:
        raise ValueError(f"待替换的价值观不存在: {replaces!r}")      # 不静默改成「新增」（上游 #212）
    if remove:
        new = [v for v in vals if v != value]
    elif replaces is not None and replaces in vals:
        new = list(dict.fromkeys(value if v == replaces else v for v in vals))
    else:
        new = list(vals) if value in vals else list(vals) + [value]
    if not new:
        raise ValueError("价值观列表不能被清空")
    return new


def _apply_trust(m: "SelfModel", t_total: float, round_no: int, p_trust: Optional[float],
                 p_gap: Optional[float]) -> None:
    """信任状态更新（就地，值域校验 #206）。"""
    t = unit(require_finite(t_total, "t_total"), "t_total")
    m.trust_state["t_total"] = t
    pt, pg = unit_or_none(p_trust, "p_trust"), unit_or_none(p_gap, "p_gap")
    if pt is not None:
        m.trust_state["p_trust"] = pt
    if pg is not None:
        m.trust_state["p_gap"] = pg
    m.trust_history.append({"round": int(round_no), "t_total": t, "at": now()})
    m._clip()
    m.trust_state["e_weight"] = m.e_weight()


def _validate_changes(changes: Dict) -> Dict:
    """整体校验后才生效（F3）。旧契约（上游 #182）：
    - 白名单外、但是本模型已有属性（治理字段 / 方法 / 类常量）⇒ PermissionError；
    - 非本模型属性的未知键 ⇒ 忽略（不生效、不进 history）并发 RuntimeWarning；
    - 白名单字段须为字符串、identity 非空 ⇒ ValueError。"""
    governed = sorted(k for k in changes if k not in MUTABLE and hasattr(SelfModel, k)
                      or k in _FIELD_NAMES and k not in MUTABLE)
    if governed:
        raise PermissionError(f"自我模型不允许直接修改字段: {governed}"
                              "（价值观走 record_value_change/retire_value，信任走 update_trust_state）")
    unknown = [k for k in changes if k not in MUTABLE]
    for k in unknown:
        warnings.warn(f"SelfModel.update 忽略未知字段 {k!r}", RuntimeWarning, stacklevel=4)
    out = {k: v for k, v in changes.items() if k in MUTABLE}
    for k in ("identity", "state_description", "current_goal"):
        if k in out and not isinstance(out[k], str):
            raise ValueError(f"{k} 必须是字符串")
    if "identity" in out and not out["identity"].strip():
        raise ValueError("identity 不能为空")
    return out


_FIELD_NAMES = frozenset(f.name for f in fields(SelfModel))


def _clone(m: SelfModel) -> SelfModel:
    """深拷贝声明字段（不拷贝绑定的存储引用）。"""
    return SelfModel(**copy.deepcopy({f.name: getattr(m, f.name) for f in fields(SelfModel)}))


class SelfStore:
    """自我层持久化与受控修改。``model`` 对象身份在整个生命周期内不变（就地替换字段）。"""

    def __init__(self, store: Store, identity: str = "协议实例") -> None:
        self.store = store
        self.model = self._load() or SelfModel(identity=identity)
        self.model.__dict__["_store"] = self

    # ------------------------------------------------------------ 持久化
    def _load(self) -> Optional[SelfModel]:
        n = self.store.nodes.get(CORE_ID)
        if n is None:
            return None
        try:
            d = loads(n.content, {})
        except ValueError:
            return None
        known = {k: v for k, v in d.items() if k in SelfModel.__dataclass_fields__}
        m = SelfModel(**known)
        m.history = list(loads(self.store.meta.get("self_history").get("self_history"), []) or [])
        return m

    @property
    def persisted(self) -> bool:
        """F1：库中是否已有 SELF 核心节点（self_check 的真实判据，#107）。"""
        return self.store.nodes.layer_of(CORE_ID) == MemoryLayer.SELF

    def _persist(self, m: SelfModel, reason: str) -> None:
        cs = ConditionSpace.default("自我认知", "内省")
        t = now()
        node = Node(id=CORE_ID, content=dumps(m.core_dict()), modality="self_state",
                    spatial_coordinates={"self_axis": 1.0}, temporal_coordinate=t,
                    condition_space=cs, importance=0.9, confidence=1.0,
                    layer=MemoryLayer.SELF, tags=["self_core"], last_access=t, created_at=t)
        old = self.store.nodes.get(CORE_ID)
        if old is not None:
            node.created_at = old.created_at
        with self.store.db.tx() as c:
            self.store.nodes.put(node)
            self.store.meta.set("self_history", dumps(m.history))
            c.execute("INSERT INTO self_snapshots (ts, identity, reason, payload) VALUES (?,?,?,?)",
                      (t, m.identity, reason, dumps(m.core_dict())))
            c.execute("DELETE FROM self_snapshots WHERE id <= (SELECT MAX(id) FROM self_snapshots) - ?",
                      (SNAPSHOT_KEEP,))

    def _commit(self, m: SelfModel, reason: str) -> SelfModel:
        m._clip()
        self._persist(m, reason)      # F3：先落库
        for f in fields(SelfModel):   # 再就地替换内存字段（调用方持有的引用保持有效）
            setattr(self.model, f.name, getattr(m, f.name))
        return self.model

    # ------------------------------------------------------------ 修改
    def update(self, changes: Dict, reason: str = "update") -> SelfModel:
        """白名单字段修改（F3/F4）。"""
        ch = _validate_changes(changes)
        m = _clone(self.model)
        for k, v in ch.items():
            setattr(m, k, v)
        m.history.append({"timestamp": now(), "changes": ch})
        return self._commit(m, reason)

    @staticmethod
    def _record_values(m: SelfModel, new_values: List[str], trigger: str,
                       replaces: Optional[str] = None) -> None:
        old = list(m.values)
        t = now()
        by = next((v for v in new_values if v not in old), None)
        for v in old:
            if v not in new_values:
                rec = {"value": v, "from": True, "to": False, "trigger": trigger, "at": t}
                if replaces is not None and v == replaces:
                    rec.update(trigger="superseded", by=by or "")
                m.value_evolution.append(rec)
        for v in new_values:
            if v not in old:
                m.value_evolution.append({"value": v, "from": False, "to": True, "trigger": trigger, "at": t})
        m.values = list(new_values)

    def change_value(self, value: str, trigger: str, replaces: Optional[str] = None,
                     remove: bool = False) -> SelfModel:
        """价值观按条修正：新增 / 替换 ``replaces`` / 删除。无变化不记账（F4）。"""
        new = _apply_value_op(self.model.values, value, replaces, remove)
        if new == self.model.values:
            return self.model
        m = _clone(self.model)
        self._record_values(m, new, trigger, replaces)
        return self._commit(m, f"value:{trigger}")

    def update_trust(self, t_total: float, round_no: int, p_trust: Optional[float] = None,
                     p_gap: Optional[float] = None) -> SelfModel:
        """信任状态：t_total 有限性校验并钳到 [0,1]（#206）；e_weight 仅记录。"""
        m = _clone(self.model)
        _apply_trust(m, t_total, round_no, p_trust, p_gap)
        return self._commit(m, "trust")

    def link(self, node_id: str, confidence: float = 1.0) -> Optional[Edge]:
        """自我 → 经历 的因果边（SELF 端不衰减，#205 由层规则保证）。"""
        if self.store.nodes.get(node_id) is None or not self.persisted:
            return None
        e = Edge(id=f"edge_self_{node_id}", source_id=CORE_ID, target_id=node_id,
                 relation_type=EdgeType.CAUSAL, confidence=confidence, verified=False,
                 condition_space=ConditionSpace.default("自我认知", "内省"))
        self.store.edges.put(e)
        return e

    def snapshots(self, limit: int = 20) -> List[Dict]:
        """最近快照（新→旧）。"""
        rows = self.store.db.all("SELECT ts, identity, reason, payload FROM self_snapshots "
                                 "ORDER BY id DESC LIMIT ?", (limit,))
        return [{"ts": r[0], "identity": r[1], "reason": r[2], "payload": loads(r[3], {})} for r in rows]
