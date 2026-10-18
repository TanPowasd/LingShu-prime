# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""真实集描述性检索（PREREG_v1 §b）+ LoCoMo dev 时间类问题解绑可用性（§c）。只跑 dev，不跑任何 test。
  python -X utf8 real.py --set locomo|hive|perltqa [--budget-secs S]   # 逐库缓存，断点续跑
  python -X utf8 real.py --summary                                     # 汇总 → results/real_v1.json/.md
数据加载只读 import agm/umb/build_umb.py、agm/bench/hive_retrieval.py、agm/all/perltqa.py；指标 lme_zerokey.score 与 hive 8000 字预算。
环境变量同 agm/umb/README.md（UMB_LOCOMO、UMB_HIVE、UMB_PERLTQA、UMB_OUT）；逐题缓存写 $VSA_OUT（默认 <仓根>/TanPowasd/vsa/data，不入库）。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, datetime, json, math, pathlib, re, resource, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
AGM = HERE.parent / "agm"
sys.path[:0] = [str(HERE), str(AGM / "umb"), str(AGM / "bench"), str(AGM / "all"), str(AGM / "tricue"), str(AGM / "lex")]
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import bm25 as B  # noqa: E402
from cleanup import DOUBT  # noqa: E402

OUT = pathlib.Path(os.environ.get("VSA_OUT") or (HERE / "data"))
UMB = AGM / "umb"
UMB_OUT = pathlib.Path(os.environ.get("UMB_OUT") or (UMB / "data"))
WS = (0.5, 1.0, 2.0)
W_MAIN = 1.0
ARMS = ["bm25s", "vsa", "vsa_b0"] + [f"fuse{w}" for w in WS]
TIME_Q = re.compile(r"^\s*(when|what (date|day|month|year|time)|which (day|date|month|year)|how long ago)\b", re.I)


def z(x):
    x = np.asarray(x, dtype=np.float64)
    s = x.std()
    return np.zeros_like(x) if s == 0 else (x - x.mean()) / s


def order(s):
    return list(np.argsort(-np.asarray(s), kind="stable"))


def score_r(o, gold):
    from lme_zerokey import score
    return score(o, gold)["r@10"]


class Cache:
    def __init__(self, name):
        self.p = OUT / "runs" / "dev" / f"{name}.json"
        self.p.parent.mkdir(parents=True, exist_ok=True)
        self.d = json.loads(self.p.read_text(encoding="utf-8")) if self.p.exists() else {"per": {}, "time": {}, "done_units": []}

    def save(self):
        tmp = self.p.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, ensure_ascii=False), encoding="utf-8"); tmp.replace(self.p)


def retrieval_rows(m, bm, qtexts):
    """→ [{arm: 分数数组}]，每题一个：bm25s / vsa(β=0.5) / vsa_b0(β=0) / fuse{w}。"""
    s5 = m.search_many(qtexts, beta=0.5)
    s0 = m.search_many(qtexts, beta=0.0)
    out = []
    for q, a, b in zip(qtexts, s5, s0):
        sb = bm.scores(q)
        r = {"bm25s": sb, "vsa": a, "vsa_b0": b}
        for w in WS:
            r[f"fuse{w}"] = z(sb) + w * z(a)
        out.append(r)
    return out


# ---------------------------------------------------------------- 金标时间规范化（§c）
_MON = "|".join(sorted(M.MONTHS, key=len, reverse=True))
_WDS = "week|weekend|" + "|".join(M.WEEKDAYS_EN)


def canon_gold(ans):
    s = re.sub(r"\s+", " ", str(ans).strip().lower().rstrip("."))
    m = re.fullmatch(rf"(?:on )?the ({_WDS}) before (.+)", s)
    if m:
        d = _date_full(m.group(2))
        return f"BEFORE:{m.group(1)}:{d.isoformat()}" if d else None
    d = _date_full(s)
    if d:
        return M.t_date(d)
    m = re.fullmatch(rf"({_MON}),? (\d{{4}})", s)
    if m:
        return f"MONTH:{int(m.group(2)):04d}-{M.MONTHS[m.group(1)]:02d}"
    if re.fullmatch(r"\d{4}", s):
        return f"YEAR:{s}"
    return None


