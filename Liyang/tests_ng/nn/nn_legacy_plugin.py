# -*- coding: utf-8 -*-
"""pytest 插件 / 导入钩子：把旧 ``lingshu.nn.<mod>`` 指向 ``lingshu_ng.nn.compat.<mod>``。
旧测试源码与断言一字不改。

- ``LINGSHU_NN_IMPL=ng``（缺省）：安装别名（sys.meta_path 查找器，命中即返回 compat 模块）；
- ``LINGSHU_NN_IMPL=legacy``：不安装，只固定从本仓导入旧 ``lingshu.nn``（对照基线）。

用法：PYTHONPATH=<repo>:<repo>/tests_ng/nn python -m pytest -p nn_legacy_plugin tests/test_hex_*.py
"""
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


def install():
    import lingshu.nn  # noqa: F401  （固定为本仓旧包）
    if os.environ.get("LINGSHU_NN_IMPL", "ng") != "ng":
        return []
    from lingshu_ng.nn.compat import install_legacy_aliases
    return install_legacy_aliases()


INSTALLED = install()
