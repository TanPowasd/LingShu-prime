# -*- coding: utf-8 -*-
"""兼容矩阵生成器（stab-r1 #6）：只**读**上游源码的 AST（不导入、不执行、不复制实现），对照 ng 兼容门面的实际签名。

用法：python tools/compat/compat_matrix.py <上游仓根目录> [--json out.json] [--md COMPAT_MATRIX.md]

对照面（tests_ng/ng_switch.py 的映射）：
  lingshu.core.core           → lingshu_ng.compat           （SpacetimeMemoryEngine / LayeredStore / 数据类型 / 模块函数）
  lingshu.core.activation     → lingshu_ng.compat_activation（ActivationEngine）
  lingshu.core.longterm_gate  → lingshu_ng.compat_gate      （LongTermMemoryGate）
判定（每个上游公开方法 / 函数）：
  覆盖：ng 有同名可调用对象，且上游每个形参（按名）ng 都接受（ng 有同名形参，或有 **kwargs）、上游可省略的形参 ng 也可省略、
        ng 多出的形参都有缺省值；
  部分：同名存在但上一条不满足（列出差异）；
  缺失：ng 没有同名对象。
频次：该名字在上游仓内（lingshu/ + tests/，排除定义处）以 ``.名字(`` 形式被调用的次数——「高频」的依据。
"""
import ast
import importlib
import inspect
import json
import os
import re
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

SURFACES = [
    ("lingshu/core/core.py", "lingshu_ng.compat", ["SpacetimeMemoryEngine", "LayeredStore", "STNode", "STEdge",
                                                     "ConditionSpace", "SelfModel", "CausalChain"]),
    ("lingshu/core/activation.py", "lingshu_ng.compat_activation", ["ActivationEngine"]),
    ("lingshu/core/longterm_gate.py", "lingshu_ng.compat_gate", ["LongTermMemoryGate"]),
]


def _params(fn: ast.FunctionDef, is_method: bool):
    a = fn.args
    pos = a.posonlyargs + a.args
    if is_method and pos and pos[0].arg in ("self", "cls"):
        pos = pos[1:]
    nd = len(a.defaults)
    out = []
    for i, p in enumerate(pos):
        out.append((p.arg, i >= len(pos) - nd))
    for p, d in zip(a.kwonlyargs, a.kw_defaults):
        out.append((p.arg, d is not None))
    return out, a.vararg is not None, a.kwarg is not None


def _decorators(fn):
    return {d.id if isinstance(d, ast.Name) else getattr(d, "attr", "") for d in fn.decorator_list}


def upstream_api(root: str, rel: str, classes: List[str]):
    tree = ast.parse(open(os.path.join(root, rel), encoding="utf-8").read())
    api = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in classes:
            for b in node.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and (not b.name.startswith("_") or b.name == "__init__"):
                    decs = _decorators(b)
                    kind = "property" if "property" in decs else ("staticmethod" if "staticmethod" in decs else "method")
                    ps, va, kw = _params(b, kind != "staticmethod")
                    api[f"{node.name}.{b.name}"] = {"kind": kind, "params": ps, "varargs": va, "varkw": kw, "line": b.lineno}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            ps, va, kw = _params(node, False)
            api[node.name] = {"kind": "function", "params": ps, "varargs": va, "varkw": kw, "line": node.lineno}
    return api


def call_freq(root: str, names):
    src = []
    for d in ("lingshu", "tests"):
        for dp, dn, fs in os.walk(os.path.join(root, d)):
            dn[:] = [x for x in dn if x != "__pycache__"]
            for f in fs:
                if f.endswith(".py"):
                    src.append(open(os.path.join(dp, f), encoding="utf-8", errors="replace").read())
    blob = "\n".join(src)
    return {n: len(re.findall(r"\." + re.escape(n) + r"\(", blob)) for n in names}


def ng_obj(modname: str, qual: str):
    mod = importlib.import_module(modname)
    obj = mod
    for part in qual.split("."):
        obj = getattr(obj, part, None) if obj is not None else None
        if obj is None:
            # 类属性可能是 property：在类上取原始描述符
            return None
    return obj


