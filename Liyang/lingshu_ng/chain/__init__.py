# -*- coding: utf-8 -*-
"""lingshu_ng.chain —— 版本链（编年）记忆核心：写入期零 LLM 登记「实体·属性·值·有效区间·来源原文」，
查询期路由现值 / 时点历史 / 变更链 / 四态（含退役、未决）/ 缘由回源。默认关闭，``LINGSHU_NG_CHAIN=1`` 或
``MemoryEngine.enable_chain()`` 启用；启用后 ``recall`` 把当前版本段与变更链段排在基础召回之前，API 不变。"""
from .extract import Event, extract, parse_header
from .ledger import Ledger, Rec
from .reader import answer, plan, read_material
from .route import Route, route

__all__ = ["Event", "extract", "parse_header", "Ledger", "Rec", "answer", "plan", "read_material", "Route", "route",
           "ChainIndex"]


def __getattr__(name):
    if name == "ChainIndex":
        from .index import ChainIndex
        return ChainIndex
    raise AttributeError(name)
