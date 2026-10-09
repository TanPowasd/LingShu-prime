# -*- coding: utf-8 -*-
"""结构性门禁：零依赖、不导入旧 core、无 LIKE 拼接、模块 <600 行、函数 <60 行、公开函数有 docstring、
兼容门面覆盖旧 core 测试用到的全部公开方法。"""
import ast
import os
import re

import pytest

PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lingshu_ng")
STDLIB_OK = {"__future__", "ast", "copy", "contextlib", "dataclasses", "enum", "hashlib", "hmac", "json",
             "math", "os", "random", "re", "sqlite3", "sys", "threading", "time", "typing", "unicodedata",
             "uuid", "importlib", "itertools", "collections", "functools", "io", "warnings",
             "difflib"}   # difflib：conflict.py 写入期矛盾检测的短文本对齐（标准库）


#: 本门禁只覆盖记忆引擎（lingshu_ng 根 + store/ + perception/）；lingshu_ng/world/ 属另一条重写线，不在此范围
SCOPE = (PKG, os.path.join(PKG, "store"), os.path.join(PKG, "perception"))


def _files():
    for d in SCOPE:
        for f in sorted(os.listdir(d)):
            if f.endswith(".py"):
                yield os.path.join(d, f)


def _code_strings(tree):
    """非 docstring 的字符串常量（即代码里真正会执行的 SQL 片段）。"""
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body \
                and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            docs.add(id(node.body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


@pytest.mark.parametrize("path", sorted(_files()), ids=lambda p: os.path.relpath(p, PKG))
def test_module_rules(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    assert len(src.splitlines()) < 600, "模块超过 600 行"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for m in mods:
                if isinstance(node, ast.ImportFrom) and node.level:
                    continue
                assert not m.startswith("lingshu.") and m != "lingshu", f"导入了旧包 {m}"
                assert m.split(".")[0] in STDLIB_OK, f"非标准库依赖 {m}"
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = node.end_lineno - node.lineno + 1
            assert n < 60, f"{node.name} 有 {n} 行"
    assert not [x for x in _code_strings(tree) if re.search(r"\bLIKE\b", x)], "SQL 中出现 LIKE"
    assert ast.get_docstring(tree), "模块缺 docstring"


def test_no_silent_broad_except():
    """#170：不允许 ``except Exception: pass`` 式静默吞错。"""
    bad = []
    for path in _files():
        for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
            if isinstance(node, ast.ExceptHandler):
                broad = node.type is None or (isinstance(node.type, ast.Name)
                                              and node.type.id in ("Exception", "BaseException"))
                if broad and all(isinstance(b, ast.Pass) for b in node.body):
                    bad.append(f"{os.path.basename(path)}:{node.lineno}")
    assert not bad, bad


def test_public_functions_documented():
    missing = []
    for path in _files():
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and not node.name.startswith("_") \
                    and not ast.get_docstring(node):
                missing.append(f"{os.path.basename(path)}:{node.name}")
    assert not missing, missing


LEGACY_METHODS = {
    "SpacetimeMemoryEngine": ["add_perception", "add_context", "add_edge", "add_structure_node", "set_anchor",
                              "consolidate_learning_result", "decay_cycle", "forget_advisor", "start_auto_decay",
                              "stop_auto_decay", "search_content", "longterm_snapshot", "prefeed_input",
                              "set_context_cap", "reason_causal", "self_check", "export_all", "import_all",
                              "verify_integrity", "_existing_tables", "visual_check", "close", "M13_TABLES"],
    "LayeredStore": ["get_node", "get_nodes_by_tag", "query_nodes", "add_node", "add_edge", "add_blindspot",
                     "find_cycles", "has_causal_cycle", "decay_cycle", "protect_node", "insight_record",
                     "insight_verify", "insight_report", "recalc_structural_importance", "SCHEMA_VERSION", "conn"],
}


def test_compat_surface_covers_legacy_core_tests():
    from lingshu_ng import compat
    e = compat.SpacetimeMemoryEngine()
    for name in LEGACY_METHODS["SpacetimeMemoryEngine"]:
        assert hasattr(e, name), name
    for name in LEGACY_METHODS["LayeredStore"]:
        assert hasattr(e.store, name), name
    for name in ("ConditionSpace", "EdgeType", "MemoryLayer", "STNode", "STEdge", "Role", "cred_step"):
        assert hasattr(compat, name)
    assert e.world3d("status", {})["status"] in ("ok", "world3d_not_ready")   # 委托 ng 世界线（numpy 可选）
    with pytest.raises(NotImplementedError):
        e.world_generator("init", {})
    assert e.evo_flywheel_metrics()["status"] == "v111_not_ready"
