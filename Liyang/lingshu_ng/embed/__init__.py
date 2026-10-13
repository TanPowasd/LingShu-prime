# -*- coding: utf-8 -*-
"""lingshu_ng.embed · 本地句向量提供者的兼容入口（核心，纯标准库）

自 lingshu-ng 1.24 起，需要 numpy / onnxruntime / tokenizers 的 ``OnnxEmbedder`` 迁到插件 ``lingshu-ng-embed``
（``lingshu_ng_embed.onnx_embed``）；本模块保留纯标准库部分（:func:`split_sentences`、:func:`from_env` 的环境变量解析），
``from lingshu_ng.embed import OnnxEmbedder`` 在装了插件时照常可用（同一个类对象），未装时抛
:class:`lingshu_ng.plugins.PluginMissingError`（:class:`ImportError` 子类，信息写明 ``pip install lingshu-ng-embed``）。

``OnnxEmbedder(model_dir)``：BGE 系中文句向量（ONNX，CPU，CLS 池化 + L2 归一，逐条编码），实现 :mod:`lingshu_ng.semindex`
的「自带索引」提供者接口 ``add(ids, texts)`` / ``search(query, limit)``，也提供旧接口约定的 ``encode(text)``。

``from_env()``：读环境变量 ``LINGSHU_NG_EMBED_MODEL``（模型目录）构造；未设置返回 None。
``LINGSHU_NG_SENT_INDEX=1/0``：句级证据向量开关（默认关；只在有交叉编码重排时参与融合）。
"""
from __future__ import annotations

import os
import re
from typing import List

__all__ = ["OnnxEmbedder", "from_env", "split_sentences"]

#: 委托给插件的名字 → 插件模块（``embed_internals`` 能力：插件 lingshu-ng-embed 的 ``lingshu_ng_embed.onnx_embed``）
_DELEGATED = ("OnnxEmbedder", "_Blas1", "_blas_fns", "_BLAS")


def __getattr__(name):
    if name not in _DELEGATED:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from .. import plugins
    mod = plugins.require("onnx_embedder", what=f"lingshu_ng.embed.{name}")
    return getattr(mod, name)


def __dir__():
    return sorted(set(globals()) | set(_DELEGATED))


_SENT_END = re.compile(r"(?<=[。！？!?；…\n])")


def split_sentences(text: str, min_len: int = 24) -> List[str]:
    """句级证据单元：按中文句末标点/换行切句，短于 min_len 的并入后一句（末尾残句并回前一句）。纯标准库。"""
    parts = [p for p in _SENT_END.split(text or "") if p.strip()]
    out: List[str] = []
    cur = ""
    for p in parts:
        if len(cur) < min_len:
            cur += p
        else:
            out.append(cur)
            cur = p
    if cur:
        if out and len(cur) < min_len:
            out[-1] += cur
        else:
            out.append(cur)
    return [o.strip() for o in out if o.strip()]


def from_env():  # -> Optional[OnnxEmbedder]（插件类）
    """``LINGSHU_NG_EMBED_MODEL`` 指向模型目录时构造提供者；未设置返回 None。"""
    d = os.environ.get("LINGSHU_NG_EMBED_MODEL", "").strip()
    if not d:
        return None
    # 句级证据向量默认关：生产实测（HMB 184 问）must_exclude −0.040、要点 +0.017，但 cid −0.004、原句 −0.011，
    # 属取舍而非净增益（见 REPORT_neural.md）；需要更少干扰材料时显式开
    sent = os.environ.get("LINGSHU_NG_SENT_INDEX", "0").strip().lower()
    return __getattr__("OnnxEmbedder")(d, sentences=sent in ("1", "true", "yes", "on"))
