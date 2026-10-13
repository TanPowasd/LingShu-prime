# -*- coding: utf-8 -*-
"""lingshu_ng.embed.cross · 本地交叉编码重排器的兼容入口（核心，纯标准库）

自 lingshu-ng 1.24 起 ``OnnxCrossEncoder``（numpy / onnxruntime / tokenizers）迁到插件 ``lingshu-ng-embed``
（``lingshu_ng_embed.cross``）；本模块保留纯标准库部分（缓存键 ``_key``、:func:`from_env`）。
``from lingshu_ng.embed.cross import OnnxCrossEncoder`` 装了插件时照常可用，未装时抛
:class:`lingshu_ng.plugins.PluginMissingError`（信息写明 ``pip install lingshu-ng-embed``）。

``OnnxCrossEncoder(model_dir)``：BGE reranker 系 ONNX 导出，对 (查询, 原文) 成对打分（logit），只在读路径使用；
实现 :mod:`lingshu_ng.neural` 的交叉编码提供者接口 ``score(query, texts) -> List[float]``。
``from_env()``：读 ``LINGSHU_NG_RERANK_MODEL``（模型目录）；未设置返回 None。
"""
from __future__ import annotations

import hashlib
import os

__all__ = list(("OnnxCrossEncoder", "from_env"))  # OnnxCrossEncoder 经 __getattr__ 委托插件


def __getattr__(name):
    if name != "OnnxCrossEncoder":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from .. import plugins
    return getattr(plugins.require("onnx_cross_encoder", what=f"lingshu_ng.embed.cross.{name}"), name)


def __dir__():
    return sorted(set(globals()) | {"OnnxCrossEncoder"})


def _key(q: str, t: str) -> bytes:
    h = hashlib.blake2b(digest_size=16)
    h.update(q.encode("utf-8", "surrogatepass"))
    h.update(b"\x00")
    h.update(t.encode("utf-8", "surrogatepass"))
    return h.digest()


def from_env():
    """``LINGSHU_NG_RERANK_MODEL`` 指向模型目录时构造；未设置返回 None。"""
    d = os.environ.get("LINGSHU_NG_RERANK_MODEL", "").strip()
    return __getattr__("OnnxCrossEncoder")(d) if d else None
