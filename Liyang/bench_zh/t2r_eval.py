# -*- coding: utf-8 -*-
"""T2R 评测台（PREREG_ZH 修订 4）：T2Ranking 人工 4 级标注、多证据段落检索，26 库 × 20 题（dev 7 库 140 题 / test 19 库 380 题）。
每库为一个独立记忆体（按 pid 升序写入），ng 取 recall(q, limit=100)，对照臂取全库排序；统一用队友 take()（hive_retrieval.take，import）
在 2000/4000/8000 字预算下取上下文，逐段落判定（段落以库内下标对齐，不做子串匹配）。
指标（每题）：证据召回 = 命中的相关度 2/3 段落数 / |E|（汇总按段落合计，同 T1 primary 口径）；全证据 = E 全部命中（0/1）；
误用 = 命中的相关度 1 段落数（人工判「相关但不满足需求」，汇总为占 |M| 的比例，越低越好）；附报 ev3 召回（相关度 3）、相关度 0 带入率。
臂：ng（任意根目录 + LINGSHU_NG_ASSOC）、BM25 / AGM（hive_retrieval，import）、多维v3×3（启发）/ TriCue v3（conf_arms.md_on_chunks，import 队友 hive_md）。
多维v3×3（LLM 源图）只有 hive 语料缓存，本语料 n/a（不新调 LLM）。对照臂一律 PYTHONHASHSEED=0（AGM 同分序依赖 hash 种子）。
  python t2r_eval.py ng <tag> <split> [root] [K=V ...]     ZH_DET=1 缺省开启
  python t2r_eval.py arms <split>                          → runs/t2r/arms_<split>.json（BM25 AGM MD3H TRI）
  python t2r_eval.py show <tag> <split>"""
import json, os, statistics, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import zh_eval as Z  # noqa: E402
HR = Z.HR
# 数据集开关（PREREG_ZH 修订 5）：T2R_SET=t2r2 → t2r2/t2r2.json，输出 runs/t2r2（口径不变）
SET = os.environ.get("T2R_SET", "t2r")
DURT_LIKE = SET in ("durt", "covr")   # 修订 9：Covr（CovidRetrieval）与 DuRT 同口径
OUT = os.path.join(HERE, "runs", SET)
_T = {}


def T():
    if "t" not in _T:
        d = json.load(open(os.path.join(HERE, SET, f"{SET}.json"), encoding="utf-8"))
        d["S"] = {s["sid"]: s for s in d["stores"]}
        for s in d["stores"]:
            s["chunks"] = [{"cid": s["sid"], "text": x["text"], "i": i, "n": HR.norm(x["text"])} for i, x in enumerate(s["docs"])]
        d["C"] = {c["qid"]: c for c in d["cards"]}
        _T["t"] = d
    return _T["t"]


def cards(split):
    return [c for c in T()["cards"] if split == "all" or c["split"] == split]


def run_ng(tag, split, root=Z.WT, env=None, limit=100):
    env = dict({"ZH_DET": "1"}, **(env or {}))
    cs = cards(split)
    np_ = int(os.environ.get("T2R_NP", "0") or 0)  # 并发库数上限（v7 语义件每进程约 1G 内存；0 = 不限，同 v6）
    specs = []
    for sid in sorted({c["store"] for c in cs}):
        st = T()["S"][sid]
        qs = [{"qid": c["qid"], "q": c["question"], "limit": limit} for c in cs if c["store"] == sid]
        specs.append(([x["text"] for x in st["docs"]], qs))
    rank, score, stats = {}, {}, []

    # 断点续跑（zh-v10；沙箱会重启）：T2R_PART=1 时每库结果存 OUT/_part/<tag>_<split>_<库序>.json，已有则直接读（口径不变）
    part = os.environ.get("T2R_PART") == "1"
    pdir = os.path.join(OUT, "_part"); os.makedirs(pdir, exist_ok=True)
    pf = [os.path.join(pdir, f"{tag}_{split}_{i:02d}.json") for i in range(len(specs))]

    def _jobs():
        k = np_ or len(specs)
        for i in range(0, len(specs), k):
            todo = [j for j in range(i, min(i + k, len(specs))) if not (part and os.path.exists(pf[j]))]
            yield from [(j, None, None) for j in range(i, min(i + k, len(specs))) if j not in todo]
            yield from [(j,) + Z.job(*specs[j], root, env) for j in todo]  # 本批全部取完后才建下一批
    for j, p, o in _jobs():
        if p is None:
            r = json.load(open(pf[j], encoding="utf-8"))
        else:
            err = p.communicate()[1]
            if not os.path.exists(o):
                raise RuntimeError(err[-3000:])
            r = json.load(open(o, encoding="utf-8"))
            if part:
                json.dump(r, open(pf[j], "w", encoding="utf-8"), ensure_ascii=False)
        rank.update(r["rank"]); score.update(r["score"]); stats.append({"db": r["db_cache"], "w": round(r["write_sec"], 2)})
    out = {"root": root, "env": env, "split": split, "rank": rank, "score": score, "stats": stats}
    Z.dump(os.path.join(OUT, f"{tag}_{split}.json"), out)
    return out


