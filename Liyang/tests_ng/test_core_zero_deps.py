# -*- coding: utf-8 -*-
"""split-r1：核心零外部依赖守卫（rel-v1.24 拆包）。

``lingshu_ng/`` 包内每个 .py 只许导入标准库与 ``lingshu_ng`` 本身——模块顶层、函数内延迟导入、
``importlib.import_module("…")`` / ``__import__("…")`` 的字面量参数都算。白名单只有 ``sys.stdlib_module_names``、
``__future__`` 与 ``lingshu_ng``。依赖第三方库的部分在 ``plugins/lingshu-ng-*``（独立发行包）。
"""
import ast
import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lingshu_ng")
ALLOWED = set(sys.stdlib_module_names) | {"__future__", "lingshu_ng"}


def _core_files():
    out = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d != "__pycache__"]
        out += [os.path.join(dp, f) for f in fn if f.endswith(".py")]
    return sorted(out)


def _top(name):
    return (name or "").split(".")[0]


def foreign_imports(path):
    """``path`` 里所有非白名单导入：[(行号, 模块名, 形态)]。"""
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            bad += [(n.lineno, a.name, "import") for a in n.names if _top(a.name) not in ALLOWED]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and _top(n.module) not in ALLOWED:
            bad.append((n.lineno, n.module, "from-import"))
        elif isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) \
                and isinstance(n.args[0].value, str):
            f = n.func
            fname = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if fname in ("import_module", "__import__", "find_spec") and _top(n.args[0].value) not in ALLOWED:
                bad.append((n.lineno, n.args[0].value, fname))
    return bad


def test_core_has_no_foreign_imports():
    files = _core_files()
    assert len(files) > 50, files      # 防止路径算错时空跑通过
    hits = {os.path.relpath(p, ROOT): foreign_imports(p) for p in files}
    hits = {k: v for k, v in hits.items() if v}
    assert not hits, f"核心 lingshu_ng/ 出现非标准库导入（应移到 plugins/ 下的插件包）：{hits}"


def test_core_has_no_plugin_subpackages():
    """world / nn / gen 的源码不在核心目录里（只由 lingshu_ng._alias 按旧名载入插件目录）。"""
    for sub in ("world", "nn", "gen"):
        d = os.path.join(ROOT, sub)
        assert not any(f.endswith(".py") for f in (os.listdir(d) if os.path.isdir(d) else [])), d


@pytest.mark.parametrize("src, n", [
    ("import numpy\n", 1),
    ("def f():\n    import onnxruntime as ort\n", 1),
    ("from PIL import Image\n", 1),
    ("import importlib\nm = importlib.import_module('tokenizers')\n", 1),
    ("x = __import__('numpy.linalg')\n", 1),
    ("import os, json\nfrom . import diag\nfrom lingshu_ng import plugins\nimport importlib\nimportlib.import_module('sqlite3')\n", 0),
    ("import importlib\nname = 'numpy'\nimportlib.import_module(name)\n", 0),   # 变量名参数：插件声明的依赖探测（capabilities）
])
def test_guard_self_check(tmp_path, src, n):
    """守卫自检：顶层 / 函数内 / from / import_module / __import__ 字面量都抓得到，标准库与包内导入不报。"""
    p = tmp_path / "m.py"
    p.write_text(src, encoding="utf-8")
    assert len(foreign_imports(str(p))) == n
