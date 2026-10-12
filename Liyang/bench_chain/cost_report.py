# -*- coding: utf-8 -*-
"""本线 LLM 费用与缓存命中汇总（读 out/llm/cost.jsonl）。python cost_report.py → out/cost_report.json"""
import json, os, collections
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "llm", "cost.jsonl")
rows = [json.loads(l) for l in open(P, encoding="utf-8") if l.strip()]
real = [r for r in rows if not r.get("cache_hit")]
hits = [r for r in rows if r.get("cache_hit")]
by = collections.defaultdict(lambda: {"calls": 0, "cost": 0.0, "cache_hits": 0})
for r in rows:
    t = r.get("tag") or "?"
    if r.get("cache_hit"):
        by[t]["cache_hits"] += 1
    else:
        by[t]["calls"] += 1; by[t]["cost"] = round(by[t]["cost"] + r["cost"], 6)
logged = [r for r in real if r.get("cached_tokens") is not None]
out = {"total_cost_usd": round(sum(r["cost"] for r in real), 4), "real_calls": len(real), "logged_cache_hits": len(hits),
       "result_cache_hit_rate_since_logging": round(len(hits) / max(1, len(hits) + sum(1 for r in real if "cached_tokens" in r)), 4),
       "prefix_cache": {"calls_with_usage_detail": len(logged), "prompt_tokens": sum(r.get("prompt_tokens") or 0 for r in logged),
                        "cached_tokens": sum(r.get("cached_tokens") or 0 for r in logged)},
       "by_tag": dict(by)}
json.dump(out, open(os.path.join(os.path.dirname(P), "..", "cost_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
