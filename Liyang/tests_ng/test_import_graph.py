# -*- coding: utf-8 -*-
"""stab-r1 #5：lingshu_ng 内部 import 图守卫——不允许新增「直接双向依赖」（A 导入 B 且 B 导入 A）。

口径（最严）：模块内任何位置的 import 语句都算（含函数体里的延迟导入），只排除 ``if TYPE_CHECKING:`` 块
（纯类型注解，运行期不导入）。

已清零：retrieval ↔ lexpath（判定函数下沉 recall_filter）、retrieval ↔ densefuse（同）、compat ↔ compat_engine
（LayeredStore 拆到 compat_store）；engine ↔ gate 只在 TYPE_CHECKING 里，不计。
已知存量（只许减少）：chain/ 规则版本模块之间的延迟互引——v16/v21/v26 等主干在运行期按缺省族开关调用后续版本，
后续版本又复用主干的正则与取值函数。拆它要改链抽取主干的调用约定，留作单独一轮（见 README 未解决项）。
"""
import ast
import os

PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lingshu_ng")

#: 已知存量（只许减少：修掉一对就从这里删掉，测试会提示过期条目）
KNOWN_DEBT = {
    ("lingshu_ng.chain.v16", "lingshu_ng.chain.v17"),
    ("lingshu_ng.chain.v16", "lingshu_ng.chain.v25"),
    ("lingshu_ng.chain.v21", "lingshu_ng.chain.v22"),
    ("lingshu_ng.chain.v21", "lingshu_ng.chain.v25"),
    ("lingshu_ng.chain.v26", "lingshu_ng.chain.v27"),
}


def _modules():
    mods = {}
    root = os.path.dirname(PKG)
    for dp, dn, fs in os.walk(PKG):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in fs:
            if f.endswith(".py"):
                p = os.path.join(dp, f)
                name = os.path.relpath(p, root)[:-3].replace(os.sep, ".")
                mods[name[:-9] if name.endswith(".__init__") else name] = p
    return mods


def _imports(tree):
    """全部 import 语句，跳过 ``if TYPE_CHECKING:`` 块。"""
    out, stack = [], [tree]
    while stack:
        n = stack.pop()
        if isinstance(n, ast.If) and (getattr(n.test, "id", None) == "TYPE_CHECKING"
                                      or getattr(n.test, "attr", None) == "TYPE_CHECKING"):
            stack.extend(n.orelse)
            continue
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            out.append(n)
        stack.extend(ast.iter_child_nodes(n))
    return out


def import_graph():
    mods = _modules()
    g = {}
    for m, p in mods.items():
        base = m.split(".") if p.endswith("__init__.py") else m.split(".")[:-1]
        deps = set()
        for n in _imports(ast.parse(open(p, encoding="utf-8").read())):
            if isinstance(n, ast.Import):
                for a in n.names:
                    x = a.name
                    while x and x not in mods:
                        x = x.rpartition(".")[0]
                    if x:
                        deps.add(x)
                continue
            mod = ".".join(base[:len(base) - (n.level - 1)] + ([n.module] if n.module else [])) if n.level else (n.module or "")
            for a in n.names:
                deps.add(mod + "." + a.name if mod + "." + a.name in mods else mod)
        deps.discard(m)
        g[m] = {d for d in deps if d in mods}
    return g


def bidirectional_pairs(g):
    return {tuple(sorted((a, b))) for a in g for b in g[a] if a in g.get(b, ())}


def test_no_new_bidirectional_imports():
    found = bidirectional_pairs(import_graph())
    new = sorted(found - KNOWN_DEBT)
    assert not new, f"新增直接双向依赖：{new}（拆接口或下沉公共模块，不要加进 KNOWN_DEBT）"


def test_known_debt_not_stale():
    found = bidirectional_pairs(import_graph())
    stale = sorted(KNOWN_DEBT - found)
    assert not stale, f"这些存量已修掉，请从 KNOWN_DEBT 删除：{stale}"


def test_non_chain_core_has_zero_bidirectional():
    """chain/ 规则版本模块之外（引擎、召回、门面、world、nn、gen、embed……）直接双向依赖为 0。"""
    found = bidirectional_pairs(import_graph())
    assert not [p for p in found if not all(x.startswith("lingshu_ng.chain.") for x in p)]


def test_guard_sees_lazy_imports_and_skips_type_checking():
    t = ast.parse("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import a\ndef f():\n    import b\n")
    assert sorted(a.names[0].name for a in _imports(t) if isinstance(a, ast.Import)) == ["b"]
