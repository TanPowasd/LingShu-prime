# -*- coding: utf-8 -*-
"""G5/AGM 评测台：同一 92 卡划分（split.json）下的两个口径。
  T2 evalsuite_hmb：178 块 / 184 查询 recall(q, limit=10) / 指标 cid、原句、要点、must_exclude（hmb_metrics.perq，不改）
                    + pairs_all 两侧 / hard9 b 侧 / hard9 两侧（run_hmbq._pairs，只有全集口径）
  T1 hive_retrieval：303 块 / 92 题 recall(q, limit=100) → 队友 take()/evaluate()（import，不改），预算 2000/4000/8000
对照臂 BM25 / AGM（队友 hive_retrieval.BM25 / AGM，import 调用，同 item1/item2 构造）。
  python zh_eval.py run <tag> [root] [K=V ...]     跑 ng（root 缺省 = 本 worktree），环境变量 K=V 传给子进程
  python zh_eval.py base                           生成 BM25/AGM 对照臂排序（缓存 runs/_arms.json）
  python zh_eval.py show <tag> [split] [vs]        split ∈ dev|test|all"""
import json, os, pathlib, statistics, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(HERE)
sys.path.insert(0, "/workspace/work/ls/prime-test/work")
from ptlib import HMB, paired, dump, load  # noqa
import hive_retrieval as HR  # noqa
sys.path.insert(0, "/workspace/work/ls/wt-titans/bench_titans")
import common as C  # noqa
import hmb_metrics as HM  # noqa
H = C.H
RUNS = os.path.join(HERE, "runs")
SPLIT = json.load(open(os.path.join(HERE, "split.json")))
ROOT = pathlib.Path(HMB)
_cache = {}


def data():
    if "tc" not in _cache:
        _cache["hc"] = H.novel_chunks(); _cache["hq"] = C.novel_queries()
        _cache["tc"] = HR.load_chunks(ROOT); _cache["tcards"] = HR.load_cards(ROOT)
        _cache["hcards"] = H.load_cards()
    return _cache


def job(docs, queries, root, env):
    jd = tempfile.mkdtemp(prefix="zhjob_", dir="/tmp")
    jf, of = os.path.join(jd, "j.json"), os.path.join(jd, "o.json")
    json.dump({"docs": docs, "queries": queries}, open(jf, "w", encoding="utf-8"), ensure_ascii=False)
    e = dict(os.environ, PYTHONPATH=root, PYTHONHASHSEED="0"); e.pop("LINGSHU_NG_ASSOC", None); e.update(env)
    if e.pop("ZH_DET", None):   # 确定性模式：钉住墙钟与节点 id 随机源（bench_zh/clockshim，同 wt-gen gate_cn 做法）
        e["PYTHONPATH"] = root + os.pathsep + os.path.join(HERE, "clockshim"); e["G1_FROZEN_CLOCK"] = "1760000000"
    return subprocess.Popen([sys.executable, "-X", "utf8", os.path.join(HERE, "zh_worker.py"), jf, of], env=e, cwd=jd,
                            stderr=subprocess.PIPE, text=True), of


def run(tag, root=WT, env=None, hmb_limit=10, hive_limit=100):  # noqa: C901
    d = data()
    p1, o1 = job([c["text"] for c in d["hc"]], [{"qid": q["qid"], "q": q["q"], "limit": hmb_limit} for q in d["hq"]], root, env or {})
    p2, o2 = job([c["text"] for c in d["tc"]], [{"qid": c["qid"], "q": c["question"], "limit": hive_limit} for c in d["tcards"]], root, env or {})
    out = {"root": root, "env": env or {}}
    for name, p, o in (("hmb", p1, o1), ("hive", p2, o2)):
        err = p.communicate()[1]
        if not os.path.exists(o):
            raise RuntimeError(err[-3000:])
        out[name] = json.load(open(o, encoding="utf-8"))
    dump(os.path.join(RUNS, f"{tag}.json"), out)
    return out