def _date_full(s):
    m = re.fullmatch(rf"(\d{{1,2}}) ({_MON}),? (\d{{4}})", s) or None
    if m:
        a, mo, y = m.groups()
    else:
        m = re.fullmatch(rf"({_MON}) (\d{{1,2}}),? (\d{{4}})", s)
        if not m:
            return None
        mo, a, y = m.groups()
    try:
        return datetime.date(int(y), M.MONTHS[mo], int(a))
    except ValueError:
        return None


def decode_time(m, i):
    try:
        return m.decode(i, "TIME")
    except H.CapacityError:
        return ("容量拒写", 0.0, 0.0, None)


# ---------------------------------------------------------------- 各集
def run_locomo(c, budget, t0):
    import build_umb as BU
    sp = json.loads((UMB / "locomo" / "split.json").read_text(encoding="utf-8"))["dev"]
    qs = {}
    with open(UMB / "locomo" / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line); qs[o["_id"]] = o
    raw = {x["sample_id"]: x["conversation"] for x in json.loads(BU.resolve(BU.tok("UMB_LOCOMO")).read_text(encoding="utf-8"))}
    by = collections.defaultdict(list)
    for q in sp:
        by[qs[q]["sid"]].append(q)
    for it in BU.locomo_conv_items():
        sid = it["sid"]
        if sid not in by or sid in c.d["done_units"]:
            continue
        conv = raw[sid]
        spk = [conv["speaker_a"], conv["speaker_b"]]
        m = M.Memory(H.Space("vsa-v1", cache_max=0))
        for t, did in zip(it["turns"], it["ids"]):
            d = M.parse_en_date(conv[f"session_{int(did.split(':')[0].lstrip('D'))}_date_time"])
            s = t.split(": ", 1)[0] if ": " in t[:40] else None
            m.write(t, persons=spk, speaker=s, base_date=d, base_time=M.t_date(d) if d else None, weekday=False)
        bm = B.BM25(it["turns"])
        idx = {d: i for i, d in enumerate(it["ids"])}
        qa = [it["qa"][qs[q]["qi"]] for q in by[sid]]
        rows = retrieval_rows(m, bm, [x["question"] for x in qa])
        for q, x, r in zip(by[sid], qa, rows):
            gold = {idx[e] for e in BU.locomo_gold(it, x)}
            c.d["per"][q] = {a: score_r(order(r[a]), gold) for a in ARMS}
            if TIME_Q.search(x["question"]):
                cand = order(r[f"fuse{W_MAIN}"])
                names = [p for p in spk if re.search(r"\b" + re.escape(p) + r"\b", x["question"])]
                if names:
                    cand = [i for i in cand if m.texts[i].split(": ", 1)[0] in names]
                ans, tr, n_try = DOUBT, None, 0
                for i in cand:
                    n_try += 1
                    a = decode_time(m, i)
                    if a[0] not in (DOUBT, "容量拒写"):
                        ans, tr = a[0], i; break
                g = canon_gold(x["answer"])
                orc = [decode_time(m, i)[0] for i in sorted(gold)]
                c.d["time"][q] = {"q": x["question"], "gold": str(x["answer"]), "gold_canon": g, "pred": ans, "cat": x.get("category"),
                                  "ok": g is not None and ans == g, "oracle": orc, "oracle_ok": g is not None and g in orc,
                                  "first_is_gold": bool(cand) and cand[0] in gold, "trace_is_gold": tr in gold, "n_try": n_try,
                                  "speaker_filter": names}
        c.d["done_units"].append(sid); c.save()
        print(f"locomo {sid} q={len(by[sid])} n={len(it['turns'])} {time.time() - t0:.0f}s rss={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}MB", flush=True)
        if budget and time.time() - t0 > budget:
            return False
    return True


