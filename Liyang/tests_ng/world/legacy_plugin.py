# -*- coding: utf-8 -*-
"""pytest 插件 / 导入钩子：把旧 lingshu.world 下已重写的模块（world3d/vprim/shapes/skeleton3d/scene_simulator/spacetime_consistency/world_model/prediction/world_learner/curiosity_explorer/seven_layer_loop/multiview/semantic_anchor_graph/anchor_verify，及派生的 scene_model）
指向 lingshu_ng.world.compat。旧测试源码与断言一字不改。

- ``LINGSHU_WORLD_IMPL=ng``（缺省）：安装别名；
- ``LINGSHU_WORLD_IMPL=legacy``：不安装，只预先从本仓导入旧 ``lingshu.world``（对照基线，
  防止外部测试文件自带的 sys.path 插入把别的工作树的 lingshu 导进来）。

用法：PYTHONPATH=<repo>:<repo>/tests_ng/world python -m pytest -p legacy_plugin tests/test_world3d_*.py
"""
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


def install():
    import lingshu.world  # noqa: F401  （固定为本仓旧包）
    if os.environ.get("LINGSHU_WORLD_IMPL", "ng") != "ng":
        return []
    from lingshu_ng.world.compat import install_legacy_aliases
    return install_legacy_aliases()


INSTALLED = install()   # 插件被加载（-p）或被 import 时即生效，早于任何测试模块导入
