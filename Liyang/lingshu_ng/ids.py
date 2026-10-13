# -*- coding: utf-8 -*-
"""ids · 按写入序单调的唯一 id（stab-r3）

召回 / 排序里分数相同的候选最后按 id 断开（``sorted(..., key=lambda n: (-score[n], n))`` 一类写法遍布检索路径）。
旧 id 是 48 位随机十六进制，同分候选的先后因此每次运行都不一样（版本链 h100 / h50 前 60 名尾部相邻对换的根因，
见 CHANGELOG_rel-v1.18）。新 id = ``<prefix>_<14 位十六进制微秒时间戳，进程内严格递增><4 位随机十六进制>``：

* 同一进程内按生成先后严格递增，字典序 = 写入序 ⇒ 同分断开规则变成「先写入者在前」，与运行时刻无关、可复现；
* 跨进程（多个引擎写同一库）仍大体按时间递增；末 4 位随机只为防同一微秒的跨进程碰撞，主键冲突仍由库约束兜底；
* 旧库里的随机 id 照常可读写，新旧 id 混排时仍是确定的（只依赖库里已有的 id）。
"""
from __future__ import annotations

import os
import threading
import time

__all__ = ["new_id"]

_lock = threading.Lock()
_last = 0


def new_id(prefix: str) -> str:
    """``<prefix>_`` + 18 位小写十六进制；同进程内按调用先后严格递增（线程安全）。"""
    global _last
    with _lock:
        t = time.time_ns() // 1000
        if t <= _last:
            t = _last + 1
        _last = t
    return f"{prefix}_{t:014x}{os.urandom(2).hex()}"
