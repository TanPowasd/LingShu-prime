"""代码质量：自写 AST 指标（不导入被测代码，只读源文件）。

口径：
  - 范围：legacy 快照 = <root>/lingshu/core/**.py；ng 快照 = <root>/lingshu_ng/**.py（被重写的记忆引擎本体）。
  - 模块行数：物理行数；sloc：非空、非纯注释行。
  - 函数长度：def/async def 的 end_lineno - lineno + 1（嵌套函数单独计，外层也含其行）。
  - 圈复杂度（McCabe）：1 + if/elif/for/while/except/with-assert 之外的分支点：
      If、For、AsyncFor、While、IfExp、ExceptHandler、comprehension 的每个 if、
      BoolOp 的 (操作数-1)、match 的每个 case、Assert；不计 try/else/finally 本身。
  - 重复代码块率：把每个模块规范化为「去首尾空白、去注释、去空行」的行序列，取 6 行滑窗哈希；
    在整个范围内出现 ≥2 次的窗口所覆盖的行 / 全部规范化行。
"""
import ast
import hashlib
import io
import os
import tokenize
from collections import defaultdict

WINDOW = 6


def scope_files(root, impl):
    base = os.path.join(root, "lingshu_ng") if impl == "ng" else os.path.join(root, "lingshu", "core")
    out = []
    for d, _, fs in os.walk(base):
        if "__pycache__" in d:
            continue
        for f in sorted(fs):
            if f.endswith(".py"):
                out.append(os.path.join(d, f))
    return base, sorted(out)


class _CC(ast.NodeVisitor):
    def __init__(self):
        self.n = 1

    def generic_visit(self, node):
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.Assert)):
            self.n += 1
        elif isinstance(node, ast.BoolOp):
            self.n += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            self.n += len(node.ifs)
        elif hasattr(ast, "match_case") and isinstance(node, ast.match_case):
            self.n += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and node is not self.root:
            return  # 嵌套函数单独计
        super().generic_visit(node)


def cyclomatic(fn):
    v = _CC()
    v.root = fn
    v.generic_visit(fn)
    return v.n


def _norm_lines(src):
    """去注释（tokenize）、去首尾空白、去空行。"""
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type != tokenize.COMMENT]
        src2 = tokenize.untokenize(toks)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        src2 = src
    return [l.strip() for l in src2.splitlines() if l.strip()]


def analyze(root, impl):
    base, files = scope_files(root, impl)
    if not files:
        return {"available": False, "scope": os.path.relpath(base, root)}
    mods, funcs = [], []
    windows = defaultdict(list)
    norm_total = 0
    parse_err = []
    for f in files:
        src = open(f, encoding="utf-8").read()
        rel = os.path.relpath(f, root)
        lines = src.splitlines()
        sloc = sum(1 for l in lines if l.strip() and not l.strip().startswith("#"))
        mods.append({"module": rel, "lines": len(lines), "sloc": sloc})
        try:
            tree = ast.parse(src)
        except SyntaxError as ex:
            parse_err.append(f"{rel}: {ex}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append({"func": f"{rel}:{node.name}@{node.lineno}",
                              "len": node.end_lineno - node.lineno + 1, "cc": cyclomatic(node)})
        nl = _norm_lines(src)
        norm_total += len(nl)
        for i in range(len(nl) - WINDOW + 1):
            h = hashlib.md5("\n".join(nl[i:i + WINDOW]).encode()).hexdigest()
            windows[h].append((rel, i))
    dup_lines = set()
    for h, occ in windows.items():
        if len(occ) > 1:
            for rel, i in occ:
                for k in range(WINDOW):
                    dup_lines.add((rel, i + k))
    flen = [x["len"] for x in funcs] or [0]
    top_cc = sorted(funcs, key=lambda x: -x["cc"])[:10]
    return {
        "available": True, "scope": os.path.relpath(base, root),
        "modules": len(mods), "total_lines": sum(m["lines"] for m in mods), "total_sloc": sum(m["sloc"] for m in mods),
        "max_module": max(mods, key=lambda m: m["lines"]),
        "module_lines": sorted(mods, key=lambda m: -m["lines"]),
        "functions": len(funcs), "max_func": max(funcs, key=lambda x: x["len"]) if funcs else None,
        "mean_func_len": round(sum(flen) / max(len(funcs), 1), 2),
        "cc_top10": top_cc, "cc_over_10": sum(1 for x in funcs if x["cc"] > 10),
        "cc_mean": round(sum(x["cc"] for x in funcs) / max(len(funcs), 1), 2),
        "dup_rate": round(len(dup_lines) / max(norm_total, 1), 4),
        "parse_errors": parse_err,
    }