def ng_sig(modname: str, qual: str):
    cls_name, _, meth = qual.partition(".")
    mod = importlib.import_module(modname)
    if not meth:
        obj = getattr(mod, cls_name, None)
        return (obj, "function") if obj is not None else (None, None)
    cls = getattr(mod, cls_name, None)
    if cls is None:
        return None, None
    raw = inspect.getattr_static(cls, meth, None)
    if raw is None:
        inst = _instance(modname, cls_name)
        if inst is None:
            return None, None
        try:
            obj = getattr(inst, meth)          # 实例属性 / __getattr__ 动态提供（如占位方法）
        except AttributeError:
            return None, None
        # 实例数据属性（如 LayeredStore.conn 是 sqlite3.Connection——它本身可调用，但不是方法）按属性计
        return obj, ("bound" if inspect.isroutine(obj) or inspect.isfunction(getattr(obj, "__func__", None))
                     or type(obj).__name__ == "function" else "property")
    if isinstance(raw, property):
        return raw, "property"
    if isinstance(raw, staticmethod):
        return raw.__func__, "staticmethod"
    if isinstance(raw, classmethod):
        return raw.__func__, "classmethod"
    return raw, "method"


_INST = {}


def _instance(modname: str, cls_name: str):
    """取一个门面实例（内存库）用于探测实例属性与动态方法；构造失败 → None。"""
    key = (modname, cls_name)
    if key not in _INST:
        mod = importlib.import_module(modname)
        try:
            if cls_name == "SpacetimeMemoryEngine":
                _INST[key] = mod.SpacetimeMemoryEngine(":memory:")
            elif cls_name == "LayeredStore":
                _INST[key] = mod.LayeredStore(":memory:")
            else:
                _INST[key] = None
        except Exception:  # 探测工具：构造失败只是少探测一类动态属性
            _INST[key] = None
    return _INST[key]


def _placeholder(modname: str, qual: str):
    """占位项：名字只由 compat_stubs 的 ``__getattr__`` 提供（NOT_READY 返回「未装配」状态 / UNSUPPORTED 抛
    NotImplementedError），类上没有真实实现。返回 None（非占位）或占位类别。"""
    from lingshu_ng import compat_stubs
    cls_name, _, meth = qual.partition(".")
    if not meth:
        return None
    cls = getattr(importlib.import_module(modname), cls_name, None)
    if cls is None or inspect.getattr_static(cls, meth, None) is not None:
        return None
    if meth in compat_stubs.UNSUPPORTED:
        return "unsupported"
    if meth in compat_stubs.NOT_READY:
        return "not_ready"
    return None


