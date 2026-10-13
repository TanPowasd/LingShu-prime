# -*- coding: utf-8 -*-
"""stab-r2：chain 共享工具下沉 chain/common 后，主干模块的原名仍是同一对象；v17.two_vals 未注入取值函数时不改判。"""
from lingshu_ng.chain import common, v16, v17, v21, v26


def test_reexports_are_same_objects():
    for n in ("_CJK", "_TR", "_UNDEC", "_TWOC", "_RETIRE", "_HYPO", "_PAST", "GLOB", "_reason_of", "known_vals", "gvals", "want_of", "_find_names"):
        assert getattr(v16, n) is getattr(common, n), n
    for n in ("_NONASSERT", "_DISP"):
        assert getattr(v21, n) is getattr(common, n), n
    for n in ("_FHEAD", "_FTAIL2", "_FTAIL1", "_FMID", "_REDUP", "_SEGNN", "_FUSE", "frame"):
        assert getattr(v26, n) is getattr(common, n), n


def test_common_imports_no_rule_version():
    import ast, inspect
    t = ast.parse(inspect.getsource(common))
    mods = {n.module for n in ast.walk(t) if isinstance(n, ast.ImportFrom) and n.level}
    mods |= {a.name for n in ast.walk(t) if isinstance(n, ast.ImportFrom) and n.level and not n.module for a in n.names}
    assert not {m for m in mods if m and m.startswith("v") and m[1:].isdigit()}, mods


def test_two_vals_without_injected_vals_is_noop():
    class E:
        op, attr, quote, reason, entity, value, alt = "set", "位置", "位置还没定，A 还是 B", None, "x", "A", None
    e = E()
    assert v17.two_vals(None, e, "ns", [], vals=None) is False and e.op == "set"
