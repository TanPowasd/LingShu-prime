"""同一 AST 脚本量两边（stab-r5，对齐《架构对比审计 v0.1》§2 的度量项）。只读源码，不导入被测包。

用法：python tools/compare/ast_metrics.py <包目录> [--exclude 子目录,子目录] [--json]
度量：py 文件数、总行数、最大文件、最大函数、函数 >50/>100/>200 行、宽 except（裸 except / Exception / BaseException）
及其中静默者（处理体内无 raise、无日志调用、无 warnings.warn）、直接双向依赖对（运行期：含函数内 import，不含 ``if TYPE_CHECKING:`` 块；另报含 TYPE_CHECKING 的对数与去掉「包 ↔ 其子模块」后的对数）、
孤儿模块（包内无任何其它模块 import 它，且不是 __init__ / __main__）。
"""
from __future__ import annotations

import ast
import json
import os
import sys

BROAD = {"Exception", "BaseException"}
LOGNAMES = {"debug", "info", "warning", "warn", "error", "exception", "critical", "warn_once", "log"}


def is_broad(t) -> bool:
    if t is None:
        return True
    if isinstance(t, ast.Name):
        return t.id in BROAD
    if isinstance(t, ast.Attribute):
        return t.attr in BROAD
    if isinstance(t, ast.Tuple):
        return any(is_broad(e) for e in t.elts)
    return False


def loud(h) -> bool:
    for n in ast.walk(ast.Module(body=h.body, type_ignores=[])):
        if isinstance(n, ast.Raise):
            return True
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if name in LOGNAMES:
                return True
    return False


def scan(pkg: str, exclude=()) -> dict:
    pkg = os.path.abspath(pkg)
    files = []
    for dp, dn, fn in os.walk(pkg):
        rel = os.path.relpath(dp, pkg)
        dn[:] = sorted(d for d in dn if d != "__pycache__" and not d.startswith(".")
                       and (os.path.normpath(os.path.join(rel, d)) if rel != "." else d) not in exclude)
        files += [os.path.join(dp, f) for f in sorted(fn) if f.endswith(".py")]

    def modname(p):
        r = os.path.relpath(p, os.path.dirname(pkg)).replace(os.sep, ".")[:-3]
        return r[:-9] if r.endswith(".__init__") else r

    mods = {modname(p): p for p in files}
    lines_tot, max_file, funcs, broad, silent = 0, ("", 0), [], 0, 0
    edges, edges_tc = {}, {}
    for m, p in mods.items():
        src = open(p, encoding="utf-8", errors="replace").read()
        n_lines = src.count("\n") + (0 if src.endswith("\n") or not src else 1)
        lines_tot += n_lines
        if n_lines > max_file[1]:
            max_file = (os.path.relpath(p, os.path.dirname(pkg)), n_lines)
        tree = ast.parse(src)
        is_pkg = p.endswith("__init__.py")
        base = m.split(".") if is_pkg else m.split(".")[:-1]
        out, out_tc = set(), set()
        tc_ids = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and (
                    (isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING")
                    or (isinstance(node.test, ast.Attribute) and node.test.attr == "TYPE_CHECKING")):
                for b in node.body:
                    tc_ids.update(id(x) for x in ast.walk(b))
        for node in ast.walk(tree):
            tgt = out_tc if id(node) in tc_ids else out
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append((node.end_lineno - node.lineno + 1, f"{os.path.relpath(p, os.path.dirname(pkg))}:{node.lineno} {node.name}"))
            elif isinstance(node, ast.ExceptHandler) and is_broad(node.type):
                broad += 1
                silent += not loud(node)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    n = a.name
                    while n and n not in mods:
                        n = n.rpartition(".")[0]
                    if n:
                        tgt.add(n)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    b = base[:len(base) - (node.level - 1)]
                    mm = ".".join(b + ([node.module] if node.module else []))
                else:
                    mm = node.module or ""
                for a in node.names:
                    c = mm + "." + a.name
                    if c in mods:
                        tgt.add(c)
                    elif mm in mods:
                        tgt.add(mm)
        out.discard(m)
        out_tc.discard(m)
        edges[m] = out
        edges_tc[m] = out | out_tc
    pairs = sorted({tuple(sorted((a, b))) for a in edges for b in edges[a] if a in edges.get(b, ())})
    pairs_tc = sorted({tuple(sorted((a, b))) for a in edges_tc for b in edges_tc[a] if a in edges_tc.get(b, ())})
    def parent_child(a, b):
        return b.startswith(a + ".") or a.startswith(b + ".")
    pairs_np = [pr for pr in pairs if not parent_child(*pr)]
    imported = {b for a in edges for b in edges[a]}
    top = os.path.basename(pkg)
    orphans = sorted(m for m, p in mods.items() if m not in imported and not p.endswith(("__init__.py", "__main__.py")) and m != top)
    funcs.sort(reverse=True)
    return {"package": os.path.basename(pkg), "exclude": list(exclude), "py_files": len(mods), "lines": lines_tot,
            "max_file": {"path": max_file[0], "lines": max_file[1]},
            "max_function": {"lines": funcs[0][0] if funcs else 0, "where": funcs[0][1] if funcs else None},
            "functions": len(funcs), "func_gt50": sum(1 for f in funcs if f[0] > 50),
            "func_gt100": sum(1 for f in funcs if f[0] > 100), "func_gt200": sum(1 for f in funcs if f[0] > 200),
            "func_gt100_list": [f[1] + f" ({f[0]})" for f in funcs if f[0] > 100],
            "broad_except": broad, "broad_except_silent": silent,
            "silent_ratio": round(silent / broad, 3) if broad else None,
            "bidir_pairs": len(pairs), "bidir_pairs_list": [" <-> ".join(p) for p in pairs],
            "bidir_pairs_excl_parent_child": len(pairs_np),
            "bidir_pairs_incl_type_checking": len(pairs_tc), "bidir_pairs_incl_type_checking_list": [" <-> ".join(p) for p in pairs_tc],
            "orphan_modules": len(orphans), "orphan_list": orphans}


def main():
    a = sys.argv[1:]
    pkg = a[0]
    ex = ()
    if "--exclude" in a:
        ex = tuple(x for x in a[a.index("--exclude") + 1].split(",") if x)
    r = scan(pkg, ex)
    if "--json" in a:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        for k, v in r.items():
            if not k.endswith("_list"):
                print(f"{k}: {v}")


if __name__ == "__main__":
    main()
