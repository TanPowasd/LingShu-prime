# -*- coding: utf-8 -*-
"""出报告前：复制录像进复核包、生成机读读数、跑 validate_report（扣分点录像引用 100%）。"""
import json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from harness.recorder import validate_report, render_timeline, CITE_RE  # noqa
PK = os.path.join(ROOT, "reports/everos_站外复核包")
os.makedirs(PK + "/录像", exist_ok=True)
runs = {"everos_install": "runs/everos_install", "everos_checks": "runs/everos_checks", "everos_probe": "runs/everos_probe",
        "B_everos_smoke": "runs/B_everos_smoke", "B_everos": "runs/B_everos"}
recs = {}
for rid, d in runs.items():
    src = os.path.join(ROOT, d, "recording.jsonl")
    dst = os.path.join(PK, "录像", f"{rid}.jsonl")
    shutil.copyfile(src, dst)
    render_timeline(dst, os.path.join(PK, "录像", f"{rid}_时间轴.md"))
    recs[rid] = dst
# 冒烟臂逐题召回/作答原样
sm = os.path.join(PK, "run_B_everos_smoke")
shutil.rmtree(sm, ignore_errors=True)
shutil.copytree(os.path.join(ROOT, "runs/B_everos_smoke"), sm, ignore=shutil.ignore_patterns("everos_state", "recording.jsonl"))
# 机读读数
r = subprocess.run([sys.executable, os.path.join(HERE, "report_numbers.py")], capture_output=True, text=True)
open(os.path.join(PK, "读数_everos.json"), "w").write(r.stdout)
shutil.copyfile(os.path.join(ROOT, "runs/B_everos/everos_state/ingest_progress.json"), os.path.join(PK, "全量臂写入进度_快照.json"))
# 校验
rep = open(os.path.join(ROOT, "reports/everos_考卷B_草稿.md"), encoding="utf-8").read()
v = validate_report(rep, recs)
allc = list(CITE_RE.finditer(rep))
bad_all = []
from harness.recorder import load_events, mmss
idx = {k: {e["seq"]: e for e in load_events(p)} for k, p in recs.items()}
for m in allc:
    e = idx.get(m.group("run"), {}).get(int(m.group("seq")))
    if not e or mmss(e["t"]) != m.group("mmss"):
        bad_all.append(m.group(0))
res = {"deductions": {k: v[k] for k in ("total", "ok", "coverage", "pass")}, "problems": v["problems"],
       "all_citations": len(allc), "all_citations_bad": bad_all}
json.dump(res, open(os.path.join(PK, "录像引用校验_报告草稿.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False))
