# -*- coding: utf-8 -*-
"""随机顺序插件（stab-r1；不依赖 pytest-randomly）：``python -m pytest -p tests_ng.shuffle_plugin tests_ng``

种子取 ``LINGSHU_TEST_SHUFFLE_SEED``（缺省取当前时间，报告头 / 结尾打印，便于复现）。先打乱测试文件的次序，
再打乱每个文件内用例的次序（同 pytest-randomly 的分桶法：文件级 fixture 不会被反复建拆）。
不改 ``random`` 的全局种子，不影响被测代码。
"""
import os
import random
import time
from collections import OrderedDict

_SEED = int(os.environ.get("LINGSHU_TEST_SHUFFLE_SEED") or int(time.time()) % 100000)


def pytest_report_header(config):
    return f"shuffle seed: {_SEED}（LINGSHU_TEST_SHUFFLE_SEED={_SEED} 可复现）"


def pytest_collection_modifyitems(session, config, items):
    rng = random.Random(_SEED)
    buckets = OrderedDict()
    for it in items:
        buckets.setdefault(str(it.fspath), []).append(it)
    keys = list(buckets)
    rng.shuffle(keys)
    out = []
    for k in keys:
        b = buckets[k]
        rng.shuffle(b)
        out.extend(b)
    items[:] = out


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"shuffle seed: {_SEED}")
