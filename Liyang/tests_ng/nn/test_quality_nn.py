# -*- coding: utf-8 -*-
"""nn/gen 线结构门禁：函数 < 60 行、模块 < 600 行、依赖仅 stdlib + numpy + Pillow、不导入旧 lingshu 包、
公开函数/类有 docstring、无内建 hash()、无全局 np.random 随机源、无静默宽 except。"""
import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2] / "lingshu_ng"
FILES = sorted(list((ROOT / "nn").rglob("*.py")) + list((ROOT / "gen").glob("*.py")))
STDLIB = {"__future__", "math", "re", "sys", "time", "json", "os", "io", "hashlib", "threading", "dataclasses",
          "typing", "functools", "collections", "importlib", "itertools"}
ALLOWED = STDLIB | {"numpy", "PIL"}
RNG_OK = {"default_rng", "Generator"}


def _ids(p):
    return str(p.relative_to(ROOT))


@pytest.mark.parametrize("path", FILES, ids=_ids)
def test_function_and_module_size(path):
    src = path.read_text(encoding="utf-8")
    assert len(src.splitlines()) < 600, "模块超过 600 行"
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = node.end_lineno - node.lineno + 1
            assert n < 60, f"{node.name} 有 {n} 行"


@pytest.mark.parametrize("path", FILES, ids=_ids)
def test_dependencies(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            mods = [node.module or ""]
        for m in mods:
            assert not (m == "lingshu" or m.startswith("lingshu.")), f"导入旧包 {m}"
            assert m.split(".")[0] in ALLOWED, f"非允许依赖 {m}"


@pytest.mark.parametrize("path", FILES, ids=_ids)
def test_docstrings(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert ast.get_docstring(tree), "模块缺 docstring"
    nodes = list(tree.body) + [m for c in tree.body if isinstance(c, ast.ClassDef) for m in c.body]
    for node in nodes:                      # 模块级函数/类与类方法（嵌套闭包不计）
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            assert ast.get_docstring(node), f"{node.name} 缺 docstring"


@pytest.mark.parametrize("path", FILES, ids=_ids)
def test_no_builtin_hash_no_global_rng_no_silent_except(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "hash", "内建 hash() 跨进程不稳定（用 lingshu_ng.gen.ids）"
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) \
                and node.value.attr == "random" and isinstance(node.value.value, ast.Name) \
                and node.value.value.id in ("np", "numpy"):
            assert node.attr in RNG_OK, f"全局随机源 np.random.{node.attr}"
        if isinstance(node, ast.ExceptHandler):
            broad = node.type is None or (isinstance(node.type, ast.Name)
                                          and node.type.id in ("Exception", "BaseException"))
            assert not (broad and all(isinstance(b, ast.Pass) for b in node.body)), "静默宽 except"


def test_compat_surface_covers_legacy_tests():
    """旧测试 import 的名字在 compat 中全部存在。"""
    import re
    from lingshu_ng.nn import compat
    tests = pathlib.Path(__file__).resolve().parents[2] / "tests"
    missing = []
    for f in sorted(tests.glob("test_hex_*.py")) + sorted(tests.glob("test_stcnn_*.py")) + \
            [tests / "test_rust_bridge_plan.py"]:
        src = f.read_text(encoding="utf-8")
        for mod, names in re.findall(r"from lingshu\.nn\.(\w+) import \(?([^)]*?)\)?\n(?!\s+\w)", src, re.S):
            m = __import__(f"lingshu_ng.nn.compat.{mod}", fromlist=["x"])
            for n in re.split(r"[,\s]+", names.replace("(", " ").replace(")", " ")):
                if n and not n.startswith("#") and not hasattr(m, n):
                    missing.append(f"{f.name}:{mod}.{n}")
    assert set(compat.MODULES) >= {"hex_cnn", "hex_gen", "stcnn", "rust_bridge"}
    assert not missing, missing
