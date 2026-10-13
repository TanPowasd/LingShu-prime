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
from .compat_store import LayeredStore  # noqa: E402,F401  stab-r1：LayeredStore 自本模块拆出（消除 compat ↔ compat_engine 双向依赖）

STNode = Node
STEdge = Edge

__all__ = ["ConditionSpace", "NodeType", "EdgeType", "MemoryLayer", "Role", "STNode", "STEdge",
           "CausalChain", "SelfModel", "LayeredStore", "SpacetimeMemoryEngine", "cred_step",
           "designer_key_configured", "verify_designer"]


from .compat_txguard import _loads_tags, _store_tx_guard  # noqa: E402,F401  旧模块级辅助名（#184/#267）
from .compat_engine import SpacetimeMemoryEngine  # noqa: E402  （门面类在独立模块，避免本文件超长）