def base_arms():
    p = os.path.join(RUNS, "_arms.json")
    if os.path.exists(p):
        return load(p)
    d = data()
    hc = [{"cid": c["cid"], "text": c["text"], "i": i, "n": HR.norm(c["text"])} for i, c in enumerate(d["hc"])]
    bm = HR.BM25(hc); ag = HR.AGM(hc, bm)
    tbm = HR.BM25(d["tc"]); tag_ = HR.AGM(d["tc"], tbm)
    hb = H.BM25([c["text"] for c in d["hc"]])
    out = {"AGM": {"hmb": {"rank": {q["qid"]: ag.rank(q["q"])[:10] for q in d["hq"]}},
                   "hive": {"rank": {c["qid"]: tag_.rank(c["question"]) for c in d["tcards"]}}},
           "BM25": {"hmb": {"rank": {q["qid"]: [i for i, _ in hb.search(q["q"], 10)] for q in d["hq"]}},
                    "hive": {"rank": {c["qid"]: sorted(range(len(d["tc"])), key=lambda i, s=tbm.scores(c["question"]): -s[i]) for c in d["tcards"]}}}}
    dump(p, out)
    return out


CONF_ARMS = {"MD3H": "md_heur", "MD3L": "md_llm", "TRI": "tricue"}   # 队友汇流多维 v3×3 三臂（bench_zh/conf_arms.py，校验见 runs/conf/check.json）


def conf_arm(tag, qset_hive="tcards"):
    a = CONF_ARMS[tag]; out = {}
    for corpus, qs, key in (("hive", qset_hive, "hive"), ("hmb", "hq", "hmb")):
        f = os.path.join(RUNS, "conf", f"{a}_{corpus}_{qs}.json")
        if os.path.exists(f):
            out[key] = {"rank": json.load(open(f, encoding="utf-8"))["rank"]}
    return out


def get(tag):
    if tag in ("AGM", "BM25"):
        return base_arms()[tag]
    if tag in CONF_ARMS:
        return conf_arm(tag)
    return load(os.path.join(RUNS, f"{tag}.json"))


def perq_hmb(R):
    d = data()
    D = {"recall": {q: {"hits": [{"chunk": d["hc"][i]["id"], "text": d["hc"][i]["text"]} for i in r[:10]]} for q, r in R["hmb"]["rank"].items()}}
    return HM.perq(D, d["hcards"], {c["id"]: c for c in d["hc"]}), D


def perq_hive(R, B, cards=None):
    d = data(); ch = d["tc"]; out = {}
    for c in (cards if cards is not None else d["tcards"]):
        ctx = HR.take(R["hive"]["rank"][c["qid"]], ch, B)
        ev = c.get("supporting_evidence") or []
        ps = [HR.norm(e["quote"]) for e in ev if e.get("weight") == "primary"]
        hp = [x in ctx for x in ps]
        me = [HR.norm(e["quote"]) for e in c.get("must_exclude") or []]
        out[c["qid"]] = {"prim_hit": sum(hp), "prim_n": len(ps), "full": (float(all(hp)) if ps else None),
                         "cross": len({e["cid"] for e in ev if e.get("weight") == "primary"}) >= 2,
                         "ex_hit": sum(x in ctx for x in me), "ex_n": len(me)}
    return out


def agg_hive(pq, ids):
    rows = [pq[q] for q in ids]
    pn = sum(r["prim_n"] for r in rows); en = sum(r["ex_n"] for r in rows)
    full = [r["full"] for r in rows if r["full"] is not None]
    cr = [r["full"] for r in rows if r["full"] is not None and r["cross"]]
    return {"primary": round(sum(r["prim_hit"] for r in rows) / max(1, pn), 4), "full": round(statistics.mean(full), 4) if full else None,
            "cross": round(statistics.mean(cr), 4) if cr else None, "excl": round(sum(r["ex_hit"] for r in rows) / max(1, en), 4),
            "n_prim_q": len(full), "n_cross": len(cr)}


def proxy_t1(R, B, ids):
    """dev 辅助代理（不作判定）：303 块语料、预算 B 下，所有题（含开放题 evidence_pool）全部证据原句的召回率（按句汇总）。"""
    d = data(); ch = d["tc"]; hit = n = 0
    for q in ids:
        ctx = HR.take(R["hive"]["rank"][q], ch, B)
        for e in H.card_evidence(d["hcards"][q]):
            nq = HR.norm(e["quote"])
            if nq:
                n += 1; hit += nq in ctx
    return round(hit / max(1, n), 4)