def run_arms(split):
    import conf_arms as CA
    G = CA.heur_glue()
    cs = cards(split); out = {k: {} for k in ("BM25", "AGM", "MD3H", "TRI")}
    for sid in sorted({c["store"] for c in cs}):
        st = T()["S"][sid]; ch = st["chunks"]
        bm = HR.BM25(ch); ag = HR.AGM(ch, bm)
        g = CA.md_on_chunks(G, [(sid, x["text"]) for x in st["docs"]])
        for c in cs:
            if c["store"] != sid:
                continue
            q = c["question"]; s = bm.scores(q)
            out["BM25"][c["qid"]] = sorted(range(len(ch)), key=lambda i: -s[i])
            out["AGM"][c["qid"]] = list(ag.rank(q))
            out["MD3H"][c["qid"]] = list(g.rank(q))
            out["TRI"][c["qid"]] = list(g.base.v3_turns(q))
    res = {"split": split, "check_hive_md": G["_check"], "rank": out}
    Z.dump(os.path.join(OUT, f"arms_{split}.json"), res)
    return res


ARMS = ("BM25", "AGM", "MD3H", "TRI")


def get(tag, split):
    if tag in ARMS:
        return json.load(open(os.path.join(OUT, f"arms_{split}.json"), encoding="utf-8"))["rank"][tag]
    if tag == "MD3L":
        return None
    return json.load(open(os.path.join(OUT, f"{tag}_{split}.json"), encoding="utf-8"))["rank"]


def take_idx(order, chunks, budget):
    """与 hive_retrieval.take 逐行同逻辑，返回所取下标集合（并断言拼接串一致）。"""
    got, used = [], 0
    for i in order:
        L = len(chunks[i]["n"])
        if used + L > budget:
            if used:
                break
        got.append(i); used += L
    return set(got)


def perq(rank, B, cs):
    out = {}
    for c in cs:
        ch = T()["S"][c["store"]]["chunks"]
        g = take_idx(rank[c["qid"]], ch, B)
        out[c["qid"]] = {"ev_hit": sum(i in g for i in c["ev"]), "ev_n": len(c["ev"]), "full": float(all(i in g for i in c["ev"])),
                         "ev3_hit": sum(i in g for i in c["ev3"]), "ev3_n": len(c["ev3"]),
                         "mis_hit": sum(i in g for i in c["mis"]), "mis_n": len(c["mis"]),
                         "r0_hit": sum(i in g for i in c["rel0"]), "r0_n": len(c["rel0"]), "n_take": len(g)}
    return out


def agg(pq):
    R = list(pq.values()); s = lambda k: sum(r[k] for r in R)  # noqa: E731
    return {"primary": round(s("ev_hit") / s("ev_n"), 4), "full": round(statistics.mean(r["full"] for r in R), 4),
            "excl": round(s("mis_hit") / s("mis_n"), 4) if s("mis_n") else None, "ev3": round(s("ev3_hit") / max(1, s("ev3_n")), 4),
            "rel0": round(s("r0_hit") / max(1, s("r0_n")), 4), "n": len(R)}


def metrics(tag, split, ids=None):
    r = get(tag, split)
    if r is None:
        return None
    if DURT_LIKE:
        return metrics2(tag, split, ids)
    cs = [c for c in cards(split) if ids is None or c["qid"] in ids]
    return {B: agg(perq(r, B, cs)) for B in HR.BUDGETS}


