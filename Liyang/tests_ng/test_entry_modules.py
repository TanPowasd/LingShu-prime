# -*- coding: utf-8 -*-
"""stab-r5：对外入口模块登记（lingshu_ng.ENTRY_MODULES / lingshu_ng.gen.ENTRY_MODULES）——属性访问懒加载、
``import lingshu_ng`` 本身不载入它们、未知名照常 AttributeError。

split-r3：rel-v1.24 起 ``lingshu_ng.gen`` 属插件 lingshu-ng-gen；核心部分与 gen 部分拆成两组用例，
纯核心环境（未装插件 / ``LINGSHU_NG_SOURCE_PLUGINS=0``）下 gen 组 skip（原因写明安装命令），核心组照常运行。"""
import importlib
import subprocess
import sys

import pytest

import lingshu_ng
from tests_ng._optdeps import require


def _gen():
    try:
        return importlib.import_module("lingshu_ng.gen")
    except ImportError as e:   # 未装 lingshu-ng-gen：兼容入口抛带安装提示的 ModuleNotFoundError
        pytest.skip(f"插件 lingshu-ng-gen 不可用：{e}")


def _check_entries(pkg):
    for name in pkg.ENTRY_MODULES:
        if pkg.__name__ == "lingshu_ng.gen" and name in ("hexgen", "composite"):
            require("PIL")
        m = getattr(pkg, name)
        assert m is importlib.import_module(f"{pkg.__name__}.{name}")
        assert name in dir(pkg)
    with pytest.raises(AttributeError):
        pkg.no_such_entry


def test_entry_attrs_resolve_to_submodules():
    _check_entries(lingshu_ng)


def test_gen_entry_attrs_resolve_to_submodules():
    _check_entries(_gen())


def _loaded_after(imports, names):
    code = f"import sys, {imports}; print(sorted(m for m in sys.modules if m in {tuple(names)!r}))"
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()


def test_import_package_does_not_load_entries():
    assert _loaded_after("lingshu_ng", ("lingshu_ng.compat", "lingshu_ng.provenance")) == "[]"


def test_import_gen_package_does_not_load_entries():
    _gen()
    assert _loaded_after("lingshu_ng, lingshu_ng.gen",
                         ("lingshu_ng.compat", "lingshu_ng.provenance", "lingshu_ng.gen.hexgen")) == "[]"
