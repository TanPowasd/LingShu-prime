# -*- coding: utf-8 -*-
"""插件测试公共设置（split-r1）。

- 已 pip 安装 lingshu-ng（干净 venv：核心 + 本插件）⇒ 直接用已安装的包；
- 未安装（仓库 / 发布目录里直接跑）⇒ 把仓库根（本目录上三级：plugins/<插件>/<测试目录>/..）放进 sys.path，
  核心的源码树发现（lingshu_ng._alias.source_plugin_paths）会找到 plugins/*/src 下的插件。
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
if importlib.util.find_spec("lingshu_ng") is None and REPO not in sys.path:
    sys.path.insert(0, REPO)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lingshu_ng._alias  # noqa: E402

lingshu_ng._alias.source_plugin_paths()   # 源码树：把 plugins/*/src 放进 sys.path（已 pip 安装时无此目录，不做事）

# split-r3：最小环境（源码目录里插件可见、但没装 numpy / Pillow / onnxruntime / tokenizers）下，
# 测试模块导入期或用例体内因这些第三方包缺失而失败 → 改报 skip（带原因）；其他错误照常。装齐依赖时本钩子不改变任何结果。
# （同 tests_ng/conftest.py 对 rel-v1.23 world/nn 子树的处理；插件测试目录各自独立安装，故各带一份。）
import pytest  # noqa: E402

_THIRD_PARTY = ("numpy", "PIL", "onnxruntime", "tokenizers")
#: 旧包 lingshu 只在仓库源码目录（Liyang/lingshu/）里有、不随任何发行包发布：与它逐位对照的用例在干净 venv（已 pip 安装、在无关目录运行）里 skip
_LEGACY = ("lingshu",)


def _why(dep):
    if dep in _LEGACY:
        return "旧包 lingshu 对照用例：旧包只在仓库源码目录可用（不随发行包发布），在仓库根运行时照常执行"
    return f"可选依赖 {dep} 未安装（插件测试需先 pip install 本插件包）"


def _missing_dep(text):
    for dep in _THIRD_PARTY + _LEGACY:
        if f"No module named '{dep}'" in text or f"No module named '{dep}." in text:
            return dep
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    outcome = yield
    rep = outcome.get_result()
    if not rep.failed or not isinstance(collector, pytest.Module):
        return
    dep = _missing_dep(str(rep.longrepr))
    if dep:
        rep.outcome = "skipped"
        rep.longrepr = (str(collector.path), 0, f"Skipped: {_why(dep)}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if not rep.failed or call.excinfo is None or not call.excinfo.errisinstance(ModuleNotFoundError):
        return
    dep = (getattr(call.excinfo.value, "name", None) or "").split(".")[0]
    if dep in _THIRD_PARTY + _LEGACY:
        rep.outcome = "skipped"
        rep.longrepr = (str(item.path), item.location[1] or 0, f"Skipped: {_why(dep)}")
