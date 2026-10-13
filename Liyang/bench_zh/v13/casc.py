# -*- coding: utf-8 -*-
"""zh-v13 C1 级联复打离线模拟（PREREG_ZH 修订 11.2）：在 v11c 返回名单上，前 k 段用 bge-reranker-v2-m3 复打、只在前 k 段内重排
（与 semrank.rerank 的 sem_casc 同语义：截断后取段集合不变）。
  T2R_SET=durt python v13/casc.py score dev,hold2 v11c 8     → 打分（磁盘缓存，可断点续跑）
  T2R_SET=durt python v13/casc.py eval  dev,hold2 v11c 3,4,5,6,8
输出 runs/<SET>/v13/casc_<splits>.json"""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(H))
import t2r_eval as E  # noqa: E402
import zh_eval as Z  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.dirname(H)))
from lingshu_ng import semrank as S  # noqa: E402
MD = "/workspace/work/ls/_shared/models"


def scorer():
    return S.CrossScorer(os.path.join(MD, "bge-reranker-v2-m3"), "model_quantized.onnx", os.path.join(MD, "_score_cache"), "bge-reranker-v2-m3")


def base_rank(tag, split):
    f = os.path.join(E.OUT, f"{tag}_{split}.json")
    if not os.path.exists(f):
        f = os.path.join(E.OUT, f"{tag}_{split}_{split}.json")
    return json.load(open(f, encoding="utf-8"))["rank"]


def items(splits, tag, kmax):
    for sp in splits:
        R = base_rank(tag, sp)
        for c in E.cards(sp):
            st = E.T()["S"][c["store"]]
            r = R[c["qid"]]
            yield sp, c, r, [st["docs"][i]["text"] for i in r[:kmax]]


def score(splits, tag, kmax):
    sc = scorer(); n = 0
    for sp, c, r, txt in items(splits, tag, kmax):
        if len(txt) > 1:
            sc.score(c["question"], txt); n += 1
            if n % 20 == 0:
                print(sp, n, flush=True)
    print("done", n)


def eval_(splits, tag, ks):
    sc = scorer(); sc._load(); kmax = max(ks)
    res = {}
    for sp in splits:
        base = base_rank(tag, sp); cs = E.cards(sp); q = [c["qid"] for c in cs]
        L = {}
        for _, c, r, txt in items([sp], tag, kmax):
            L[c["qid"]] = [sc.mem.get(sc.key(c["question"], t)) for t in txt] if len(txt) > 1 else []
        miss = sum(1 for v in L.values() for x in v if x is None)
        res[sp] = {"miss": miss}
        for k in ks:
            new = {}
            for qq, r in base.items():
                l2 = L.get(qq, [])[:k]
                if len(l2) > 1 and None not in l2:
                    hk = r[:len(l2)]
                    new[qq] = [hk[i] for i in sorted(range(len(hk)), key=lambda i: (-l2[i], i))] + r[len(l2):]
                else:
                    new[qq] = r
            st = {}
            for B in E.HR.BUDGETS:
                pa, pb = E.perq(new, B, cs), E.perq(base, B, cs)
                keys = (("p", "ev_hit"), ("f", "full")) if E.DURT_LIKE else (("p", "ev_hit"), ("f", "full"), ("x", "mis_hit"))
                for kk, key in keys:
                    if key in pa[q[0]]:
                        st[f"{B}{kk}"] = Z.paired([pa[x][key] for x in q], [pb[x][key] for x in q])
            qa, qb = E.rankq(new, cs), E.rankq(base, cs)
            for kk in ("ndcg", "mrr"):
                st[kk] = Z.paired([qa[x][kk] for x in q], [qb[x][kk] for x in q])
            res[sp][str(k)] = {kk: [round(v["diff_ci95"][0], 4), v["胜"], v["负"], round(v["p"], 4)] for kk, v in st.items()}
            print(sp, "k", k, " ".join(f"{kk}{v['diff_ci95'][0]:+.4f}({v['胜']}/{v['负']},p{v['p']:.3f})" for kk, v in st.items()), flush=True)
    os.makedirs(os.path.join(E.OUT, "v13"), exist_ok=True)
    json.dump(res, open(os.path.join(E.OUT, "v13", f"casc_{'_'.join(splits)}.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sp = sys.argv[2].split(","); tag = sys.argv[3]
    if sys.argv[1] == "score":
        score(sp, tag, int(sys.argv[4]))
    else:
        eval_(sp, tag, [int(x) for x in sys.argv[4].split(",")])
