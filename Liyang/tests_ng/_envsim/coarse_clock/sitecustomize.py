# 测试用环境模拟：Windows 式粗粒度墙钟（time.time() 量化到 1/64 s）。只在 PYTHONPATH 显式加入本目录时生效。
import time as _time

_orig = _time.time
_RES = 1 / 64.0


def _coarse() -> float:
    return int(_orig() / _RES) * _RES


_time.time = _coarse