def run_hive(c, budget, t0):
    import build_umb as BU
    import hive_retrieval as HR
    if "hive" in c.d["done_units"]:
        return True
    HIVE = BU.resolve(json.loads((UMB / "hive" / "source.json").read_text(encoding="utf-8"))["repo"])
    chunks = HR.load_chunks(HIVE)
    texts = [x["text"] for x in chunks]
    gq = json.loads((UMB / "hive" / "gold_quotes.json").read_text(encoding="utf-8"))
    qs = {}
    with open(UMB / "hive" / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line); qs[o["_id"]] = o["text"]
    dev = json.loads((UMB / "hive" / "split.json").read_text(encoding="utf-8"))["dev"]
    m = M.Memory(H.Space("vsa-v1", cache_max=0))
    for t in texts:
        m.write(t, roles=[])                    # 检索只用内容向量，不抽角色、不建痕迹
    bm = B.BM25(texts)
    rows = retrieval_rows(m, bm, [qs[q] for q in dev])
    for q, r in zip(dev, rows):
        ps = list(gq[q].values())
        c.d["per"][q] = {a: sum(x in HR.take(order(r[a]), chunks, 8000) for x in ps) / len(ps) for a in ARMS}
    c.d["done_units"].append("hive"); c.save()
    print(f"hive q={len(dev)} chunks={len(texts)} vocab={len(m.ri.words)} {time.time() - t0:.0f}s rss={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}MB", flush=True)
    return True


def run_perltqa(c, budget, t0):
    import perltqa as P
    data, _ = P.load()
    for nm in sorted(data):
        if P.split_of(nm) != "dev" or nm in c.d["done_units"] or not data[nm]["qs"]:
            continue
        d = data[nm]
        m = M.Memory(H.Space("vsa-v1", cache_max=0))
        for t in d["texts"]:
            m.write(t, roles=[])
        bm = B.BM25(d["texts"])
        rows = retrieval_rows(m, bm, [x for _, x, _ in d["qs"]])
        for (q, _, gold), r in zip(d["qs"], rows):
            c.d["per"][q] = {a: score_r(order(r[a]), gold) for a in ARMS}
        c.d["done_units"].append(nm); c.save()
        print(f"perltqa {nm} q={len(d['qs'])} n={len(d['texts'])} vocab={len(m.ri.words)} {time.time() - t0:.0f}s "
              f"rss={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}MB", flush=True)
        if budget and time.time() - t0 > budget:
            return False
    return True


