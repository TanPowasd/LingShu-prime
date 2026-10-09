# -*- coding: utf-8 -*-
"""pytest 插件：``LINGSHU_IMPL=ng python -m pytest -p tests_ng.ng_plugin tests/...``

插件在收集测试模块之前加载，因此旧测试的 ``from lingshu.core.core import ...`` 拿到的是 ng 门面。
未设置 LINGSHU_IMPL=ng 时什么都不做（旧实现照常运行）。
"""
from tests_ng import ng_switch

if ng_switch.enabled():
    ng_switch.install()


def pytest_report_header(config):  # noqa: D401
    """在报告头标注当前实现。"""
    return "lingshu impl: " + ("ng (lingshu_ng.compat)" if ng_switch.enabled() else "legacy")
