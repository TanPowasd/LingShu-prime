# r@5/r@10 方向可行性（只用已暴露 dev：r12_it2 BASE 名次）：前 10 外证据轮的名次分布与说话人；理想化上限（把 11–50 名的用户自述证据轮拉进前 10）
import json, collections, statistics
out = {}
for s in ("cm8s_dev", "cm10ds_dev", "cm8_dev", "cm10d_dev"):
    jobs = {json.loads(l)["key"]: json.loads(l) for l in open(f"/tmp/gen_jobs/{s}.jsonl") if l.strip()}
    meta = json.load(open(f"/tmp/gen_jobs/meta_{s}.json"))
    R = {json.loads(l)["key"]: json.loads(l) for l in open(f"runs/r12_it2/{s}.0.jsonl") if l.strip()}
    miss_rank, spk, cat = [], collections.Counter(), collections.Counter()
    nq = 0; r10 = []; r10_or = []
    for cid, mm in meta.items():
        docs = jobs[cid]["docs"]
        for qi, m in mm.items():
            nq += 1
            o = R[cid]["rank"]["BASE"][qi]; ev = set(m["ev"])
            r10.append(len(ev & set(o[:10])) / len(ev))
            pos = {d: i for i, d in enumerate(o)}
            moved = set(o[:10])
            for e in ev - set(o[:10]):
                rk = pos.get(e, 999); miss_rank.append(rk); cat[m["cat"]] += 1
                t = docs[e] if isinstance(docs[e], str) else str(docs[e])
                sp = "user" if t.lower().startswith("user:") else ("assistant" if t.lower().startswith("assistant:") else "?")
                spk[sp] += 1
                if rk < 50: moved.add(e)
            r10_or.append(len(ev & moved) / len(ev))
    b = lambda lo, hi: sum(lo <= r < hi for r in miss_rank)
    out[s] = {"n_q": nq, "miss_ev": len(miss_rank), "rank_11_20": b(10, 20), "rank_21_50": b(20, 50), "rank_50plus": b(50, 9999),
              "median_rank": statistics.median(miss_rank) if miss_rank else None, "speaker": dict(spk), "cat": dict(cat),
              "r@10_base": round(statistics.mean(r10), 4), "r@10_oracle_pull_11_50": round(statistics.mean(r10_or), 4)}
    print(s, json.dumps(out[s], ensure_ascii=False))
json.dump(out, open("out/r13_feas.json", "w"), ensure_ascii=False, indent=1)
