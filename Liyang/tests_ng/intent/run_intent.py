# -*- coding: utf-8 -*-
"""run_intent · 旧项目自己的测试在 ng 上（意图守卫）

对旧工作树 tests/ 下每个文件，在该树内以 ng_all_plugin 跑（ng / legacy 两种实现）。
pytest 式按用例（junitxml）；脚本式（无 def test_）按退出码 1 例，并解析 PASS/FAIL 子项。

  python tests_ng/intent/run_intent.py <tree> <impl> [--files a.py,b.py] [--out PATH] [--timeout S]
结果按文件增量写入 tests_ng/intent/result_<treename>_<impl>.json（可分段续跑）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def env(tree: str, impl: str) -> dict:
    e = dict(os.environ, LINGSHU_INTENT_IMPL=impl, PYTHONHASHSEED="0",
             OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    e["PYTHONPATH"] = os.pathsep.join([tree, REPO, HERE])
    e.pop("LINGSHU_IMPL", None)
    return e


def is_pytest(path: str) -> bool:
    return re.search(r"^\s*def test_", open(path, encoding="utf-8").read(), re.M) is not None


def run_pytest(tree, path, impl, timeout):
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as t:
        xml = t.name
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "ng_all_plugin", "-p", "no:cacheprovider",
           "--junitxml", xml, "-o", "junit_family=xunit1", path]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=tree, env=env(tree, impl), capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"kind": "pytest", "total": 1, "passed": 0, "failed_cases": ["<timeout>"],
                "seconds": timeout}
    try:
        s = ET.parse(xml).getroot()
    except Exception:
        return {"kind": "pytest", "total": 1, "passed": 0, "failed_cases": ["<no-xml>"],
                "tail": (p.stdout + p.stderr)[-1500:], "seconds": round(time.time() - t0, 1)}
    s = s if s.tag == "testsuite" else s[0]
    tot = int(s.get("tests"))
    skipped = int(s.get("skipped") or 0)
    fails, msgs = [], {}
    for c in s.iter("testcase"):
        bad = c.find("failure") if c.find("failure") is not None else c.find("error")
        if bad is not None:
            n = c.get("name")
            fails.append(n)
            msgs[n] = ((bad.get("message") or "") + "\n" + (bad.text or ""))[-1200:]
    if tot == 0 and p.returncode not in (0, 5):
        return {"kind": "pytest", "total": 1, "passed": 0, "failed_cases": ["<collect-error>"],
                "tail": (p.stdout + p.stderr)[-1500:], "seconds": round(time.time() - t0, 1)}
    return {"kind": "pytest", "total": tot - skipped, "passed": tot - skipped - len(fails),
            "skipped": skipped, "failed_cases": fails, "messages": msgs,
            "seconds": round(time.time() - t0, 1)}


def run_script(tree, path, impl, timeout):
    code = ("import ng_all_plugin, runpy, sys; sys.argv=[%r]; "
            "runpy.run_path(%r, run_name='__main__')" % (path, path))
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-c", code], cwd=tree, env=env(tree, impl),
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"kind": "script", "total": 1, "passed": 0, "failed_cases": ["<timeout>"],
                "seconds": timeout}
    out = p.stdout + p.stderr
    ok = len(re.findall(r"^\s*(?:\[PASS\]|PASS\b|✓|\[OK\])", out, re.M))
    bad = re.findall(r"^\s*(?:\[FAIL\]|FAIL\b|✗)(.*)$", out, re.M)
    return {"kind": "script", "total": 1, "passed": int(p.returncode == 0),
            "failed_cases": [] if p.returncode == 0 else ["<script rc=%d>" % p.returncode],
            "sub": [ok, ok + len(bad)], "sub_failed": [b.strip()[:200] for b in bad][:15],
            "tail": out[-1500:] if p.returncode else "", "seconds": round(time.time() - t0, 1)}


def main(argv):
    tree, impl = os.path.abspath(argv[0]), argv[1]
    files, timeout, out = None, 900, None
    i = 2
    while i < len(argv):
        if argv[i] == "--files":
            files = argv[i + 1].split(","); i += 2
        elif argv[i] == "--timeout":
            timeout = int(argv[i + 1]); i += 2
        elif argv[i] == "--out":
            out = argv[i + 1]; i += 2
        else:
            raise SystemExit("unknown arg " + argv[i])
    name = os.path.basename(tree)
    out = out or os.path.join(HERE, f"result_{name}_{impl}.json")
    res = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {}
    tdir = os.path.join(tree, "tests")
    files = files or sorted(f for f in os.listdir(tdir) if f.startswith("test_") and f.endswith(".py"))
    for f in files:
        path = os.path.join(tdir, f)
        r = run_pytest(tree, path, impl, timeout) if is_pytest(path) else run_script(tree, path, impl, timeout)
        res[f] = r
        print("%-55s %-6s %s/%s %ss" % (f, impl, r["passed"], r["total"], r.get("seconds")), flush=True)
        json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
