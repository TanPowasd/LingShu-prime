# -*- coding: utf-8 -*-
"""旧 world 测试在 compat 下的通过率（旧断言零改动）。

对每个文件跑两遍：legacy（旧实现）与 ng（compat 别名）。pytest 式文件按用例计数，
脚本式文件（无 test_ 函数，靠 __main__）按退出码计、并解析「N/M 通过」子项。
输出 tests_ng/world/legacy_compat_result.json。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WT = os.path.join(os.path.dirname(REPO), "wt-gen-world", "tests")

MAIN = ["test_world3d_add_vprim_pose.py", "test_world3d_box_backface.py",
        "test_world3d_camera_depth.py", "test_world3d_part_order.py",
        "test_world3d_pyramid_apex.py", "test_vprim_overlap_scale.py",
        "test_scene_model_skeleton_channel.py", "test_silhouette_joint_names.py",
        "test_scene_follow_patrol.py", "test_spacetime_invariant_verdict.py",
        "test_world_model_edge_supersede.py", "test_world_learner_oracle_rate.py",
        "test_wm_simloop_load_priors.py", "test_wm_verify_unobserved.py",
        "test_prediction_d006_threshold.py", "test_brain_store.py", "test_dedup_shims.py"]
EXTRA = ["test_skeleton_fk_order_guard.py", "test_world_seed.py", "test_scene_relations.py"]


def _env(impl: str) -> dict:
    env = dict(os.environ, LINGSHU_WORLD_IMPL=impl, PYTHONHASHSEED="0")
    env["PYTHONPATH"] = os.pathsep.join([REPO, HERE])
    return env


def _is_pytest_file(path: str) -> bool:
    return re.search(r"^def test_", open(path, encoding="utf-8").read(), re.M) is not None


def run_pytest(path: str, impl: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as t:
        xml = t.name
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "legacy_plugin", "-p", "no:cacheprovider",
           "--junitxml", xml, path]
    p = subprocess.run(cmd, cwd=os.path.dirname(path), env=_env(impl), capture_output=True,
                       text=True, timeout=600)
    s = ET.parse(xml).getroot()
    s = s if s.tag == "testsuite" else s[0]
    tot, bad = int(s.get("tests")), int(s.get("failures")) + int(s.get("errors"))
    fails = [c.get("name") for c in s.iter("testcase") if c.find("failure") is not None
             or c.find("error") is not None]
    return {"kind": "pytest", "total": tot, "passed": tot - bad - int(s.get("skipped")),
            "failed_cases": fails}


def run_script(path: str, impl: str) -> dict:
    code = ("import legacy_plugin, runpy, sys; sys.argv=[%r]; "
            "runpy.run_path(%r, run_name='__main__')" % (path, path))
    p = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(path), env=_env(impl),
                       capture_output=True, text=True, timeout=600)
    out = p.stdout + p.stderr
    m = re.findall(r"(\d+)/(\d+)\s*通过", out)
    sub = [int(m[-1][0]), int(m[-1][1])] if m else None
    fails = [ln.strip() for ln in out.splitlines() if re.match(r"\s*(\[FAIL\]|FAIL )", ln)]
    return {"kind": "script", "total": 1, "passed": int(p.returncode == 0),
            "subchecks": sub, "failed_cases": fails[:10]}


def run(path: str, impl: str) -> dict:
    return run_pytest(path, impl) if _is_pytest_file(path) else run_script(path, impl)


def summarize(rows: list, impl: str) -> dict:
    tot = sum(r[impl]["total"] for r in rows)
    ok = sum(r[impl]["passed"] for r in rows)
    return {"passed": ok, "total": tot, "rate": round(ok / tot, 4) if tot else None}


def main() -> int:
    result = {}
    for group, base, files in (("main", os.path.join(REPO, "tests"), MAIN), ("extra_wt_gen_world", WT, EXTRA)):
        rows = []
        for f in files:
            path = os.path.join(base, f)
            if not os.path.exists(path):
                continue
            row = {"file": f, "legacy": run(path, "legacy"), "ng": run(path, "ng")}
            rows.append(row)
            print("%-42s legacy %s/%s   ng %s/%s" % (f, row["legacy"]["passed"], row["legacy"]["total"],
                                                    row["ng"]["passed"], row["ng"]["total"]))
        result[group] = {"files": rows, "legacy": summarize(rows, "legacy"), "ng": summarize(rows, "ng")}
        print(group, result[group]["legacy"], result[group]["ng"])
    with open(os.path.join(HERE, "legacy_compat_result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
