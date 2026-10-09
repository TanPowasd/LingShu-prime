# -*- coding: utf-8 -*-
"""旧 nn 测试在 compat 下的通过率（旧断言零改动）。

对每个旧测试文件跑两遍：legacy（旧 lingshu.nn）与 ng（导入钩子把 lingshu.nn.* 指向
lingshu_ng.nn.compat.*）。计数两种口径：
- 用例口径：pytest 式文件按用例（junitxml）；纯脚本式文件（test_hex_cnn）按 1 个用例（退出码）；
- 子项口径：脚本模式运行，统计输出中的 PASS/FAIL 行（test_hex_gen / test_hex_composite /
  test_hex_cnn 的 run_checks 子判据都在这里展开）。

用法：python tests_ng/nn/run_legacy_compat.py [legacy|ng|both|merge] [文件名...]
单实现运行写 tests_ng/nn/legacy_compat_<impl>.json（可两个实现并行跑）；
``merge`` 合并为 tests_ng/nn/legacy_compat_result.json 并给出汇总。
子项口径只对有 run_checks 的文件与纯脚本 test_hex_cnn 运行（其余文件的 __main__ 只是 pytest.main）。
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
TESTS = os.path.join(REPO, "tests")
OUT = os.path.join(HERE, "legacy_compat_result.json")
FILES = ["test_hex_cnn.py", "test_hex_composite.py", "test_hex_gen.py",
         "test_hex_gen_background_words.py", "test_hex_gen_constructive_pixels.py",
         "test_hex_gen_shape_words.py", "test_hex_hier.py", "test_hex_ortho.py",
         "test_hex_recon_zorder.py", "test_hex_search.py", "test_hex_text.py",
         "test_hex_train.py", "test_stcnn_memory_consistency.py",
         "test_stcnn_scale_invariance.py", "test_stcnn_time_anchor.py",
         "test_rust_bridge_plan.py"]


def _env(impl: str) -> dict:
    # 单线程 BLAS：共享 2 核沙箱上多线程 OpenBLAS 互相抢核，细长 GEMM 慢 20 倍（新旧实现同一设置）
    env = dict(os.environ, LINGSHU_NN_IMPL=impl, PYTHONHASHSEED="0", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    env["PYTHONPATH"] = os.pathsep.join([REPO, HERE])
    return env


def _has_pytest_cases(path: str) -> bool:
    return re.search(r"^def test_", open(path, encoding="utf-8").read(), re.M) is not None


def run_pytest(path: str, impl: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as t:
        xml = t.name
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "nn_legacy_plugin", "-p", "no:cacheprovider",
           "--junitxml", xml, path]
    t0 = time.time()
    subprocess.run(cmd, cwd=TESTS, env=_env(impl), capture_output=True, text=True, timeout=3000)
    s = ET.parse(xml).getroot()
    s = s if s.tag == "testsuite" else s[0]
    tot, bad = int(s.get("tests")), int(s.get("failures")) + int(s.get("errors"))
    fails = [c.get("name") for c in s.iter("testcase")
             if c.find("failure") is not None or c.find("error") is not None]
    return {"total": tot, "passed": tot - bad - int(s.get("skipped")), "failed_cases": fails,
            "seconds": round(time.time() - t0, 1)}


def run_script(path: str, impl: str) -> dict:
    code = ("import nn_legacy_plugin, runpy, sys; sys.argv=[%r]; "
            "runpy.run_path(%r, run_name='__main__')" % (path, path))
    t0 = time.time()
    p = subprocess.run([sys.executable, "-c", code], cwd=TESTS, env=_env(impl),
                       capture_output=True, text=True, timeout=3000)
    out = p.stdout + p.stderr
    ok = len(re.findall(r"^\s*(?:\[PASS\]|PASS )", out, re.M))
    bad = re.findall(r"^\s*(?:\[FAIL\]|FAIL )(.*)$", out, re.M)
    return {"rc": p.returncode, "sub_passed": ok, "sub_total": ok + len(bad),
            "sub_failed": [b.strip()[:160] for b in bad][:12],
            "tail": out.strip().splitlines()[-3:] if p.returncode else [],
            "seconds": round(time.time() - t0, 1)}


def run_file(name: str, impl: str) -> dict:
    path = os.path.join(TESTS, name)
    row = {}
    if _has_pytest_cases(path):
        row["cases"] = run_pytest(path, impl)
    if "run_checks" in open(path, encoding="utf-8").read() or "cases" not in row:
        row["script"] = run_script(path, impl)
        if "cases" not in row:
            row["cases"] = {"total": 1, "passed": int(row["script"]["rc"] == 0),
                            "failed_cases": [] if row["script"]["rc"] == 0 else ["<script>"]}
    return row


def summarize(result: dict, impl: str) -> dict:
    rows = [r[impl] for r in result.values() if impl in r]
    ct = sum(r["cases"]["total"] for r in rows)
    cp = sum(r["cases"]["passed"] for r in rows)
    st = sum(r["script"]["sub_total"] for r in rows if "script" in r)
    sp = sum(r["script"]["sub_passed"] for r in rows if "script" in r)
    return {"cases": [cp, ct, round(cp / ct, 4) if ct else None],
            "script_subchecks": [sp, st, round(sp / st, 4) if st else None]}


def _part(impl: str) -> str:
    return os.path.join(HERE, f"legacy_compat_{impl}.json")


def merge() -> dict:
    """合并两个实现的分文件结果（按 FILES 顺序）并汇总。"""
    files: dict = {}
    for impl in ("legacy", "ng"):
        if os.path.exists(_part(impl)):
            for name, row in json.load(open(_part(impl), encoding="utf-8")).items():
                files.setdefault(name, {})[impl] = row
    files = {n: files[n] for n in FILES if n in files}
    result = {"files": files, "summary": {impl: summarize(files, impl) for impl in ("legacy", "ng")}}
    json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return result


def main(argv: list) -> int:
    mode = argv[0] if argv else "both"
    if mode == "merge":
        print(json.dumps(merge()["summary"], ensure_ascii=False))
        return 0
    impls = ["legacy", "ng"] if mode == "both" else [mode]
    names = argv[1:] or FILES
    for impl in impls:
        part = json.load(open(_part(impl), encoding="utf-8")) if os.path.exists(_part(impl)) else {}
        for name in names:
            part[name] = run_file(name, impl)
            c = part[name]["cases"]
            print("%-40s %-6s %s/%s" % (name, impl, c["passed"], c["total"]), flush=True)
            json.dump(part, open(_part(impl), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(merge()["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