def rankq(rank, cs, k=10):
    """排序指标（修订 8.3）：nDCG@k（二值增益，理想 = min(|E|,k)）、MRR（名单内首个正例倒数名次，无则 0）。"""
    import math
    out = {}
    for c in cs:
        E = set(c["ev"]); r = list(rank[c["qid"]])
        dcg = sum(1 / math.log2(i + 2) for i, x in enumerate(r[:k]) if x in E)
        idcg = sum(1 / math.log2(i + 2) for i in range(min(len(E), k)))
        mrr = next((1 / (i + 1) for i, x in enumerate(r) if x in E), 0.0)
        out[c["qid"]] = {"ndcg": dcg / idcg, "mrr": mrr}
    return out


def metrics2(tag, split, ids=None):
    """DuRT 口径：三档证据召回 / 全证据 / 干扰带入 / 平均取段数 + nDCG@10 / MRR。"""
    r = get(tag, split)
    cs = [c for c in cards(split) if ids is None or c["qid"] in ids]
    m = {B: agg(perq(r, B, cs)) for B in HR.BUDGETS}
    for B in HR.BUDGETS:
        m[B]["ntake"] = round(statistics.mean(v["n_take"] for v in perq(r, B, cs).values()), 3)
    rq = rankq(r, cs)
    m["ndcg10"] = round(statistics.mean(v["ndcg"] for v in rq.values()), 4)
    m["mrr"] = round(statistics.mean(v["mrr"] for v in rq.values()), 4)
    return m


def compare2(a, b, split, ids=None):
    ra, rb = get(a, split), get(b, split)
    cs = [c for c in cards(split) if ids is None or c["qid"] in ids]
    q = [c["qid"] for c in cs]; out = {}
    for B in HR.BUDGETS:
        pa, pb = perq(ra, B, cs), perq(rb, B, cs)
        out[f"{B}.primary"] = Z.paired([pa[x]["ev_hit"] for x in q], [pb[x]["ev_hit"] for x in q])
        out[f"{B}.full"] = Z.paired([pa[x]["full"] for x in q], [pb[x]["full"] for x in q])
    qa, qb = rankq(ra, cs), rankq(rb, cs)
    for k in ("ndcg", "mrr"):
        out[k] = Z.paired([qa[x][k] for x in q], [qb[x][k] for x in q])
    return out


def fmt2(m):
    return " | ".join(f"{B} p{m[B]['primary']:.3f} f{m[B]['full']:.3f} r0{m[B]['rel0']:.3f} n{m[B]['ntake']:.2f}" for B in HR.BUDGETS) + f" | nDCG10 {m['ndcg10']:.4f} MRR {m['mrr']:.4f}"


def compare(a, b, split, ids=None):
    ra, rb = get(a, split), get(b, split)
    cs = [c for c in cards(split) if ids is None or c["qid"] in ids]
    out = {}
    for B in HR.BUDGETS:
        pa, pb = perq(ra, B, cs), perq(rb, B, cs)
        q = [c["qid"] for c in cs]
        out[f"{B}.primary"] = Z.paired([pa[x]["ev_hit"] for x in q], [pb[x]["ev_hit"] for x in q])
        out[f"{B}.full"] = Z.paired([pa[x]["full"] for x in q], [pb[x]["full"] for x in q])
        out[f"{B}.excl"] = Z.paired([pa[x]["mis_hit"] for x in q], [pb[x]["mis_hit"] for x in q])
    return out


def fmt(m):
    if DURT_LIKE:
        return fmt2(m)
    return " | ".join(f"{B} p{m[B]['primary']:.3f} f{m[B]['full']:.3f} x{m[B]['excl']:.3f} e3{m[B]['ev3']:.3f}" for B in HR.BUDGETS)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "ng":
        tag, split = sys.argv[2], sys.argv[3]; rest = sys.argv[4:]
        root = rest.pop(0) if rest and "=" not in rest[0] else Z.WT
        run_ng(tag, split, root, dict(x.split("=", 1) for x in rest))
        print(tag, split, fmt(metrics(tag, split)))
    elif cmd == "arms":
        assert os.environ.get("PYTHONHASHSEED") == "0", "对照臂须 PYTHONHASHSEED=0"
        run_arms(sys.argv[2])
        for a in ARMS:
            print(a, sys.argv[2], fmt(metrics(a, sys.argv[2])))
    elif cmd == "show":
        print(sys.argv[2], sys.argv[3], fmt(metrics(sys.argv[2], sys.argv[3])))
