# -*- coding: utf-8 -*-
"""api_coverage · 旧项目公开 API（lingshu/ 下各模块的 ``__all__``）在 ng 模式下的覆盖清单

  python tests_ng/intent/api_coverage.py <旧树> [--out PATH]

做法：在子进程里按意图守卫同一方式装 ng 别名（ng_all_plugin，LINGSHU_INTENT_IMPL=ng），然后对旧树
``lingshu/`` 下每个 .py 模块：
  * 从**旧源码**用 AST 读出公开名：有 ``__all__`` 用它，否则取顶层不带下划线的 def/class；
  * ``importlib.import_module`` 旧模块名后逐名看：模块本身已换成 ng（``__name__`` 以 lingshu_ng 开头），
    或该名字的对象 ``__module__`` 属 lingshu_ng（world 线按名替换类）⇒ 由 ng 提供；否则仍是旧实现；缺名单列。
状态：ng（全部公开名由 ng 提供）/ ng-partial（部分）/ legacy（ng 模式下仍是旧实现）/ no-public-api /
import-error（ng 模式下导入失败）。结果写 JSON，供 evalsuite/INTENT_FIDELITY.md 引用。
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

CHILD = r'''
import ast, importlib, json, os, sys, warnings
warnings.filterwarnings("ignore")
tree = sys.argv[1]
import ng_all_plugin  # noqa: F401  装别名
out = {}
root = os.path.join(tree, "lingshu")
for dp, dn, fn in os.walk(root):
    dn[:] = sorted(d for d in dn if not d.startswith((".", "__pycache__")))
    for f in sorted(fn):
        if not f.endswith(".py"):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, tree)[:-3].replace(os.sep, ".")
        mod = rel[:-9] if rel.endswith(".__init__") else rel
        src = open(p, encoding="utf-8").read()
        names, has_all = [], False
        try:
            body = ast.parse(src).body
            for node in body:
                if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "__all__" for t in node.targets):
                    names, has_all = [ast.literal_eval(e) for e in node.value.elts], True
            if not has_all:
                names = [n.name for n in body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                         and not n.name.startswith("_")]
        except Exception:
            pass
        rec = {"api_source": "__all__" if has_all else "top-level public def/class", "names": names,
               "lines": src.count(chr(10)) + 1}
        try:
            m = importlib.import_module(mod)
            rec["resolved"] = m.__name__
            mod_ng = m.__name__.startswith("lingshu_ng")
            served, legacy, missing = [], [], []
            for n in names:
                if not hasattr(m, n):
                    missing.append(n)
                    continue
                o = getattr(m, n)
                om = getattr(o, "__module__", None) or ""
                (served if (mod_ng or om.startswith("lingshu_ng")) else legacy).append(n)
            rec.update(ng_names=served, legacy_names=legacy, missing=missing)
        except BaseException as ex:
            rec["error"] = "%s: %s" % (type(ex).__name__, str(ex)[:160])
        out[mod] = rec
print(json.dumps(out, ensure_ascii=False))
'''


def run(tree: str) -> dict:
    """子进程（cwd=旧树）里装 ng 别名后逐模块检查。"""
    env = dict(os.environ, LINGSHU_INTENT_IMPL="ng", PYTHONHASHSEED="0", PYTHONUTF8="1")
    env["PYTHONPATH"] = os.pathsep.join([tree, REPO, HERE])
    p = subprocess.run([sys.executable, "-c", CHILD, tree], cwd=tree, env=env, capture_output=True,
                       text=True, timeout=600)
    if p.returncode != 0:
        raise SystemExit(p.stderr[-2000:])
    raw = json.loads(p.stdout.strip().splitlines()[-1])
    for rec in raw.values():
        if "error" in rec:
            rec["status"] = "import-error"
        elif not rec["names"]:
            rec["status"] = "no-public-api"
        elif not rec["ng_names"]:
            rec["status"] = "legacy"
        elif rec["legacy_names"] or rec["missing"]:
            rec["status"] = "ng-partial"
        else:
            rec["status"] = "ng"
    return raw


def main(argv):
    tree = os.path.abspath(argv[0])
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(
        HERE, f"api_coverage_{os.path.basename(tree)}.json")
    res = run(tree)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    from collections import Counter
    c = Counter(r["status"] for r in res.values())
    print(out, dict(c))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
