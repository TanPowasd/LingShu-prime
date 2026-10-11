# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""题面侧 LLM 抽取的开发集读数（零 key，读 cache/ 与 cache_q/locomo-dev/）。对照 v3 与 多维 v3×3。
用法：python bench_qmd.py"""
import json, math, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import extract as X, bench_dev as BD, multidim as M, qmd as Q, qx  # noqa: E402

ZERO = dict(w_ent=0, w_pred=0, w_syn=0, w_tmp=0)
CFG = {
    "多维 v3×3": None,
    "Q 全开": dict(w_v3=3.0),
    "Q 去qx": dict(w_v3=3.0, w_qx=0),
    "Q 去qtri": dict(w_v3=3.0, w_qtri=0),
    "Q 去qent": dict(w_v3=3.0, w_qent=0),
    "Q 去hyde": dict(w_v3=3.0, use_hyde=0),
    "Q qx×3": dict(w_v3=3.0, w_qx=3.0),
    "v3+qx(HyDE)": dict(w_v3=1.0, w_qx=1.0, w_qent=0, w_qtri=0, **ZERO),
    "v3+qx+qtri": dict(w_v3=2.0, w_qx=2.0, w_qent=0, w_qtri=1.0, **ZERO),
}


def sign_p(w, l):
    n, k = w + l, min(w, l)
    return min(1, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1


def main():
    H = qx.load("locomo-dev")
    agg = {k: [] for k in ["v3", *CFG]}
    nh = 0
    for it in X.items("dev"):
        tri = BD.load_triples(it)[0]
        hints = {q["question"]: H.get(f"{it['sid']}#{k}") for k, q in enumerate(it["qa"])}
        nh += sum(1 for v in hints.values() if v)
        gs = {k: (M.MultiDim(it["turns"], it["ids"], tri, w_v3=3.0) if v is None else Q.QMD(it["turns"], it["ids"], tri, hints, **v))
              for k, v in CFG.items()}
        idx = {d: i for i, d in enumerate(it["ids"])}
        for q in it["qa"]:
            ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
            if not ev:
                continue
            os_ = {"v3": gs["多维 v3×3"].base.v3_turns(q["question"]), **{k: g.rank(q["question"]) for k, g in gs.items()}}
            for k, o in os_.items():
                agg[k].append({n: len(ev & set(o[:n])) / len(ev) for n in (5, 10, 25)})
    res = {"题面抽取覆盖": nh}
    for k, rs in agg.items():
        r = {f"r@{n}": round(sum(x[n] for x in rs) / len(rs), 3) for n in (5, 10, 25)}
        for b in ("v3", "多维 v3×3"):
            w = sum(a[10] > c[10] for a, c in zip(rs, agg[b])); l = sum(a[10] < c[10] for a, c in zip(rs, agg[b]))
            r[f"@10 vs {b}"] = f"{w}/{l} p={sign_p(w, l):.3f}"
        res[k] = r
        print(k, r, flush=True)
    (HERE / "results" / "qmd_dev.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
