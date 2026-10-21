# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""方案 body_date_v0.1 的根因诊断统计（只读 dev，零 LLM、零 key、确定性；不跑检索、不跑解绑、不碰任何保留集）。
  python -X utf8 proposals/body_date_diag.py      # → proposals/body_date_diag.json / .md
统计内容：
  1. 单元内显式时间表达的个数分布（v2 规则表全部匹配，而不是只取最先出现的一个）：PerLTQA dev 单元、LoCoMo dev 轮、crossproj-zh dev 轮；
  2. PerLTQA dev 的 L1 块（seg.segment_long，PerLTQA 口径：切句、每句 TIME = 句中最先出现的日期）里角色并集含 ≥2 个不同 TIME 填充的块数；
  3. dev 时间题按「金标时间位于证据单元的哪个时间表达」分型：first（= 单元最先出现者，v2 能写进痕迹）/ body（只在非首位出现，v2 写不进）/ absent / 不可规范化；
  4. （只读已提交 dev 缓存）PerLTQA E2 的 L1 逐题判对按上述分型交叉（$VSA_OUT/runs/dev/long_perltqa.json，存在才读）。
不改 memory.py / seg.py / real_v2.py；时间规则直接复用 memory.RE2_ZH / RE2_EN / _fill_zh / _fill_en。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import collections, json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import real_v2 as RV  # noqa: E402  （导入即设好 agm 只读 sys.path）
import real as R1  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402
import seg_real as SR  # noqa: E402
import hdc as H  # noqa: E402


def all_times(text, base, zh):
    """v2 规则表的全部匹配（不在第一次出现处 break）；重叠片段按 (起点, −长度) 贪心保留。→ [(起点, 规则号, 填充)] 按起点排序。"""
    low = text.lower()
    src = text if zh else low
    hits = []
    for rule, rx in (M.RE2_ZH if zh else M.RE2_EN):
        if not zh and base is None and rule not in ("en-TM2-full", "en-TM2-inyear"):
            continue
        for m in rx.finditer(src):
            f = M._fill_zh(rule, m, base) if zh else M._fill_en(rule, m, base, low)
            if f is not None:
                hits.append((m.start(), m.end(), rule, f))
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    out, end = [], -1
    for s, e, r, f in hits:
        if s >= end:
            out.append((s, r, f)); end = e
    return out


def dist(counts):
    c = collections.Counter(min(n, 3) for n in counts)
    n = len(counts)
    return {"n": n, "0": c[0], "1": c[1], "2": c[2], ">=3": c[3], "share_ge2": round((c[2] + c[3]) / n, 4) if n else None}


def classify(gold_c, unit_fills, judge):
    """unit_fills = 每个证据单元的填充序列（文中顺序）。judge(gold_c, fill) → bool。"""
    if gold_c is None:
        return "uncanon"
    if any(fs and judge(gold_c, fs[0]) for fs in unit_fills):
        return "first"
    if any(judge(gold_c, f) for fs in unit_fills for f in fs[1:]):
        return "body"
    return "absent"


def perltqa():
    import perltqa as P
    data, _ = P.load()
    A = RV.perltqa_answers()
    unit_n, long_n, short_n, chunk_multi, chunks = [], [], [], 0, 0
    qcls, qrow = collections.Counter(), {}
    for nm in sorted(data):
        if P.split_of(nm) != "dev":
            continue
        d = data[nm]
        fills = []
        pay, elems = [], []
        for u, t in enumerate(d["texts"]):
            fs = [f for _, _, f in all_times(t, None, True)]
            fills.append(fs)
            k = len(set(fs))
            unit_n.append(k)
            row = (M.tokens(t), M.extract_time_v2(t, None, lang="zh"))
            pay.append(row)
            (long_n if SG.n_items(row) > H.K_MAX else short_n).append(k)
            es, _ = SG.make_elems(u, t, None, None, u, sentence_split=True, role_fn=SR.zh_time)
            elems += es
        if any(SG.n_items(p) > H.K_MAX for p in pay):
            _, _, why, rows, _ = SG.segment_long(pay, elems)
            for w, (_, rs) in zip(why, rows):
                if w in ("chunk", "kmax"):
                    chunks += 1
                    chunk_multi += len({f for r, f, *_ in rs if r == "TIME"}) >= 2
        for q, x, g in d["qs"]:
            if not RV.ZH_TIME_Q.search(x):
                continue
            gc = RV.canon_zh(A.get(q))
            c = classify(gc, [fills[i] for i in sorted(g)], lambda a, f: RV.granularity(x, f) == a)
            qcls[c] += 1; qrow[q] = c
    out = {"units_all": dist(unit_n), "units_long": dist(long_n), "units_short": dist(short_n),
           "L1_chunks": {"n": chunks, "multi_TIME_ge2": chunk_multi, "share": round(chunk_multi / chunks, 4) if chunks else None},
           "time_q": dict(qcls), "time_q_n": sum(qcls.values())}
    cache = SR.OUT / "runs" / "dev" / "long_perltqa.json"
    if cache.exists():
        e2 = json.loads(cache.read_text(encoding="utf-8")).get("e2", {})
        x = collections.defaultdict(lambda: collections.Counter())
        for q, c in qrow.items():
            if q in e2:
                for a in ("S0", "L1"):
                    x[c][a] += bool(e2[q][a]["ok"])
                x[c]["n"] += 1
        out["E2_by_class_committed_cache"] = {k: dict(v) for k, v in x.items()}
    return out


