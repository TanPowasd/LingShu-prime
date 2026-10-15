# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流 LoCoMo 开发集读数（零 key，读 extract.py 的缓存）：证据轮召回 @5/@10/@25，对照 TriCue v3。
用法：python bench_dev.py [--set k=v ...]"""
import argparse, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import extract as X, confluence as C, heur as H  # noqa: E402
SRC = "llm"


def load_triples(it):
    m = {}
    for f in sorted(X.CACHE.glob(f"{it['sid']}_*.json")):
        d = json.loads(f.read_text())
        turns = (d["out"] or {}).get("turns", {})
        for k, v in turns.items():
            m[k.strip("[] ")] = [t for t in v if isinstance(t, list) and len(t) == 3]
    cov = sum(1 for i in it["ids"] if i in m) / len(it["ids"])
    if not m:                       # dsh-bounty#466 F3：空源图（如 LLM_SYS=1 而 cache_sys/ 未抽）显式报错，不当作图继续跑
        raise RuntimeError(f"{it['sid']}：源图缓存 {X.CACHE} 里没有任何三元组（LLM_SYS_GRAPH=0 可显式沿用旧源图）")
    return [m.get(i, []) for i in it["ids"]], cov


def run(params, verbose=False):
    global SRC
    ARMS = {"v3": None, "汇流": {}, "无近义": {"syn": 0}, "无谓词": {"pred_f": 0, "pred_b": 0},
            "无时序": {"tmp_f": 0, "tmp_b": 0}, "无题面实体": {"qent": 0}, "PPR对照": "ppr"}
    agg = {a: [] for a in ARMS}
    info = {}
    for it in X.items("dev"):
        tri, cov = load_triples(it) if SRC == "llm" else ([H.triples(t) for t in it["turns"]], 1.0)
        gs = {a: C.Confluence(it["turns"], it["ids"], tri, **{**params, **v}) for a, v in ARMS.items() if isinstance(v, dict)}
        g = gs["汇流"]
        info[it["sid"]] = {"抽取覆盖": round(cov, 3), "实体": len(g.ename), "近义边": g.n_syn, "三元组": sum(map(len, tri))}
        idx = {d: i for i, d in enumerate(it["ids"])}
        for q in it["qa"]:
            ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
            if not ev:
                continue
            for arm, v in ARMS.items():
                o = g.v3_turns(q["question"]) if v is None else g.rank_ppr(q["question"]) if v == "ppr" else gs[arm].rank(q["question"])
                agg[arm].append({k: len(ev & set(o[:k])) / len(ev) for k in (5, 10, 25)})
    res = {a: {f"r@{k}": round(sum(r[k] for r in rs) / len(rs), 3) for k in (5, 10, 25)} | {"n": len(rs)} for a, rs in agg.items()}
    for A, B in (("汇流", "v3"), ("汇流", "PPR对照")):
        res[f"{A} vs {B} @10 胜/负"] = [sum(a[10] > b[10] for a, b in zip(agg[A], agg[B])), sum(a[10] < b[10] for a, b in zip(agg[A], agg[B]))]
    return res, info


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--set", nargs="*", default=[]); ap.add_argument("--src", default="llm", choices=("llm", "heur"))
    a = ap.parse_args(); SRC = a.src
    p = {k: float(v) for k, v in (s.split("=") for s in a.set)}
    for k in ("seeds", "steps", "kwta"):
        if k in p: p[k] = int(p[k])
    r, info = run(p)
    print(json.dumps(info, ensure_ascii=False)); print(json.dumps(r, ensure_ascii=False))
