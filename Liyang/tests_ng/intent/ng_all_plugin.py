# -*- coding: utf-8 -*-
"""意图守卫插件：在「旧项目工作树」里把旧模块整体换成 ng（core / world / nn 三条线一起）。

用法（由 run_intent.py 调用）：
  cwd=<旧树根>  PYTHONPATH=<旧树根>:<rewrite 根>:<本目录>  LINGSHU_INTENT_IMPL=ng|legacy
  python -m pytest -p ng_all_plugin <旧树>/tests/test_x.py

- 旧树的 ``lingshu`` 包（integrated@667e84a 或 upstream）先于 rewrite 的旧副本被导入；
- ng 模式下安装 tests_ng.ng_switch（core）、lingshu_ng.world.compat、lingshu_ng.nn.compat 三组别名；
- legacy 模式什么都不装（同一 harness 下的旧实现对照）。
旧测试源码与断言一字不改。
"""
import os
import sys

IMPL = os.environ.get("LINGSHU_INTENT_IMPL", "ng")


def _install():
    import lingshu  # noqa: F401  旧树的包
    if IMPL != "ng":
        return []
    from tests_ng import ng_switch
    done = list(ng_switch.install())
    from lingshu_ng.world.compat import install_legacy_aliases as w
    done += ["lingshu.world." + s for s in w()]
    from lingshu_ng.nn.compat import install_legacy_aliases as n
    done += n()
    return done


INSTALLED = _install()


def pytest_report_header(config):  # noqa: D401
    return "lingshu intent impl: %s (%d aliases)" % (IMPL, len(INSTALLED))