# ---------------------------------------------------------------- 汇总
def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def summary():
    res, md = {}, ["# VSA 阶段 1 · 真实集 dev 描述性检索（PREREG_v1 §b）", "",
                   "| 集 | 题数 | bm25(UMB缓存) | te(UMB缓存) | bm25s(自写) | vsa β=.5 | vsa β=0(消融) | fuse w=.5 | **fuse w=1(主报)** | fuse w=2 | fuse1 vs bm25 胜/负/平 p | fuse1 vs te 胜/负/平 p | vsa vs bm25 胜/负/平 p |",
                   "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|"]
    for name in ("locomo", "hive", "perltqa"):
        p = OUT / "runs" / "dev" / f"{name}.json"
        if not p.exists():
            md.append(f"| {name} | 未跑 |" + " |" * 12); continue
        d = json.loads(p.read_text(encoding="utf-8"))
        base = {}
        for a in ("bm25", "te"):
            bp = UMB_OUT / "runs" / "dev" / name / f"{a}.json"
            base[a] = {k: v["r@10"] for k, v in json.loads(bp.read_text(encoding="utf-8"))["per"].items()} if bp.exists() else {}
        qs = [q for q in d["per"] if q in base["bm25"] and q in base["te"]]
        if not qs:
            continue
        sc = {a: float(np.mean([d["per"][q][a] for q in qs])) for a in ARMS}
        sc["bm25"] = float(np.mean([base["bm25"][q] for q in qs])); sc["te"] = float(np.mean([base["te"][q] for q in qs]))

        def sg(a, b):
            va = [d["per"][q][a] for q in qs]
            vb = [base[b][q] for q in qs] if b in base else [d["per"][q][b] for q in qs]
            w = sum(x > y + 1e-12 for x, y in zip(va, vb)); l = sum(x < y - 1e-12 for x, y in zip(va, vb))
            return {"win": w, "loss": l, "tie": len(qs) - w - l, "p": sign_p(w, l)}
        s = {"fuse1_vs_bm25": sg(f"fuse{W_MAIN}", "bm25"), "fuse1_vs_te": sg(f"fuse{W_MAIN}", "te"), "vsa_vs_bm25": sg("vsa", "bm25"),
             "vsa_vs_vsab0": sg("vsa", "vsa_b0"), "bm25s_vs_bm25": sg("bm25s", "bm25")}
        res[name] = {"n": len(qs), "n_vsa_rows": len(d["per"]), "r@10": sc, "sign": s, "done_units": len(d["done_units"])}
        f = lambda x: f"{x:.3f}"
        t = lambda x: f"{x['win']}/{x['loss']}/{x['tie']} p={x['p']:.2g}"
        md.append(f"| {name} | {len(qs)} | {f(sc['bm25'])} | {f(sc['te'])} | {f(sc['bm25s'])} | {f(sc['vsa'])} | {f(sc['vsa_b0'])} | "
                  f"{f(sc['fuse0.5'])} | **{f(sc['fuse1.0'])}** | {f(sc['fuse2.0'])} | {t(s['fuse1_vs_bm25'])} | {t(s['fuse1_vs_te'])} | {t(s['vsa_vs_bm25'])} |")
    md += ["", "指标：LoCoMo/PerLTQA r@10（lme_zerokey.score）；hive = 8000 字预算证据句完整率（UMB 口径记为 r@10）。",
           "bm25/te 读 UMB 既有 dev 逐题缓存（未重跑）。fuse w = z(bm25s)+w·z(vsa)，w=1 为读数前指定的主报。"]
    tp = OUT / "runs" / "dev" / "locomo.json"
    if tp.exists():
        T = json.loads(tp.read_text(encoding="utf-8"))["time"]
        n = len(T); canon = [v for v in T.values() if v["gold_canon"]]
        cat2 = sum(v["cat"] == 2 for v in T.values())
        tm = {"n_time_q": n, "n_cat2_among": cat2, "n_gold_canon": len(canon),
              "acc_all": sum(v["ok"] for v in T.values()) / max(1, n), "acc_canon": sum(v["ok"] for v in canon) / max(1, len(canon)),
              "oracle_all": sum(v["oracle_ok"] for v in T.values()) / max(1, n), "oracle_canon": sum(v["oracle_ok"] for v in canon) / max(1, len(canon)),
              "first_is_gold": sum(v["first_is_gold"] for v in T.values()) / max(1, n), "trace_is_gold": sum(v["trace_is_gold"] for v in T.values()) / max(1, n),
              "pred_doubt": sum(v["pred"] == DOUBT for v in T.values()) / max(1, n),
              "gold_kinds": dict(collections.Counter((v["gold_canon"] or "不可规范化").split(":")[0] for v in T.values()))}
        res["locomo_time"] = tm
        md += ["", "## LoCoMo dev 时间类问题：解绑 TIME 角色（PREREG_v1 §c，描述性）", "",
               "| 时间题数（规则识别） | 其中 category 2 | 金标可规范化 | 解绑答对/全部 | 解绑答对/可规范化 | oracle（金标证据轮解绑）/全部 | oracle/可规范化 | 候选首轮=金标证据 | 解绑所用轮=金标证据 | 存疑 |",
               "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
               f"| {n} | {cat2} | {len(canon)} | {tm['acc_all']:.3f} | {tm['acc_canon']:.3f} | {tm['oracle_all']:.3f} | {tm['oracle_canon']:.3f} | "
               f"{tm['first_is_gold']:.3f} | {tm['trace_is_gold']:.3f} | {tm['pred_doubt']:.3f} |", "",
               "金标形态分布：" + "，".join(f"{k} {v}" for k, v in tm["gold_kinds"].items())]
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "real_v1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "results" / "real_v1.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["locomo", "hive", "perltqa"]); ap.add_argument("--budget-secs", type=float)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        return summary()
    t0 = time.time()
    c = Cache(a.set)
    done = {"locomo": run_locomo, "hive": run_hive, "perltqa": run_perltqa}[a.set](c, a.budget_secs, t0)
    c.save()
    print(a.set, "完成" if done else "预算到，下次同命令续跑", f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
