# -*- coding: utf-8 -*-
"""C7：全量臂 B_everos 写入进度快照（录像化，供报告引用）：已 flush 批次、插件 LLM 调用/token/费用、
单次提示词长度随记忆增长的轨迹、输出顶到 max_tokens(8192) 的次数、服务日志里的 LLM 超时与非正常结束告警、外联采样结果。"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from harness.recorder import Recorder, render_timeline, load_events  # noqa
out = os.path.join(ROOT, "runs/everos_checks")
rec = Recorder(f"{out}/recording.jsonl", "everos_checks", resume=True)
st = os.path.join(ROOT, "runs/B_everos/everos_state")
prog = json.load(open(f"{st}/ingest_progress.json")) if os.path.exists(f"{st}/ingest_progress.json") else {}
rows = [json.loads(l) for l in open(f"{st}/everos_llm_calls.jsonl")]
ok = [r for r in rows if r.get("status") == 200]
fl = [e for e in load_events(os.path.join(ROOT, "runs/B_everos/recording.jsonl")) if e["type"] == "plugin.flush"]
log = re.sub(r"\x1b\[[0-9;]*m", "", open(os.path.join(ROOT, "runs/sbx/B_everos/server.log"), errors="replace").read())
pc = [r["prompt_chars"] for r in ok]
win = max(1, len(pc) // 8)
traj = [max(pc[i:i + win]) for i in range(0, len(pc), win)]
eg = os.path.join(ROOT, "runs/everos/egress_samples.jsonl")
e = rec.event("check.full_snapshot",
              batches_done=sum(prog.values()), batches_total=698, sessions_started=len(prog), progress=prog,
              flush_events=len(fl), flush_failed=sum(1 for x in fl if x.get("code") != 200),
              flush_s_median=sorted(x["flush_s"] for x in fl)[len(fl) // 2] if fl else None,
              llm_calls=len(rows), llm_ok=len(ok), prompt_tokens=sum(r.get("prompt_tokens") or 0 for r in ok),
              completion_tokens=sum(r.get("completion_tokens") or 0 for r in ok),
              cost_usd=round(sum(float(r.get("cost_usd") or 0) for r in ok), 4),
              prompt_chars_max_by_window=traj, completion_hit_8192=sum(1 for r in ok if (r.get("completion_tokens") or 0) >= 8192),
              server_log={"llm_non_stop_finish": log.count("llm_non_stop_finish"), "APITimeoutError": log.count("APITimeoutError: Request timed out"),
                          "Exception_in_ASGI": log.count("Exception in ASGI application"), "episode_extract_retry": log.count("episode_extract_retry")},
              egress_unique_nonloopback=[json.loads(l) for l in open(eg)] if os.path.exists(eg) else [],
              egress_watch_heartbeat=json.load(open(eg + ".heartbeat")) if os.path.exists(eg + ".heartbeat") else None)
print(json.dumps({k: v for k, v in e.items() if k not in ("progress",)}, ensure_ascii=False))
rec.close(); render_timeline(f"{out}/recording.jsonl", f"{out}/timeline.md")
