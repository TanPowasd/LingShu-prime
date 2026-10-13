"""vs_hmb.py 产物的逐题配对对照（stab-r5b）：HMB 检索轨 cid/原句/要点/excl 与状态链代理 gold6/mrr，
两臂逐题胜负与双侧符号检验 p（平局不计）。只读 <dir>/hmb_<impl>_ranks.json，口径与 bench_gen/gate_cn.py 相同。

    python tools/compare/vs_paired.py <dir> <implA> <implB>
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "bench_gen"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "bench_gen"))
import gate_cn as G  # noqa: E402


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def hmb_perq(ranks):
    chunks = G.H.novel_chunks(); cmap = {c["id"]: c for c in chunks}
    D = {"recall": {q: {"hits": [{"chunk": c, "text": cmap[c]["text"]} for c in v]} for q, v in ranks.items()}}
    return G.HM.perq(D, G.H.load_cards(), cmap)


def chain_perq(ranks):
    sys.path.insert(0, G.TIT)
    import chain_metrics as CM
    Kq = [q for q in json.load(open(os.path.join(G.ptlib.HMB, "chain", "keys", "keys.json"), encoding="utf-8")) if not q.get("reconstructible")]
    pq = CM.perq({"ranked": ranks}, Kq, CM.chain_index())
    return {q["qid"]: pq[q["qid"]] for q in Kq if q["doc_id"] not in G.DEV}


def cmp(pa, pb, keys):
    out = {}
    for k in keys:
        w = l = 0; sa = sb = 0.0; n = 0
        for q in pa:
            a, b = pa[q].get(k), pb[q].get(k)
            if a is None or b is None:
                continue
            n += 1; sa += a; sb += b
            w += a > b; l += a < b
        out[k] = {"n": n, "A": round(sa / max(n, 1), 4), "B": round(sb / max(n, 1), 4), "A_wins": w, "B_wins": l, "sign_p": round(sign_p(w, l), 6)}
    return out


def main():
    d, a, b = sys.argv[1:4]
    ra = json.load(open(os.path.join(d, f"hmb_{a}_ranks.json"), encoding="utf-8"))
    rb = json.load(open(os.path.join(d, f"hmb_{b}_ranks.json"), encoding="utf-8"))
    res = {"A": a, "B": b,
           "hmb": cmp(hmb_perq(ra["hmb"]), hmb_perq(rb["hmb"]), ("cid", "quote", "point", "excl")),
           "chain": cmp(chain_perq(ra["chain"]), chain_perq(rb["chain"]), ("gold6", "mrr"))}
    ca, cb = chain_perq(ra["chain"]), chain_perq(rb["chain"])
    cur = [q for q in ca if ca[q].get("type") == "现值"]
    res["chain"].update({f"{k}_现值": v for k, v in cmp({q: ca[q] for q in cur}, {q: cb[q] for q in cur}, ("gold6",)).items()})
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
