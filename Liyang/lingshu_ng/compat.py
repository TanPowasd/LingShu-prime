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

import importlib
import itertools
from typing import Dict, List, Optional, Sequence, Tuple

from .governance import designer_key_configured, verify_designer
from .timecore import cred_step
from .types import (CausalChain, ConditionSpace, Edge, EdgeType, MemoryLayer, Node, NodeType, Role,
                    now)

STNode = Node
STEdge = Edge

__all__ = ["ConditionSpace", "NodeType", "EdgeType", "MemoryLayer", "Role", "STNode", "STEdge",
           "CausalChain", "SelfModel", "LayeredStore", "SpacetimeMemoryEngine", "cred_step",
           "designer_key_configured", "verify_designer"]


from .compat_txguard import _loads_tags, _store_tx_guard  # noqa: E402,F401  旧模块级辅助名（#184/#267）
from .compat_engine import SpacetimeMemoryEngine  # noqa: E402  （门面类在独立模块，避免本文件超长）

#: stab-r13：旧版在本模块顶层导入的其余名字改为首次属性访问时载入（PEP 562），取到的是同一对象；
#: ``from lingshu_ng.compat import X`` / ``import *`` 照旧可用。它们连带载入存储层与检索层（约 40 个模块），
#: ``import lingshu_ng.compat`` 本身不再载入（tests_ng/test_import_lazy.py）。名字 → (子模块, 属性；None = 子模块本身)。
_LAZY: Dict[str, Tuple[str, Optional[str]]] = {
    "causal": ("causal", None), "graphquery": ("graphquery", None),
    "Maintenance": ("decay", "Maintenance"),
    "bigrams": ("dedup", "bigrams"), "jaccard": ("dedup", "jaccard"),
    "Insights": ("insight", "Insights"),
    "LayerPolicy": ("layers", "LayerPolicy"), "LayerViolation": ("layers", "LayerViolation"),
    "NegativeMemory": ("negative", "NegativeMemory"),
    "SYNONYM_GROUPS": ("retrieval", "SYNONYM_GROUPS"), "Retriever": ("retrieval", "Retriever"),
    "expand_terms": ("retrieval", "expand_terms"),
    "SelfModel": ("self_model", "SelfModel"), "SkillBook": ("skills", "SkillBook"),
    "Store": ("store", "Store"), "schema": ("store.schema", None),
    "LayeredStore": ("compat_store", "LayeredStore"),
}


def __getattr__(name: str):
    spec = _LAZY.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod = importlib.import_module("." + spec[0], __package__)
    val = mod if spec[1] is None else getattr(mod, spec[1])
    globals()[name] = val
    return val


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
