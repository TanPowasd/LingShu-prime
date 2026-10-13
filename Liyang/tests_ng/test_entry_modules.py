# -*- coding: utf-8 -*-
"""stab-r5：对外入口模块登记（lingshu_ng.ENTRY_MODULES / lingshu_ng.gen.ENTRY_MODULES）——属性访问懒加载、
``import lingshu_ng`` 本身不载入它们、未知名照常 AttributeError。"""
import importlib
import subprocess
import sys

import pytest

import lingshu_ng
import lingshu_ng.gen
from tests_ng._optdeps import require


def test_entry_attrs_resolve_to_submodules():
    for pkg in (lingshu_ng, lingshu_ng.gen):
        for name in pkg.ENTRY_MODULES:
            if pkg is lingshu_ng.gen:
                if name in ("hexgen", "composite"):
                    require("PIL")
            m = getattr(pkg, name)
            assert m is importlib.import_module(f"{pkg.__name__}.{name}")
            assert name in dir(pkg)
    with pytest.raises(AttributeError):
        lingshu_ng.no_such_entry
    with pytest.raises(AttributeError):
        lingshu_ng.gen.no_such_entry


def test_import_package_does_not_load_entries():
    code = ("import sys, lingshu_ng, lingshu_ng.gen; "
            "print(sorted(m for m in sys.modules if m in ('lingshu_ng.compat','lingshu_ng.provenance','lingshu_ng.gen.hexgen')))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"
