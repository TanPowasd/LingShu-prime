# -*- coding: utf-8 -*-
"""零散核对（录像）：对正在跑的 EverOS 服务做只读请求，不写入。录像 runs/everos_checks/recording.jsonl。
C1：search 不写 method（API 缺省值）在 Tier 1 一键档下的返回。
C2：/health 能力矩阵。"""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from harness.recorder import Recorder, render_timeline  # noqa
port = sys.argv[1] if len(sys.argv) > 1 else "18780"
out = os.path.join(ROOT, "runs/everos_checks")
rec = Recorder(f"{out}/recording.jsonl", "everos_checks", resume=os.path.exists(f"{out}/recording.jsonl"))
env = {k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy")}
def run(step, cmd, note):
    rec.event("cmd.start", step=step, cmd=cmd, note=note)
    t0 = time.monotonic(); p = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, timeout=60)
    e = rec.event("cmd.end", step=step, rc=p.returncode, stdout=p.stdout[-6000:], stderr=p.stderr[-2000:], dur_s=round(time.monotonic() - t0, 3))
    print(step, e["seq"], p.stdout[:600])
run("C1", f"""curl -s -w '\\nHTTP %{{http_code}}\\n' -X POST http://127.0.0.1:{port}/api/v2/memory/search -H 'Content-Type: application/json' -d '{{"user_id":"pes-user","app_id":"dsh","project_id":"pes-examb","query":"信任协议","top_k":5}}'""",
    "不写 method（API 缺省），一键档（无嵌入）")
run("C2", f"curl -s http://127.0.0.1:{port}/health", "能力矩阵")
rec.close(); render_timeline(f"{out}/recording.jsonl", f"{out}/timeline.md")
