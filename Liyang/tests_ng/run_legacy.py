# -*- coding: utf-8 -*-
"""run_legacy · 在指定实现（legacy / ng）下跑 tests/ 里的 core 相关测试并汇总

用法：
  python tests_ng/run_legacy.py            # 按环境变量 LINGSHU_IMPL（默认 legacy）
  LINGSHU_IMPL=ng python tests_ng/run_legacy.py --json out.json

两类旧测试：
  * pytest 式：子进程 ``python -m pytest -p tests_ng.ng_plugin``，按用例计数；
  * 脚本式（test_core_export_all / test_issue145_*，pytest 收集 0 条）：子进程导入模块并
    依次执行其 group_* 函数，读取模块内 _PASS/_FAIL 断言清单计数。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = os.path.join(ROOT, "tests_ng", "legacy_core_tests.txt")
SCRIPT_STYLE = ("tests/test_core_export_all.py", "tests/test_issue145_causal_depth_cycles.py")

_SCRIPT_DRIVER = r"""
import importlib.util, json, os, sys
sys.path.insert(0, os.getcwd())
from tests_ng import ng_switch
if ng_switch.enabled():
    ng_switch.install()
spec = importlib.util.spec_from_file_location("legacy_script", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
errors = []
for name in sorted(n for n in dir(m) if n.startswith("group_")):
    try:
        getattr(m, name)()
    except Exception as exc:
        errors.append(f"{name}: {type(exc).__name__}: {exc}")
print("@@RESULT@@" + json.dumps({"pass": list(m._PASS), "fail": list(m._FAIL), "errors": errors},
                                ensure_ascii=False))
"""


def run_pytest(files: List[str]) -> Dict:
    """pytest 式测试：返回 {passed, failed, failures:[nodeid]}。"""
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "tests_ng.ng_plugin",
           "-rf", *files]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout
    failures = re.findall(r"^FAILED (\S+)", out, re.M)
    m = re.search(r"(\d+) passed", out)
    f = re.search(r"(\d+) failed", out)
    return {"passed": int(m.group(1)) if m else 0, "failed": int(f.group(1)) if f else 0,
            "failures": failures}


def run_script(path: str) -> Dict:
    """脚本式测试：返回断言级 {passed, failed, failures, errors}。"""
    out = subprocess.run([sys.executable, "-c", _SCRIPT_DRIVER, path], cwd=ROOT,
                         capture_output=True, text=True)
    line = next((l for l in out.stdout.splitlines() if l.startswith("@@RESULT@@")), None)
    if line is None:
        return {"passed": 0, "failed": 1, "failures": [f"{path}: 无法运行"], "errors": [out.stderr[-2000:]]}
    r = json.loads(line[len("@@RESULT@@"):])
    return {"passed": len(r["pass"]), "failed": len(r["fail"]) + len(r["errors"]),
            "failures": [f"{path}::{x}" for x in r["fail"]], "errors": r["errors"]}


def main(argv: List[str]) -> int:
    """跑全部并打印汇总；--json PATH 落盘明细。"""
    files = [l.strip() for l in open(LIST, encoding="utf-8") if l.strip()]
    py = [f for f in files if f not in SCRIPT_STYLE]
    report = {"impl": os.environ.get("LINGSHU_IMPL", "legacy") or "legacy", "pytest": run_pytest(py),
              "scripts": {s: run_script(s) for s in SCRIPT_STYLE}}
    tp = report["pytest"]["passed"] + sum(v["passed"] for v in report["scripts"].values())
    tf = report["pytest"]["failed"] + sum(v["failed"] for v in report["scripts"].values())
    report["total"] = {"passed": tp, "failed": tf, "rate": round(tp / max(1, tp + tf), 4)}
    print(json.dumps(report["total"], ensure_ascii=False), report["impl"])
    for k in ("pytest",):
        for x in report[k]["failures"]:
            print("  FAIL", x)
    for s, v in report["scripts"].items():
        print(f"  [script] {s}: {v['passed']} passed / {v['failed']} failed")
        for x in v["failures"] + v.get("errors", []):
            print("    FAIL", x)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
