# -*- coding: utf-8 -*-
"""LLM 花费与缓存命中统计（qa/cost.jsonl + qa/llm_cache_hits.jsonl）→ out/llm_cache_stats.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_eval as G
rows = [json.loads(l) for l in open(os.path.join(HERE, "qa", "cost.jsonl")) if l.strip()]
hits = [json.loads(l) for l in open(os.path.join(HERE, "qa", "llm_cache_hits.jsonl"))] if os.path.exists(os.path.join(HERE, "qa", "llm_cache_hits.jsonl")) else []
out = {"by_tag": {}, "local_hits_by_tag": {}}
for r in rows:
    u = r.get("usage") or {}
    pt = r.get("prompt_tokens") or u.get("prompt_tokens") or 0
    ct = r.get("cached_tokens")
    if ct is None:
        ct = ((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0) + (u.get("prompt_cache_hit_tokens") or 0)
    d = out["by_tag"].setdefault(r["tag"], {"calls": 0, "cost": 0.0, "prompt_tokens": 0, "cached_tokens": 0, "calls_with_cache": 0})
    d["calls"] += 1; d["cost"] += r["cost"]; d["prompt_tokens"] += pt; d["cached_tokens"] += ct; d["calls_with_cache"] += ct > 0
for d in out["by_tag"].values():
    d["cost"] = round(d["cost"], 5); d["cost_per_call"] = round(d["cost"] / d["calls"], 7)
    d["cached_ratio"] = round(d["cached_tokens"] / max(1, d["prompt_tokens"]), 4)
for h in hits:
    out["local_hits_by_tag"][h["tag"]] = out["local_hits_by_tag"].get(h["tag"], 0) + 1
tot = lambda f: sum(f(r) for r in rows)
out["total"] = {"calls": len(rows), "cost": round(tot(lambda r: r["cost"]), 4),
                "prompt_tokens": sum(d["prompt_tokens"] for d in out["by_tag"].values()),
                "cached_tokens": sum(d["cached_tokens"] for d in out["by_tag"].values()), "local_hits": len(hits)}
G.dump(os.path.join(HERE, "out", "llm_cache_stats.json"), out)
print(json.dumps(out, ensure_ascii=False, indent=1))
