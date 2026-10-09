# -*- coding: utf-8 -*-
"""scheduler · 后台自动衰减线程

旧实现的缺陷类别：stop→start 在一个 interval 内叠加线程(core-py-06)；close() 不 join，
后台线程访问已关闭连接(#37)；首次异常即静默退出(#184)；遗忘按调用次数计(#176)。

不变量：
  W1 每次 start 创建独立的 stop Event；stop 置位并 join（带超时）——任何时刻至多一个
     活动线程。
  W2 tick 收到的是**墙钟流逝秒数**（距上一次 tick），调用方据此换算等效衰减因子。
  W3 tick 抛异常不终止线程：记入 ``errors``（有界）并按指数退避继续。
"""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional

__all__ = ["AutoDecay"]


class AutoDecay:
    """周期执行 ``tick(elapsed_seconds)``。"""

    MAX_ERRORS = 50

    def __init__(self, tick: Callable[[float], object]) -> None:
        self._tick = tick
        self._thread: Optional[threading.Thread] = None
        self._stop: Optional[threading.Event] = None
        self._lock = threading.Lock()
        self.errors: List[str] = []

    @property
    def running(self) -> bool:
        """是否有活动线程。"""
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def start(self, interval: float = 60.0) -> bool:
        """启动（已在运行则返回 False）。"""
        if not (interval > 0):
            raise ValueError("interval 必须为正数")
        with self._lock:
            if self.running:
                return False
            stop = threading.Event()
            self._stop = stop
            self._thread = threading.Thread(target=self._loop, args=(stop, float(interval)),
                                            name="lingshu-ng-autodecay", daemon=True)
            self._thread.start()
            return True

    def _loop(self, stop: threading.Event, interval: float) -> None:
        last = time.monotonic()
        backoff = interval
        while not stop.wait(backoff):
            t = time.monotonic()
            try:
                self._tick(t - last)
                backoff = interval
            except Exception as exc:  # W3：记录并退避，不静默退出
                self.errors.append(f"{type(exc).__name__}: {exc}")
                del self.errors[:-self.MAX_ERRORS]
                backoff = min(interval * 8, backoff * 2)
            last = t

    def stop(self, timeout: float = 5.0) -> None:
        """停止并等待线程退出（W1）。"""
        with self._lock:
            stop, th = self._stop, self._thread
            if stop is not None:
                stop.set()
        if th is not None and th is not threading.current_thread():
            th.join(timeout)