def ids_of(split):
    return SPLIT[split] if split in ("dev", "test") else SPLIT["dev"] + SPLIT["test"]


def metrics(tag, split="dev"):
    R = get(tag); ids = ids_of(split)
    m = {}
    if "hmb" in R:
        ph, _ = perq_hmb(R)
        m["T2"] = {k: round(statistics.mean(ph[q][k] for q in ids if ph[q][k] is not None), 4) for k in ("cid", "quote", "point", "excl")}
    for B in HR.BUDGETS:
        m[f"T1_{B}"] = agg_hive(perq_hive(R, B), ids)
        m[f"T1_{B}"]["proxy_all_ev"] = proxy_t1(R, B, ids)
    return m


def pairs_all(tag):
    """pairs_all 两侧 / hard9（全集口径；代理清单按对计，不按卡划分）。"""
    R = get(tag); _, D = perq_hmb(R)
    prox = json.load(open(os.path.join(H.OUT, "hmb_proxy_lists.json"), encoding="utf-8"))
    HM.R.OUT = "/tmp/zh_pairs_tool"
    return HM.R._pairs("zh_" + tag.replace("/", "_"), D["recall"], prox)


def compare(a, b, split="test"):
    """a−b 逐题配对：T2 cid/原句/要点/excl（逐卡）；T1 各预算 primary 句数、全证据 0/1、跨章全证据、误用句数。"""
    ids = ids_of(split); A, Bb = get(a), get(b)
    out = {}
    if "hmb" in A and "hmb" in Bb:
        pa, _ = perq_hmb(A); pb, _ = perq_hmb(Bb)
        for k in ("cid", "quote", "point", "excl"):
            qs = [q for q in ids if pa[q][k] is not None]
            out[f"T2.{k}"] = paired([pa[q][k] for q in qs], [pb[q][k] for q in qs])
    for B in HR.BUDGETS:
        ha, hb = perq_hive(A, B), perq_hive(Bb, B)
        pq = [q for q in ids if ha[q]["prim_n"]]
        out[f"T1_{B}.primary句数"] = paired([ha[q]["prim_hit"] for q in pq], [hb[q]["prim_hit"] for q in pq])
        out[f"T1_{B}.全证据"] = paired([ha[q]["full"] for q in pq], [hb[q]["full"] for q in pq])
        cq = [q for q in pq if ha[q]["cross"]]
        out[f"T1_{B}.跨章全证据"] = paired([ha[q]["full"] for q in cq], [hb[q]["full"] for q in cq])
        eq = [q for q in ids if ha[q]["ex_n"]]
        out[f"T1_{B}.误用句数"] = paired([ha[q]["ex_hit"] for q in eq], [hb[q]["ex_hit"] for q in eq])
    return out


# ---------------- T1-H（PREREG_ZH 修订 2）：同 hive 语料、LLM 生成的跨章多证据保留集 ----------------
T1H = os.path.join(HERE, "t1h", "t1h.json")
#: 当前 T1-H 族保留集：""（T1-H）或 "2"（T1-H2，PREREG_ZH 修订 3/3b；runs/t1h2_*、conf/*_hive_t1h2.json）
T1H_SET = os.environ.get("ZH_T1H_SET", "")


def set_t1h(which=""):
    global T1H_SET
    T1H_SET = which
    _cache.pop("t1h", None)


def _t1h_path():
    return os.path.join(HERE, "t1h2" if T1H_SET == "2" else "t1h", "t1h.json")


def _tp():
    return f"t1h{T1H_SET}"


def t1h():
    if "t1h" not in _cache:
        _cache["t1h"] = json.load(open(_t1h_path(), encoding="utf-8"))
    return _cache["t1h"]


