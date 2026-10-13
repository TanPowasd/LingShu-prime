# -*- coding: utf-8 -*-
"""recall_filter · 召回通路共用的可检索性判定（stab-r1：自 retrieval 下沉，消除 retrieval ↔ lexpath / densefuse 双向依赖）

- :func:`_layer_values`：可检索层的取值集合；
- :func:`_retired` / :data:`ARCHIVED_IMP_MAX`：Q5 退役判定（归档且 importance 未恢复）；
- :func:`tag_hit`：标签加分条件。

retrieval 中的同名符号是本模块的再导出（同一对象），行为逐字节不变。本模块不导入 retrieval 及其任何下游。
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Set

from .expansion import tags_of
from .layers import LayerPolicy
from .types import MemoryLayer

__all__ = ["ARCHIVED_IMP_MAX", "tag_hit"]

#: 归档节点的 importance 上限（forget_advisor 默认 archived_imp=0.1；恢复到此之上即解除退役）
ARCHIVED_IMP_MAX = 0.1 + 1e-9


def tag_hit(query: str, tags: Iterable[str]) -> bool:
    """标签加分条件：某标签等于查询，或（长度 >1 且）是查询的子串。"""
    return any(t == query or (len(t) > 1 and t in query) for t in tags)


def _layer_values(layers: Optional[Sequence[MemoryLayer]]) -> Set[str]:
    allowed = set(LayerPolicy.layers(searchable=True))
    use = [x for x in (MemoryLayer.coerce(y) for y in layers) if x in allowed] if layers else list(allowed)
    return {m.value for m in use}


def _retired(imp, tags_json) -> bool:
    """Q5：归档且未恢复（importance 仍 ≤ 归档值）。"""
    if not tags_json or "archived" not in tags_json:
        return False
    return (imp or 0.0) <= ARCHIVED_IMP_MAX and "archived" in tags_of(tags_json)
