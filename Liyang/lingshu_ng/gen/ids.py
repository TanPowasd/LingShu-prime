# -*- coding: utf-8 -*-
"""ids · 稳定标识：sha256(规范 JSON)。

旧 ``hexgen_multi_seed.load_multi`` 用内建 ``hash((sid, seed))`` 生成 id——字符串哈希随
``PYTHONHASHSEED`` 变化，跨进程不可复现（#198）。本模块是 gen 线唯一的 id 来源：
键排序、无空白、UTF-8 的 JSON 文本取 sha256，截取前 ``n`` 个十六进制字符。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """规范 JSON：键排序、紧凑分隔、保留中文；numpy 标量经 ``item()`` 转原生类型。"""
    def default(o: Any) -> Any:
        if hasattr(o, "item"):
            return o.item()
        if hasattr(o, "tolist"):
            return o.tolist()
        raise TypeError(f"不可序列化: {type(o).__name__}")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=default)


def stable_id(*parts: Any, n: int = 16) -> str:
    """任意可 JSON 化参数 → 稳定十六进制 id（跨进程/跨 PYTHONHASHSEED 一致）。"""
    return hashlib.sha256(canonical_json(list(parts)).encode("utf-8")).hexdigest()[:n]


def stable_int(*parts: Any, mod: int = 10 ** 9) -> int:
    """稳定整数 id（替代 ``hash(...) % mod``）。"""
    return int(hashlib.sha256(canonical_json(list(parts)).encode("utf-8")).hexdigest(), 16) % mod
