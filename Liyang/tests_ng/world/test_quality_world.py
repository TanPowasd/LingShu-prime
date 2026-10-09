"""world 线结构门禁：函数 < 60 行、公开函数带类型标注、仅依赖 stdlib + numpy（PIL 仅 compat 惰性）、
不在模块顶层导入旧 lingshu 包。"""
import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2] / "lingshu_ng" / "world"
FILES = sorted(ROOT.glob("*.py"))
STDLIB = {"__future__", "math", "random", "re", "sys", "time", "types", "uuid", "itertools",
          "dataclasses", "typing", "importlib", "pathlib", "functools", "json"}


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_functions_short_and_annotated(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = node.end_lineno - node.lineno + 1
            assert n < 60, f"{path.name}:{node.name} {n} 行"
            if not node.name.startswith("_") and path.name != "catalog.py":
                assert node.returns is not None, f"{path.name}:{node.name} 缺返回类型标注"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_top_level_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            mods = [node.module]
        for m in mods:
            top = m.split(".")[0]
            assert top in STDLIB | {"numpy"}, f"{path.name}: 顶层 import {m}"
