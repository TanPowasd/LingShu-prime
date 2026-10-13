# -*- coding: utf-8 -*-
"""compat_providers · 旧 API 的「依赖注入」接口（stab-r2：由占位转为真实实现）

旧 ``SpacetimeMemoryEngine`` 把语义空间 / 注意力 / 视觉做成可注入的 duck-typed 提供者：
``set_*`` 注入、``get_*`` 读回，相关方法在提供者存在时委托它，不存在时返回固定的退回值。
公开仓形态下默认没有提供者，所以这些方法以前在 ng 里只做成占位（恒返回退回值）。
现在按旧版同样的约定真实实现：注入后照样委托（调用方自己的提供者对象），未注入时退回值与旧版一致。

本模块不内置任何提供者，也不写库（``attend_query`` 只读知识层节点）。
有意不同：旧版 ``semantic_blindspot_report`` / ``compiler_introspect`` 未注入时 ``error`` 是旧引擎的装配错误原文，
ng 写固定说明（ng 没有对应的自动装配步骤）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .types import MemoryLayer

__all__ = ["ProvidersMixin", "PROVIDED"]

_NO_SEM = "未注入语义提供者（ng 不自动装配；用 set_semantic_provider 注入）"

#: 本模块真实实现、因而从 compat_stubs.NOT_READY 移出的方法名
PROVIDED = ("set_semantic_provider", "get_semantic_provider", "resolve_concepts", "compute_semantic_coordinates",
            "semantic_blindspot_report", "compiler_introspect",
            "set_attention_policy", "get_attention_policy", "filter_attention", "allocate_depth", "attend_query",
            "set_vision_provider", "get_vision_provider")


class ProvidersMixin:
    """语义 / 注意力 / 视觉提供者的注入与委托（旧版同名方法的约定）。"""

    _semantic_provider: Any = None
    _attention_policy: Any = None
    _vision_provider: Any = None

    # ---------------------------------------------------------------- 语义空间
    def set_semantic_provider(self, provider: Any) -> None:
        """注入语义提供者（duck-typed：to_coordinates / resolve_concepts / introspect / blindspot_report）。传 None 即撤销。"""
        self._semantic_provider = provider

    def get_semantic_provider(self) -> Any:
        """读回已注入的语义提供者（未注入为 None）。"""
        return self._semantic_provider

    def resolve_concepts(self, text: str) -> List[str]:
        """文本 → 协议概念；未注入语义提供者时返回空列表。"""
        if not self._semantic_provider:
            return []
        return self._semantic_provider.resolve_concepts(text)

    def compute_semantic_coordinates(self, text: str) -> Dict[str, float]:
        """文本 → 语义坐标（委托 ``to_coordinates``）；未注入时返回空字典。"""
        if not self._semantic_provider:
            return {}
        return self._semantic_provider.to_coordinates(text)

    def semantic_blindspot_report(self) -> Dict:
        """语义盲区报告（委托 ``blindspot_report``）；未注入时 ``{"available": False, "error": …}``。"""
        if not self._semantic_provider:
            return {"available": False, "error": _NO_SEM}
        return self._semantic_provider.blindspot_report()

    def compiler_introspect(self) -> Dict:
        """编译器自省（委托 ``introspect``）；未注入时 ``{"available": False, "error": …}``。"""
        if not self._semantic_provider:
            return {"available": False, "error": _NO_SEM}
        return self._semantic_provider.introspect()

    # ---------------------------------------------------------------- 注意力
    def set_attention_policy(self, policy: Any) -> None:
        """注入注意力策略（duck-typed：filter_attention / allocate_depth / attend）。传 None 即撤销。"""
        self._attention_policy = policy

    def get_attention_policy(self) -> Any:
        """读回已注入的注意力策略（未注入为 None）。"""
        return self._attention_policy

    def filter_attention(self, signals: List[Dict], threshold: Optional[float] = None) -> List[Dict]:
        """输入侧过滤：委托策略；未注入时原样返回 ``signals``。"""
        if not self._attention_policy:
            return signals
        return self._attention_policy.filter_attention(signals, threshold)

    def allocate_depth(self, signal: Dict, context: Optional[Dict] = None) -> int:
        """处理深度分配（L1/L2/L3）：委托策略；未注入时返回 1。"""
        if not self._attention_policy:
            return 1
        return self._attention_policy.allocate_depth(signal, context)

    def attend_query(self, query: str, limit: int = 10, source: str = "engine") -> List[Dict]:
        """知识层节点（至多 200 个）交策略 ``attend`` 排序，取前 ``limit``；未注入时返回空列表。只读。"""
        if not self._attention_policy:
            return []
        nodes = self.store.query_nodes(layer=MemoryLayer.KNOWLEDGE, limit=200)
        cands = [{"id": n.id, "content": n.content, "signal_type": n.modality, "information_gap": 0.0} for n in nodes]
        return self._attention_policy.attend(cands, query=query, source=source)[:limit]

    # ---------------------------------------------------------------- 视觉
    def set_vision_provider(self, provider: Any) -> None:
        """注入视觉提供者（duck-typed：available() / detect()）。ng 不内置视觉闭环，``perceive_image`` 仍是占位。"""
        self._vision_provider = provider

    def get_vision_provider(self) -> Any:
        """读回已注入的视觉提供者（未注入为 None）。"""
        return self._vision_provider