def locomo():
    import build_umb as BU
    sp = json.loads((RV.UMB / "locomo" / "split.json").read_text(encoding="utf-8"))["dev"]
    qs = {}
    with open(RV.UMB / "locomo" / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line); qs[o["_id"]] = o
    raw = {x["sample_id"]: x["conversation"] for x in json.loads(BU.resolve(BU.tok("UMB_LOCOMO")).read_text(encoding="utf-8"))}
    items = {it["sid"]: it for it in BU.locomo_conv_items()}
    dev_sids = sorted({qs[q]["sid"] for q in sp})
    turn_n, fills_of = [], {}
    for sid in dev_sids:
        it, conv = items[sid], raw[sid]
        for i, (t, did) in enumerate(zip(it["turns"], it["ids"])):
            b = M.parse_en_date(conv[f"session_{int(did.split(':')[0].lstrip('D'))}_date_time"])
            fs = [f for _, _, f in all_times(t, b, False)]
            fills_of[(sid, i)] = fs
            turn_n.append(len(set(fs)))
    qcls = collections.Counter()
    for q in sp:
        it = items[qs[q]["sid"]]
        x = it["qa"][qs[q]["qi"]]
        if not R1.TIME_Q.search(x["question"]):
            continue
        idx = {d: i for i, d in enumerate(it["ids"])}
        gold = sorted({idx[e] for e in BU.locomo_gold(it, x)})
        gc = RV.canon_gold_v2(x["answer"])
        qt = x["question"]
        qcls[classify(gc, [fills_of[(it["sid"], g)] for g in gold], lambda a, f: RV.judge2(a, RV.granularity(qt, f)))] += 1
    return {"turns": dist(turn_n), "time_q": dict(qcls), "time_q_n": sum(qcls.values())}


def crossproj():
    data, h = SR.cp_load("crossproj_zh_dev.json")
    conv = data["conversation"]
    sess = sorted(int(k.split("_")[1]) for k in conv if re.fullmatch(r"session_\d+", k))
    import datetime
    turn_n, fills = [], {}
    for sn in sess:
        b = datetime.date.fromisoformat(conv[f"session_{sn}_date_time"][:10])
        for tt in conv[f"session_{sn}"]:
            fs = [f for _, _, f in all_times(f"{tt['speaker']}: {tt['text']}", b, True)]
            fills[tt["dia_id"]] = fs
            turn_n.append(len(set(fs)))
    qcls = collections.Counter()
    for q in data["qa"]:
        if q.get("category") == "abstention" or not q.get("evidence") or not RV.ZH_TIME_Q.search(q["question"]):
            continue
        gc = RV.canon_zh(q.get("answer"))
        qcls[classify(gc, [fills.get(e, []) for e in q["evidence"]], lambda a, f: RV.granularity(q["question"], f) == a)] += 1
    return {"sha256": h, "turns": dist(turn_n), "time_q": dict(qcls), "time_q_n": sum(qcls.values())}


def main():
    res = {"note": "dev 诊断统计，非算法读数；不跑检索/解绑；不碰保留集", "perltqa_dev": perltqa(), "locomo_dev": locomo(), "crossproj_zh_dev": crossproj()}
    (HERE / "body_date_diag.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
