# -*- coding: utf-8 -*-
"""diag · 可见的退回（stab-r1）

可选依赖（onnxruntime / tokenizers / 模型文件）不可用时，各通路会逐位退回无模型档。退回本身不改变行为，
但必须看得见：每一类退回在进程内只打一次 ``logging.WARNING``（logger 名 ``lingshu_ng``），并登记进
:func:`fallbacks`，供 :func:`lingshu_ng.capabilities.capabilities` 与测试报告头读取。

只用标准库，不导入包内任何模块（任何模块都能安全地 import 它，不引入循环依赖）。
"""
from __future__ import annotations

import logging
import threading
from typing import Dict

log = logging.getLogger("lingshu_ng")

_LOCK = threading.Lock()
_FALLBACKS: Dict[str, str] = {}


def warn_once(key: str, msg: str) -> bool:
    """登记一类退回；同一 ``key`` 在进程内第一次出现时打一条 WARNING 并返回 True，之后只返回 False。"""
    with _LOCK:
        if key in _FALLBACKS:
            return False
        _FALLBACKS[key] = msg
    log.warning("lingshu_ng 退回 [%s]：%s", key, msg)
    return True


def cache_cap(name: str, default: int) -> int:
    """进程内缓存上限的环境变量（stab-r11）：非负整数，0 = 不缓存；未设/空串 → ``default``；非法值 → ``default``
    并打一条 WARNING（只影响内存与速度，不影响任何读数）。在模块导入时读取一次。"""
    import os
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    if raw.isdigit():
        return int(raw)
    log.warning("lingshu_ng：%s=%r 不是非负整数，按缺省 %d", name, raw, default)
    return default


def fallbacks() -> Dict[str, str]:
    """本进程迄今发生过的退回：{类别: 说明}（副本）。"""
    with _LOCK:
        return dict(_FALLBACKS)


def reset() -> None:
    """清空登记（测试用：让下一次退回重新打 WARNING）。"""
    with _LOCK:
        _FALLBACKS.clear()
