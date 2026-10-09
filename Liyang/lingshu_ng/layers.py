# -*- coding: utf-8 -*-
"""layers · 记忆层不变量的唯一声明处 + 全部写路径共用的守卫（LayerPolicy）

为什么集中在这里：旧实现把「共享层只读」「锚点/结构层不衰减」「SELF 不可遗忘」
分散写在门面方法、SQL 字面量（``NOT IN ('anchor','structure')``）和若干 if 里，
于是出现了「门面加了锁、store 没加」(#222/#217)、「排除列表漏 SELF」(#205)、
「只看新行 layer 不看旧行 layer」(#127)、「边接口零守卫」(#244/#234) 一整类缺陷。

不变量（由 :class:`LayerPolicy` 强制，所有仓储写方法必须调用）：
  I1 共享层（anchor/structure）节点：仅 PRIMARY 可新建/改写/打标/保护；
     任何角色都不能删除。判定同时看**库中旧行的层**与**新行的层**。
  I2 层迁移只允许 :data:`ALLOWED_TRANSITIONS` 中列出的方向；共享层与 SELF 层只进不出。
  I3 边：任一端点在共享层 ⇒ 写/改/删该边需 PRIMARY（含同 id 覆盖）。
  I4 衰减/遗忘/检索资格只由 :data:`RULES` 推导；SQL 中的层列表由
     :meth:`LayerPolicy.layers_where` 生成，任何模块不得手写层名字面量。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, Optional, Tuple

from .types import MemoryLayer, Role

__all__ = ["LayerRule", "RULES", "ALLOWED_TRANSITIONS", "LayerPolicy", "LayerViolation"]


class LayerViolation(PermissionError):
    """违反层不变量（PermissionError 子类，与旧 API 的异常类型兼容）。"""


@dataclass(frozen=True)
class LayerRule:
    """单层规则。

    shared       共享层：跨实例同步、仅 PRIMARY 写。
    node_decays  节点 importance 随维护周期衰减并在阈值下被遗忘。
    edge_decays  该层节点上的未验证边是否参与边衰减（两端都为 True 才衰减）。
    deletable    是否允许显式删除。
    searchable   是否进入内容检索/召回/去重候选池。
    """
    shared: bool
    node_decays: bool
    edge_decays: bool
    deletable: bool
    searchable: bool


RULES: Dict[MemoryLayer, LayerRule] = {
    MemoryLayer.ANCHOR: LayerRule(True, False, False, False, True),
    MemoryLayer.STRUCTURE: LayerRule(True, False, False, False, True),
    MemoryLayer.SELF: LayerRule(False, False, False, False, False),
    MemoryLayer.KNOWLEDGE: LayerRule(False, False, True, True, True),
    MemoryLayer.CONTEXT: LayerRule(False, True, True, True, True),
}

#: 允许的层迁移（旧层 → 新层集合）；同层改写总是允许（受 I1 约束）。
ALLOWED_TRANSITIONS: Dict[MemoryLayer, FrozenSet[MemoryLayer]] = {
    MemoryLayer.CONTEXT: frozenset({MemoryLayer.KNOWLEDGE, MemoryLayer.STRUCTURE}),
    MemoryLayer.KNOWLEDGE: frozenset({MemoryLayer.STRUCTURE}),
    MemoryLayer.ANCHOR: frozenset(),
    MemoryLayer.STRUCTURE: frozenset(),
    MemoryLayer.SELF: frozenset(),
}


class LayerPolicy:
    """绑定角色的层守卫。无状态（除角色外），可安全共享。"""

    def __init__(self, role: Role = Role.PRIMARY) -> None:
        self.role = Role(role) if not isinstance(role, Role) else role

    # ------------------------------------------------------------ 查询
    @staticmethod
    def rule(layer: MemoryLayer) -> LayerRule:
        """取层规则（未知层抛 ValueError）。"""
        return RULES[MemoryLayer.coerce(layer)]

    @staticmethod
    def layers(**flags: bool) -> Tuple[MemoryLayer, ...]:
        """按规则字段筛层，如 ``layers(node_decays=True)``；顺序固定（声明序）。"""
        out = []
        for layer, rule in RULES.items():
            if all(getattr(rule, k) == v for k, v in flags.items()):
                out.append(layer)
        return tuple(out)

    @classmethod
    def layers_where(cls, column: str, **flags: bool) -> Tuple[str, Tuple[str, ...]]:
        """生成 ``column IN (?,..)`` 片段与参数——SQL 中层名的唯一来源（I4）。"""
        ls = cls.layers(**flags)
        if not ls:
            return "0", ()
        return f"{column} IN ({','.join('?' * len(ls))})", tuple(x.value for x in ls)

    @property
    def is_primary(self) -> bool:
        """是否主实例。"""
        return self.role == Role.PRIMARY

    # ------------------------------------------------------------ 守卫
    def check_node_write(self, new_layer: MemoryLayer,
                         old_layer: Optional[MemoryLayer] = None,
                         allow_transition: bool = False) -> None:
        """节点新建/改写守卫（I1 + I2）。``allow_transition`` 仅供晋升/提层等受审路径。"""
        new_layer = MemoryLayer.coerce(new_layer)
        touched = [new_layer] + ([MemoryLayer.coerce(old_layer)] if old_layer else [])
        if any(RULES[x].shared for x in touched) and not self.is_primary:
            raise LayerViolation(
                f"role={self.role.value} 无权写入共享层（{'/'.join(x.value for x in touched)}）")
        if old_layer is None or MemoryLayer.coerce(old_layer) == new_layer:
            return
        old_layer = MemoryLayer.coerce(old_layer)
        if not allow_transition or new_layer not in ALLOWED_TRANSITIONS[old_layer]:
            raise LayerViolation(f"不允许的层迁移 {old_layer.value} → {new_layer.value}")

    def check_node_delete(self, layer: MemoryLayer) -> None:
        """显式删除守卫：不可删除层一律拒绝（任何角色）。"""
        layer = MemoryLayer.coerce(layer)
        if not RULES[layer].deletable:
            raise LayerViolation(f"{layer.value} 层节点不可删除")

    def check_node_annotate(self, layer: MemoryLayer) -> None:
        """打标签/登记保护/登记冲突守卫：共享层需 PRIMARY（#217/#234）。"""
        layer = MemoryLayer.coerce(layer)
        if RULES[layer].shared and not self.is_primary:
            raise LayerViolation(f"role={self.role.value} 无权改写共享层节点的标注")

    def check_node_cascade(self, edges_store, nodes_store, node_id: str) -> None:
        """删节点会级联删其全部关联边（N5）：另一端在共享层的边同样受 I3 守卫（#244 级联面）。"""
        if self.is_primary:
            return
        adj = edges_store.outgoing(node_id) + edges_store.incoming(node_id)
        others = {e.target_id if e.source_id == node_id else e.source_id for e in adj}
        self.check_edge_write(nodes_store.layer_of(o) for o in others)

    def check_edge_write(self, endpoint_layers: Iterable[Optional[MemoryLayer]]) -> None:
        """边写/改/删守卫（I3）：端点含共享层 ⇒ 需 PRIMARY。端点缺失由仓储另行拒绝。"""
        for layer in endpoint_layers:
            if layer is not None and RULES[MemoryLayer.coerce(layer)].shared \
                    and not self.is_primary:
                raise LayerViolation(
                    f"role={self.role.value} 无权写入触及共享层（{MemoryLayer.coerce(layer).value}）的边")
