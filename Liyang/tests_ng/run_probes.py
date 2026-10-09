# -*- coding: utf-8 -*-
"""run_probes · 在 ng 开关下跑缺陷探针（bench/probes/core-* 与修补线的 issue-* 探针），汇总 BUG/OK

用法：python tests_ng/run_probes.py [探针目录 ...] [--json out.json]
探针约定：末行以 OK 或 BUG 开头（见 bench/probes/*.py）。每个探针在独立子进程中运行。
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = ("import sys, runpy; sys.path.insert(0, {root!r}); from tests_ng import ng_switch; "
          "ng_switch.install(); sys.argv=[{p!r}]; runpy.run_path({p!r}, run_name='__main__')")


def run(path: str, ng: bool) -> str:
    """跑一个探针，返回末行（超时/异常也如实返回）。"""
    code = DRIVER.format(root=ROOT, p=path) if ng else f"import runpy,sys; sys.path.insert(0,{ROOT!r}); sys.argv=[{path!r}]; runpy.run_path({path!r}, run_name='__main__')"
    try:
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    lines = (out.stdout.strip() or out.stderr.strip() or "?").splitlines()
    return lines[-1][:160]


def main(argv):
    dirs = [a for a in argv if not a.startswith("--") and not a.endswith(".json")] or [os.path.join(ROOT, "bench", "probes")]
    probes = sorted(p for d in dirs for p in glob.glob(os.path.join(d, "*.py"))
                    if os.path.basename(p).startswith(("core-", "issue-")))
    rows = [{"probe": os.path.relpath(p, ROOT), "legacy": run(p, False), "ng": run(p, True)} for p in probes]
    for r in rows:
        print(f"{r['probe']:<55} legacy={r['legacy'][:40]:<42} ng={r['ng'][:60]}")
    ok = sum(r["ng"].startswith("OK") for r in rows)
    print(f"ng OK {ok}/{len(rows)}；legacy OK {sum(r['legacy'].startswith('OK') for r in rows)}/{len(rows)}")
    if "--json" in argv:
        json.dump(rows, open(argv[argv.index("--json") + 1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
