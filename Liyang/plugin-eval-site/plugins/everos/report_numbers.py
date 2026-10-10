# -*- coding: utf-8 -*-
"""汇总 EverOS 测评读数（机读 JSON），供报告与复核包引用。只读录像与日志，不调 LLM。
用法：python3 plugins/everos/report_numbers.py > reports/everos_站外复核包/读数_everos.json
"""
import glob, json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from harness.recorder import load_events, mmss  # noqa: E402

R = lambda *p: os.path.join(ROOT, *p)


def llm_log(p):
    rows = [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []
    ok = [r for r in rows if r.get("status") == 200]
    lat = [r["dur_s"] for r in ok]
    return {"calls": len(rows), "ok": len(ok), "errors": len(rows) - len(ok),
            "prompt_tokens": sum(r.get("prompt_tokens") or 0 for r in ok),
            "completion_tokens": sum(r.get("completion_tokens") or 0 for r in ok),
            "cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in ok), 4),
            "call_latency_s_median": round(statistics.median(lat), 1) if lat else None,
            "prompt_chars_max": max((r.get("prompt_chars") or 0 for r in ok), default=0)}


def flushes(rec_path):
    if not os.path.exists(rec_path):
        return []
    return [e for e in load_events(rec_path) if e["type"] == "plugin.flush"]


def cite(run, e):
    return f"⟦录像:{run}@{mmss(e['t'])}#{e['seq']}⟧"


out = {}
# 安装录像
ev = load_events(R("runs/everos_install/recording.jsonl"))
out["install_steps"] = [{"step": e.get("step"), "rc": e.get("rc"), "dur_s": e.get("dur_s"), "cite": cite("everos_install", e)}
                        for e in ev if e["type"] == "cmd.end"]
# 单位写入成本：冒烟臂（1 份语料 5 批，全程独占一个会话）+ 探针（被中途停掉的单会话写入）
units = {}
for name, rec, log in (("smoke", "runs/B_everos_smoke/recording.jsonl", "runs/B_everos_smoke/everos_state/everos_llm_calls.jsonl"),
                       ("probe", "runs/everos_probe/recording.jsonl", "runs/everos/probe_sbx/everos_llm_calls.jsonl"),
                       ("full", "runs/B_everos/recording.jsonl", "runs/B_everos/everos_state/everos_llm_calls.jsonl")):
    fl = [e for e in flushes(R(rec))]
    ok = [e for e in fl if e.get("code") == 200]
    u = {"flushes": len(fl), "flush_ok": len(ok), "est_tokens_flushed": sum(e.get("est_tokens") or 0 for e in ok),
         "flush_s_median": round(statistics.median([e["flush_s"] for e in ok]), 1) if ok else None,
         "flush_s_max": max((e["flush_s"] for e in ok), default=None), "llm": llm_log(R(log))}
    if ok:
        u["llm_calls_per_flush"] = round(u["llm"]["calls"] / len(ok), 2)
        u["prompt_tokens_per_flush"] = round(u["llm"]["prompt_tokens"] / len(ok))
        u["cost_usd_per_flush"] = round(u["llm"]["cost_usd"] / len(ok), 5)
        u["first_flush_cite"] = cite(os.path.basename(os.path.dirname(rec)), ok[0])
        u["last_flush_cite"] = cite(os.path.basename(os.path.dirname(rec)), ok[-1])
    units[name] = u
out["ingest_units"] = units
# 全卷计划
plan = [e for e in load_events(R("runs/B_everos/recording.jsonl")) if e["type"] == "plugin.ingest.plan"] if os.path.exists(R("runs/B_everos/recording.jsonl")) else []
out["full_plan"] = {k: plan[-1][k] for k in ("sessions", "batches", "already_done", "par")} if plan else None
if plan:
    out["full_plan"]["cite"] = cite("B_everos", plan[0])
prog = R("runs/B_everos/everos_state/ingest_progress.json")
out["full_progress"] = json.load(open(prog)) if os.path.exists(prog) else {}
out["full_progress_batches_done"] = sum(out["full_progress"].values())
# 冒烟臂召回
sm = R("runs/B_everos_smoke")
if os.path.exists(sm + "/state.json"):
    st = json.load(open(sm + "/state.json"))
    out["smoke_state"] = {k: st.get(k) for k in ("install", "ingest", "recall_latency_s", "permissions", "sandbox_env_has_api_key")}
    out["smoke_uninstall"] = {"reported": (st.get("uninstall") or {}).get("reported"),
                              "sandbox_residue_added": len(((st.get("uninstall") or {}).get("residue") or {}).get("added") or []),
                              "sandbox_residue_bytes": ((st.get("uninstall") or {}).get("residue") or {}).get("added_bytes"),
                              "outside_new": ((st.get("uninstall") or {}).get("residue") or {}).get("outside_new")}
    out["smoke_recall"] = []
    evs = {e["seq"]: e for e in load_events(sm + "/recording.jsonl")}
    for p in sorted(glob.glob(sm + "/q/*.recall.json")):
        r = json.load(open(p))
        searches = [e for e in evs.values() if e["type"] == "plugin.search"]
        out["smoke_recall"].append({"qid": r["qid"], "raw_sources": r["raw_sources"], "material": [(m["source"], len(m["text"])) for m in r["material"]],
                                    "latency_s": round(r["latency_s"], 2), "leak_audit": r["leak_audit"],
                                    "cite": cite("B_everos_smoke", evs[r["ev"][0]])})
    out["smoke_searches"] = [{k: e.get(k) for k in ("latency_s", "n", "episode_unmapped", "injected_chars")} | {"cite": cite("B_everos_smoke", e)}
                             for e in evs.values() if e["type"] == "plugin.search"]
# 外联
eg = R("runs/everos/egress_samples.jsonl")
out["egress_samples"] = [json.loads(l) for l in open(eg)] if os.path.exists(eg) else []
hb = eg + ".heartbeat"
out["egress_heartbeat"] = json.load(open(hb)) if os.path.exists(hb) else None
print(json.dumps(out, ensure_ascii=False, indent=1))