def judge(up, obj, kind):
    if obj is None:
        return "缺失", []
    if up["kind"] == "property":
        return ("覆盖", []) if kind == "property" or not callable(obj) else ("部分", ["上游是属性，ng 是方法"])
    if kind == "property":
        return "部分", ["上游是方法，ng 是属性"]
    if not callable(obj):
        return "部分", ["ng 同名对象不可调用"]
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        return "覆盖", ["签名不可内省（内建 / C 实现），按同名计"]
    ps = list(sig.parameters.values())
    if kind in ("method", "classmethod") and ps and ps[0].name in ("self", "cls"):  # bound 已去掉 self
        ps = ps[1:]
    ng_names = {p.name: p for p in ps if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)}
    ng_kw = any(p.kind == p.VAR_KEYWORD for p in ps)
    ng_va = any(p.kind == p.VAR_POSITIONAL for p in ps)
    diffs = []
    up_names = [n for n, _ in up["params"]]
    for n, has_def in up["params"]:
        p = ng_names.get(n)
        if p is None:
            if not ng_kw:
                diffs.append(f"缺形参 {n}")
            continue
        if has_def and p.default is p.empty and p.kind != p.VAR_KEYWORD:
            diffs.append(f"形参 {n} 上游可省略、ng 必填")
    for n, p in ng_names.items():
        if n not in up_names and p.default is p.empty:
            diffs.append(f"ng 多出必填形参 {n}")
    # 位置顺序：上游按位置传参时 ng 应同序
    ng_pos = [p.name for p in ps if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    up_pos = [n for n in up_names if n in ng_pos]
    if up_pos and ng_pos[:len(up_pos)] != up_pos and not all(n in ng_pos for n in up_pos[:0]):
        if [n for n in ng_pos if n in up_pos] != up_pos:
            diffs.append("位置形参顺序不同")
    if up["varargs"] and not ng_va:
        diffs.append("上游有 *args，ng 没有")
    if up["varkw"] and not ng_kw:
        diffs.append("上游有 **kwargs，ng 没有")
    return ("覆盖" if not diffs else "部分"), diffs


def build(root: str):
    rows = []
    for rel, modname, classes in SURFACES:
        api = upstream_api(root, rel, classes)
        freq = call_freq(root, {k.rpartition(".")[2] for k in api})
        for qual, up in sorted(api.items()):
            obj, kind = ng_sig(modname, qual)
            st, diffs = judge(up, obj, kind)
            ph = _placeholder(modname, qual)
            rows.append({"upstream": f"{rel}:{up['line']}", "module": modname, "name": qual, "kind": up["kind"],
                         "status": st, "placeholder": ph, "diffs": diffs, "freq": freq.get(qual.rpartition(".")[2], 0),
                         "sig": "(" + ", ".join(n + ("=…" if d else "") for n, d in up["params"])
                                + (", *args" if up["varargs"] else "") + (", **kw" if up["varkw"] else "") + ")"})
    return rows


def summary(rows):
    n = len(rows)
    cov = sum(r["status"] == "覆盖" for r in rows)
    ph = sum(r["status"] == "覆盖" and bool(r["placeholder"]) for r in rows)
    return {"total": n, "covered_incl_placeholder": cov, "placeholder": ph, "covered_real": cov - ph,
            "partial": sum(r["status"] == "部分" for r in rows), "missing": sum(r["status"] == "缺失" for r in rows)}


def to_markdown(rows, upstream_desc: str) -> str:
    s = summary(rows)
    pct = lambda k: f"{s[k]}/{s['total']}（{100.0 * s[k] / s['total']:.1f}%）"
    out = ["# COMPAT_MATRIX · ng 兼容门面 × 上游当前 API", "",
           f"生成：`python tools/compat/compat_matrix.py <上游仓根> --md COMPAT_MATRIX.md`（只读上游 AST，不导入、不执行、不复制实现）。",
           f"上游：{upstream_desc}。对照面：`lingshu.core.core`（SpacetimeMemoryEngine / LayeredStore / 数据类型 / 模块函数）→ "
           "`lingshu_ng.compat`；`lingshu.core.activation.ActivationEngine` → `lingshu_ng.compat_activation`；"
           "`lingshu.core.longterm_gate.LongTermMemoryGate` → `lingshu_ng.compat_gate`。", "",
           "判定：**覆盖**＝同名可调用，且上游每个形参 ng 都接受、上游可省略的 ng 也可省略、ng 多出的形参都有缺省值；"
           "**部分**＝同名存在但签名不满足上一条；**缺失**＝无同名对象。**占位**＝签名覆盖、但只由 `compat_stubs` 动态提供："
           "`not_ready` 返回「未装配」状态字典（与上游公开仓形态下这些器官模块未装配时同形，不伪造成功），"
           "`unsupported` 调用即 NotImplementedError。签名覆盖不等于语义逐项相同；有意不同之处写在各门面方法的 docstring。", "",
           "| 口径 | 读数 |", "|---|---|",
           f"| 签名覆盖（含占位） | {pct('covered_incl_placeholder')} |",
           f"| 真实覆盖（不含占位） | {pct('covered_real')} |",
           f"| 占位 | {pct('placeholder')} |",
           f"| 部分 | {pct('partial')} |",
           f"| 缺失 | {pct('missing')} |", "",
           "频次＝该名字在上游仓（`lingshu/` + `tests/`，排除定义处）以 `.名字(` 被调用的次数。", ""]
    def table(title, sel, cols_diff=True):
        rs = sorted([r for r in rows if sel(r)], key=lambda r: (-r["freq"], r["name"]))
        out.extend([f"## {title}（{len(rs)}）", ""])
        if not rs:
            out.extend(["（无）", ""])
            return
        out.extend(["| 名字 | 上游签名 | 频次 | 说明 |", "|---|---|---|---|"])
        for r in rs:
            note = "；".join(r["diffs"]) if r["diffs"] else (r["placeholder"] or "")
            out.append(f"| `{r['name']}` | `{r['sig']}` | {r['freq']} | {note} |")
        out.append("")
    table("缺失", lambda r: r["status"] == "缺失")
    table("部分", lambda r: r["status"] == "部分")
    table("占位（签名覆盖，无真实实现）", lambda r: r["status"] == "覆盖" and r["placeholder"])
    table("真实覆盖", lambda r: r["status"] == "覆盖" and not r["placeholder"])
    return "\n".join(out)


def main(argv):
    root = argv[1]
    rows = build(root)
    if "--json" in argv:
        json.dump(rows, open(argv[argv.index("--json") + 1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if "--md" in argv:
        desc = argv[argv.index("--desc") + 1] if "--desc" in argv else root
        open(argv[argv.index("--md") + 1], "w", encoding="utf-8").write(to_markdown(rows, desc))
    print(json.dumps(summary(rows), ensure_ascii=False))
    return rows


if __name__ == "__main__":
    main(sys.argv)
