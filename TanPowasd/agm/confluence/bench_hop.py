# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""两跳检索 LoCoMo dev 读数（零 key，读 cache_q/ 与 cache_h/locomo-dev/）。用法：python bench_hop.py"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import extract as X, bench_dev as BD, qmd as Q, qx, hx, hop  # noqa: E402
from bench_qmd import sign_p  # noqa: E402

CFG = {
    "h w1=1 wh=.5": dict(wh=.5), "h w1=1 wh=1": dict(wh=1.0), "h w1=1 wh=2": dict(wh=2.0),
    "h wh=1 pin5": dict(wh=1.0, pin=5), "h wh=1 pin10": dict(wh=1.0, pin=10), "h wh=2 pin10": dict(wh=2.0, pin=10),
    "h wh=1 不分摊": dict(wh=1.0, split=False), "h wh=1 已找到跳过": dict(wh=1.0, skip_found=True),
}


def main():
    H, HH = qx.load("locomo-dev"), hx.load("locomo-dev")
    agg = {k: [] for k in ["v3", "QMD", *CFG]}
    nh = 0
    for it in X.items("dev"):
        tri = BD.load_triples(it)[0]
        hints = {q["question"]: H.get(f"{it['sid']}#{k}") for k, q in enumerate(it["qa"])}
        g = Q.QMD(it["turns"], it["ids"], tri, hints, w_v3=3.0, w_qx=3.0)
        idx = {d: i for i, d in enumerate(it["ids"])}
        for k, q in enumerate(it["qa"]):
            ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
            if not ev:
                continue
            h = HH.get(f"{it['sid']}#{k}") or {"found": False, "follow": []}
            nh += bool(h["follow"])
            o1 = g.rank(q["question"])
            os_ = {"v3": g.base.v3_turns(q["question"]), "QMD": o1}
            for c, p in CFG.items():
                os_[c] = hop.fuse(o1, h["follow"], g.base.v3_turns, found=h["found"], **p)
            for c, o in os_.items():
                agg[c].append({n: len(ev & set(o[:n])) / len(ev) for n in (5, 10, 25)})
    res = {"追问覆盖": nh}
    for c, rs in agg.items():
        r = {f"r@{n}": round(sum(x[n] for x in rs) / len(rs), 3) for n in (5, 10, 25)}
        for b in ("v3", "QMD"):
            w = sum(a[10] > z[10] for a, z in zip(rs, agg[b])); l = sum(a[10] < z[10] for a, z in zip(rs, agg[b]))
            r[f"@10 vs {b}"] = f"{w}/{l} p={sign_p(w, l):.3f}"
        res[c] = r; print(c, r, flush=True)
    (HERE / "results" / "hop_dev.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