def run_t1h(tag, split, root=WT, env=None, limit=100):
    """ng 臂在 T1-H 某一划分上的排序（split ∈ dev|test；test 每版本只跑一次，见 PREREG_ZH）。"""
    d = data(); T = t1h(); ids = set(T[split]) if split in ("dev", "test") else {c["qid"] for c in T["cards"]}
    qs = [{"qid": c["qid"], "q": c["question"], "limit": limit} for c in T["cards"] if c["qid"] in ids]
    p, o = job([c["text"] for c in d["tc"]], qs, root, env or {})
    err = p.communicate()[1]
    if not os.path.exists(o):
        raise RuntimeError(err[-3000:])
    out = {"root": root, "env": env or {}, "split": split, "hive": json.load(open(o, encoding="utf-8"))}
    dump(os.path.join(RUNS, f"{_tp()}_{tag}.json"), out)
    return out


def t1h_arms():
    p = os.path.join(RUNS, f"{_tp()}_arms.json")
    if os.path.exists(p):
        return load(p)
    d = data(); tbm = HR.BM25(d["tc"]); ag = HR.AGM(d["tc"], tbm)
    out = {"AGM": {"hive": {"rank": {c["qid"]: ag.rank(c["question"]) for c in t1h()["cards"]}}},
           "BM25": {"hive": {"rank": {c["qid"]: sorted(range(len(d["tc"])), key=lambda i, s=tbm.scores(c["question"]): -s[i])
                                      for c in t1h()["cards"]}}}}
    dump(p, out)
    return out


def get_t1h(tag):
    if tag in CONF_ARMS:
        return conf_arm(tag, _tp())
    return t1h_arms()[tag] if tag in ("AGM", "BM25") else load(os.path.join(RUNS, f"{_tp()}_{tag}.json"))


def metrics_t1h(tag, split):
    R = get_t1h(tag); ids = [q for q in t1h()[split] if q in R["hive"]["rank"]]
    cards = [c for c in t1h()["cards"] if c["qid"] in set(ids)]
    return {f"T1H_{B}": agg_hive(perq_hive(R, B, cards), ids) for B in HR.BUDGETS}


def compare_t1h(a, b, split):
    A, Bb = get_t1h(a), get_t1h(b)
    ids = [q for q in t1h()[split] if q in A["hive"]["rank"] and q in Bb["hive"]["rank"]]
    cards = [c for c in t1h()["cards"] if c["qid"] in set(ids)]
    out = {}
    for B in HR.BUDGETS:
        ha, hb = perq_hive(A, B, cards), perq_hive(Bb, B, cards)
        out[f"T1H_{B}.primary句数"] = paired([ha[q]["prim_hit"] for q in ids], [hb[q]["prim_hit"] for q in ids])
        out[f"T1H_{B}.全证据"] = paired([ha[q]["full"] for q in ids], [hb[q]["full"] for q in ids])
        out[f"T1H_{B}.误用句数"] = paired([ha[q]["ex_hit"] for q in ids], [hb[q]["ex_hit"] for q in ids])
    return out


def fmt_t1h(m):
    return " | ".join(f"{B} p{m[f'T1H_{B}']['primary']:.3f} f{m[f'T1H_{B}']['full'] or 0:.3f} x{m[f'T1H_{B}']['excl']:.3f}" for B in HR.BUDGETS)


def fmt(m):
    s = ("T2 cid %.4f quote %.4f point %.4f excl %.4f" % tuple(m["T2"][k] for k in ("cid", "quote", "point", "excl"))) if "T2" in m else "T2 n/a"
    for B in HR.BUDGETS:
        r = m[f"T1_{B}"]
        s += f" | {B} p{r['primary']:.3f} f{r['full'] or 0:.3f} c{r['cross'] or 0:.3f} x{r['excl']:.3f}"
    return s


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "run":
        tag = sys.argv[2]; rest = sys.argv[3:]
        root = rest.pop(0) if rest and "=" not in rest[0] else WT
        env = dict(x.split("=", 1) for x in rest)
        run(tag, root, env)
        for s in ("dev",):
            print(tag, s, fmt(metrics(tag, s)))
    elif cmd == "base":
        base_arms()
        for t in ("BM25", "AGM"):
            print(t, "dev", fmt(metrics(t, "dev")))
    elif cmd == "show":
        tag = sys.argv[2]; s = sys.argv[3] if len(sys.argv) > 3 else "dev"
        print(tag, s, fmt(metrics(tag, s)))
