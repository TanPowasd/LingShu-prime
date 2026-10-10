"""EverOS 全量臂进度快照（只读）：python -m tools.everos_status
批次（ingest_progress.json）、插件 LLM 调用/token/USD（everos_llm_calls.jsonl，考场侧转发器逐次记账）、
录像里的 flush 失败/重试、最近 flush 的提示词规模。不打印任何密钥或提示词正文。"""
import collections, json, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "runs" / "B_everos"
st = R / "everos_state"
prog = json.loads((st / "ingest_progress.json").read_text(encoding="utf-8"))
calls = [json.loads(l) for l in (st / "everos_llm_calls.jsonl").open(encoding="utf-8") if l.strip()]
ev = collections.Counter(); fails = []; flush = []
with (R / "recording.jsonl").open(encoding="utf-8") as f:
    for l in f:
        try:
            e = json.loads(l)
        except Exception:
            continue
        ev[e["type"]] += 1
        if e["type"] == "plugin.flush":
            flush.append(e)
            if e.get("code") != 200:
                fails.append((e.get("file"), e.get("batch"), e.get("code")))
cost = sum(c.get("cost_usd") or 0 for c in calls)
last = calls[-60:]
out = {
    "batches_done": sum(prog.values()), "files_started": len(prog),
    "llm_calls": len(calls), "status": dict(collections.Counter(c["status"] for c in calls)),
    "prompt_tokens": sum(c.get("prompt_tokens") or 0 for c in calls),
    "completion_tokens": sum(c.get("completion_tokens") or 0 for c in calls),
    "cost_usd": round(cost, 4),
    "last_call_wall": calls[-1]["wall"] if calls else None,
    "recent60_median_prompt_chars": statistics.median([c["prompt_chars"] for c in last]) if last else None,
    "recent60_max_prompt_chars": max([c["prompt_chars"] for c in last]) if last else None,
    "recent60_finish_length": sum(1 for c in last if c.get("finish_reason") == "length"),
    "flush_events": len(flush), "flush_failed": fails[-10:], "n_flush_failed": len(fails),
    "flush_retry_events": ev.get("plugin.flush.retry", 0),
    "event_types_tail": {k: v for k, v in ev.items() if k.startswith(("plugin.", "gen", "judge", "llm.retry"))},
}
print(json.dumps(out, ensure_ascii=False, indent=1))
import time as _t
out["snap_cst"] = _t.strftime("%H:%M:%S", _t.gmtime(_t.time() + 8 * 3600))
try:
    out["cooldown_file_age_s"] = round(_t.time() - Path("/tmp/pes-llm-slots/cooldown").stat().st_mtime, 1)
except OSError:
    out["cooldown_file_age_s"] = None
with (st / "status_snapshots.jsonl").open("a", encoding="utf-8") as f:
    f.write(json.dumps({k: out[k] for k in ("snap_cst", "batches_done", "llm_calls", "prompt_tokens", "cost_usd",
                                            "recent60_max_prompt_chars", "n_flush_failed", "flush_retry_events",
                                            "cooldown_file_age_s")}, ensure_ascii=False) + "\n")
