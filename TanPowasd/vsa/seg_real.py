# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""事件切分写入 · 真实集读数（PREREG_seg.md §3–§6）。零 LLM、零 key、确定性。
  python -X utf8 seg_real.py --set locomo|hive|perltqa|crossproj [--budget-secs S]   # dev：S0/S1/S2a/b/c 的 E1/E2/E3，逐单元缓存可续跑
  python -X utf8 seg_real.py --summary                                               # → results/seg_dev.json/.md（含 §4 选臂）
  python -X utf8 seg_real.py --hold crossproj --arm S2x                              # §5：先核 sha256，只跑一次（已有结果则拒跑）
  python -X utf8 seg_real.py --reuse kmb|tmd --arm S2x                               # §5：产出 reuse.py 每题文件（只交给 reuse.py，不打印逐题），并问一次
数据加载只读 import agm/umb、agm/bench、agm/all、agm/lex（lmeb_extra）；不改 agm/。逐题缓存写 $VSA_OUT（不入库）。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, datetime, hashlib, json, pathlib, re, subprocess, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
import real as R1  # noqa: E402  （导入即设好 sys.path：agm/umb、agm/bench、agm/all、agm/lex 只读）
import real_v2 as RV  # noqa: E402
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402
from cleanup import DOUBT  # noqa: E402

OUT, UMB, UMB_OUT = R1.OUT, R1.UMB, R1.UMB_OUT
CP = pathlib.Path(os.environ.get("CROSSPROJ") or (HERE.parent / "datasets" / "crossproj-zh" / "release"))
CP_HOLD_SHA = "5373589bdc4af59fe4cab384d1875dbfa2e93af870cc61dd7e6740b93700a565"
ARMS = ["S0", "S1", "S2a", "S2b", "S2c"]
BETA = 0.5                      # 阶段 1 主 VSA 检索臂 vsa（β=.5），不调
SETS = ("locomo", "hive", "perltqa", "crossproj")


def arm_segs(arm, elems):
    if arm == "S1":
        return SG.segment_fixed(elems)
    return SG.segment(elems, SG.THETAS[arm])


def order0(s):
    return list(np.argsort(-np.asarray(s), kind="stable"))


def rank_unit(owner_payload, elems, forced, queries, arms=ARMS, texts=None, need_mem=False):
    """一个检索单元（一段对话 / 一个 PerLTQA 角色 / hive 全库 / KMB 一个语料）：
    → orders[arm][qi]（源单元下标完整排序）、E3 描述、（need_mem 时）各臂记忆供 E2 解绑。"""
    m0 = SG.memory_from(owner_payload)
    if texts is not None:
        m0.texts = list(texts)
    s0 = m0.search_many(queries, beta=BETA)
    n = len(owner_payload)
    orders, e3, mems = {}, {}, {}
    rej0 = 0
    for p in owner_payload:
        rej0 += SG.n_items(p) > H.K_MAX
    for arm in arms:
        if arm == "S0":
            orders["S0"] = [order0(x) for x in s0]
            e3["S0"] = {"n_units": n, "n_rejected": rej0, "max_items": max((SG.n_items(p) for p in owner_payload), default=0)}
            mems["S0"] = m0
            continue
        segs, why = arm_segs(arm, elems)
        pay = SG.seg_payload(elems, segs)
        assert max((SG.n_items(p) for p in pay), default=0) <= H.K_MAX, ("I3", arm)     # 白箱边界：不超 K_MAX
        ms = SG.memory_from(pay)
        ss = ms.search_many(queries, beta=BETA)
        orders[arm] = [SG.expand(b, segs, elems, a, n) for a, b in zip(s0, ss)]
        d = SG.describe(segs, why, pay, elems, forced)
        d["len_hist"] = dict(collections.Counter(len(s) for s in segs))
        e3[arm] = d
        if need_mem:
            mems[arm] = SG.SegView(ms, segs, elems, texts if texts is not None else [""] * n)
    return orders, e3, mems


class Cache(R1.Cache):
    def __init__(self, name, split="dev"):
        self.p = OUT / "runs" / split / f"{name}.json"
        self.p.parent.mkdir(parents=True, exist_ok=True)
        self.d = json.loads(self.p.read_text(encoding="utf-8")) if self.p.exists() else {"per": {}, "e2": {}, "e3": {}, "done_units": []}


# ---------------------------------------------------------------- LoCoMo
def locomo_elems(it, conv):
    spk = [conv["speaker_a"], conv["speaker_b"]]
    pay, elems, forced = [], [], 0
    for k, (t, did) in enumerate(zip(it["turns"], it["ids"])):
        sn = int(did.split(":")[0].lstrip("D"))
        d = M.parse_en_date(conv[f"session_{sn}_date_time"])
        s = t.split(": ", 1)[0] if ": " in t[:40] else None
        rs = M.extract_roles(t, persons=spk, speaker=s, base_date=d, weekday=False, time_rules="v2", session=M.t_date(d) if d else None)
        pay.append((M.tokens(t), rs))
        es, f = SG.make_elems(k, t, rs, d, sn)
        elems += es; forced += f
    return pay, elems, forced, spk


def run_locomo(c, budget, t0):
    import build_umb as BU
    sp = json.loads((UMB / "locomo" / "split.json").read_text(encoding="utf-8"))["dev"]
    qs = {}
    with open(UMB / "locomo" / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line); qs[o["_id"]] = o
    raw = {x["sample_id"]: x["conversation"] for x in json.loads(BU.resolve(BU.tok("UMB_LOCOMO")).read_text(encoding="utf-8"))}
    te = json.loads((UMB_OUT / "runs" / "dev" / "locomo" / "te.json").read_text(encoding="utf-8"))["per"]
    by = collections.defaultdict(list)
    for q in sp:
        by[qs[q]["sid"]].append(q)
    for it in BU.locomo_conv_items():
        sid = it["sid"]
        if sid not in by or sid in c.d["done_units"]:
            continue
        conv = raw[sid]
        pay, elems, forced, spk = locomo_elems(it, conv)
        idx = {d: i for i, d in enumerate(it["ids"])}
        qa = [it["qa"][qs[q]["qi"]] for q in by[sid]]
        orders, e3, mems = rank_unit(pay, elems, forced, [x["question"] for x in qa], texts=it["turns"], need_mem=True)
        for k, (q, x) in enumerate(zip(by[sid], qa)):
            gold = {idx[e] for e in BU.locomo_gold(it, x)}
            c.d["per"][q] = {a: R1.score_r(orders[a][k], gold) for a in ARMS}
            if R1.TIME_Q.search(x["question"]):                  # E2：阶段 2 A3 口径（te10、v2、K=10、说话人过滤、粒度），段痕迹解绑
                qt = x["question"]
                names = [p for p in spk if re.search(r"\b" + re.escape(p) + r"\b", qt)]
                gc = RV.canon_gold_v2(x["answer"])
                row = {"gold": str(x["answer"]), "J2_gold": gc}
                for a in ARMS:
                    v = mems[a]
                    ans, tr, src = RV.answer_time(v, RV.candidates(te[q]["top10"], v, names), RV.K_TE)
                    pred = RV.granularity(qt, ans)
                    row[a] = {"pred": pred, "src": src, "ok": RV.judge2(gc, pred)}
                c.d["e2"][q] = row
        c.d["e3"][sid] = e3
        c.d["done_units"].append(sid); c.save()
        print(f"locomo {sid} q={len(qa)} n={len(it['turns'])} {time.time() - t0:.0f}s", flush=True)
        if budget and time.time() - t0 > budget:
            return False
    return True


# ---------------------------------------------------------------- hive（8000 字预算口径，同阶段 1）
def run_hive(c, budget, t0):
    import build_umb as BU
    import hive_retrieval as HR
    if "hive" in c.d["done_units"]:
        return True
    HIVE = BU.resolve(json.loads((UMB / "hive" / "source.json").read_text(encoding="utf-8"))["repo"])
    chunks = HR.load_chunks(HIVE)
    gq = json.loads((UMB / "hive" / "gold_quotes.json").read_text(encoding="utf-8"))
    qs = {}
    with open(UMB / "hive" / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line); qs[o["_id"]] = o["text"]
    dev = json.loads((UMB / "hive" / "split.json").read_text(encoding="utf-8"))["dev"]
    pay, elems, forced = [], [], 0
    for k, ch in enumerate(chunks):
        pay.append((M.tokens(ch["text"]), []))               # 阶段 1 hive 只用内容向量，不抽角色
        es, f = SG.make_elems(k, ch["text"], [], None, ch["cid"])
        elems += es; forced += f
    orders, e3, _ = rank_unit(pay, elems, forced, [qs[q] for q in dev])
    for k, q in enumerate(dev):
        ps = list(gq[q].values())
        c.d["per"][q] = {a: sum(x in HR.take(orders[a][k], chunks, 8000) for x in ps) / len(ps) for a in ARMS}
    c.d["e3"]["hive"] = e3
    c.d["done_units"].append("hive"); c.save()
    print(f"hive q={len(dev)} chunks={len(chunks)} {time.time() - t0:.0f}s", flush=True)
    return True


# ---------------------------------------------------------------- PerLTQA（长单元先切句；E2 = 阶段 2 §B 口径）
def zh_time(s):
    return M.extract_time_v2(s, None, lang="zh")


def run_perltqa(c, budget, t0):
    import perltqa as P
    data, _ = P.load()
    A = RV.perltqa_answers()
    te = json.loads((UMB_OUT / "runs" / "dev" / "perltqa" / "te.json").read_text(encoding="utf-8"))["per"]
    for nm in sorted(data):
        if P.split_of(nm) != "dev" or nm in c.d["done_units"] or not data[nm]["qs"]:
            continue
        d = data[nm]
        pay, elems, forced = [], [], 0
        for u, t in enumerate(d["texts"]):
            pay.append((M.tokens(t), zh_time(t)))              # S0 = 阶段 2：整单元一条痕迹，TIME = 文中最先出现的日期
            es, f = SG.make_elems(u, t, None, None, u, sentence_split=True, role_fn=zh_time)
            elems += es; forced += f
        orders, e3, mems = rank_unit(pay, elems, forced, [x for _, x, _ in d["qs"]], texts=d["texts"], need_mem=True)
        for k, (q, x, gold) in enumerate(d["qs"]):
            c.d["per"][q] = {a: R1.score_r(orders[a][k], gold) for a in ARMS}
            if RV.ZH_TIME_Q.search(x):
                gc = RV.canon_zh(A.get(q))
                row = {"gold": A.get(q), "gold_canon": gc}
                for a in ARMS:
                    v = mems[a]
                    ans, tr, _ = RV.answer_time(v, RV.candidates(te[q]["top10"], v, [], n_all=len(v)), RV.K_TE)
                    pred = RV.granularity(x, ans)
                    row[a] = {"pred": pred, "ok": gc is not None and pred == gc}
                c.d["e2"][q] = row
        c.d["e3"][nm] = e3
        c.d["done_units"].append(nm); c.save()
        print(f"perltqa {nm} q={len(d['qs'])} n={len(d['texts'])} elems={len(elems)} {time.time() - t0:.0f}s", flush=True)
        if budget and time.time() - t0 > budget:
            return False
    return True


# ---------------------------------------------------------------- crossproj-zh（evidence_groups，score.py 口径）
def cp_load(name):
    raw = (CP / name).read_bytes()
    return json.loads(raw)[0], hashlib.sha256(raw).hexdigest()


def cp_score_mod():
    sys.path.insert(0, str(CP.parent))
    import score as CS   # crossproj-zh/score.py
    sys.path.pop(0)
    return CS


def cp_elems(conv):
    spk = [conv["speaker_a"], conv["speaker_b"]]
    ids, texts, pay, elems, forced = [], [], [], [], 0
    sess = sorted((int(k.split("_")[1]) for k in conv if re.fullmatch(r"session_\d+", k)))
    for sn in sess:
        d = datetime.date.fromisoformat(conv[f"session_{sn}_date_time"][:10])
        for tt in conv[f"session_{sn}"]:
            t = f"{tt['speaker']}: {tt['text']}"
            rs = M.extract_roles(t, persons=spk, speaker=tt["speaker"], base_date=d, weekday=False, time_rules="v2", session=M.t_date(d))
            k = len(ids)
            ids.append(tt["dia_id"]); texts.append(t); pay.append((M.tokens(t), rs))
            es, f = SG.make_elems(k, t, rs, d, sn)
            elems += es; forced += f
    return ids, texts, pay, elems, forced


def cp_rows(data, arms):
    CS = cp_score_mod()
    ids, texts, pay, elems, forced = cp_elems(data["conversation"])
    qa = [q for q in data["qa"] if q["category"] != "abstention" and q["evidence"]]
    orders, e3, _ = rank_unit(pay, elems, forced, [q["question"] for q in qa], arms=arms)
    per, preds = {}, {a: {} for a in arms}
    for k, q in enumerate(qa):
        for a in arms:
            preds[a][q["qid"]] = [ids[i] for i in orders[a][k][:50]]
        per[q["qid"]] = {"cat": q["category"], **{a: CS.score([q], preds[a])["ALL"]["r@10"] for a in arms}}
    agg = {a: CS.score(qa, preds[a])["ALL"] for a in arms}
    return per, agg, e3


def run_crossproj(c, budget, t0):
    if "crossproj" in c.d["done_units"]:
        return True
    data, h = cp_load("crossproj_zh_dev.json")
    per, agg, e3 = cp_rows(data, ARMS)
    c.d["per"] = {q: {a: v[a] for a in ARMS} for q, v in per.items()}
    c.d["cat"] = {q: v["cat"] for q, v in per.items()}
    c.d["agg"] = agg; c.d["sha256"] = h; c.d["e3"]["crossproj"] = e3
    c.d["done_units"].append("crossproj"); c.save()
    print(f"crossproj dev q={len(per)} {time.time() - t0:.0f}s", flush=True)
    return True


# ---------------------------------------------------------------- 汇总（§3 显著性、§4 选臂）
def sign(a, b):
    w = sum(x > y + 1e-12 for x, y in zip(a, b)); l = sum(x < y - 1e-12 for x, y in zip(a, b))
    p = R1.sign_p(w, l)
    return {"win": w, "loss": l, "tie": len(a) - w - l, "p": p,
            "verdict": "显著提升" if p < .05 and w > l else "显著下降" if p < .05 and l > w else "无显著差异"}


def summary():
    res = {"prereg": "PREREG_seg.md", "E1": {}, "E2": {}, "E3": {}}
    for s in SETS:
        p = OUT / "runs" / "dev" / f"seg_{s}.json"
        if not p.exists():
            raise SystemExit(f"缺 dev 缓存：{p}（先跑 --set {s}）")
        D = json.loads(p.read_text(encoding="utf-8"))
        qs = sorted(D["per"])
        v = {a: [D["per"][q][a] for q in qs] for a in ARMS}
        res["E1"][s] = {"n": len(qs), "mean": {a: float(np.mean(v[a])) for a in ARMS},
                        "vs_S0": {a: sign(v[a], v["S0"]) for a in ARMS if a != "S0"},
                        "vs_S1": {a: sign(v[a], v["S1"]) for a in ARMS if a not in ("S0", "S1")}}
        if s == "crossproj":
            res["E1"][s]["agg_scorepy"] = D["agg"]
        if D.get("e2"):
            e = D["e2"]; eq = sorted(e)
            ok = {a: [bool(e[q][a]["ok"]) for q in eq] for a in ARMS}
            res["E2"][s] = {"n": len(eq), "acc": {a: sum(ok[a]) / len(eq) for a in ARMS},
                            "mcnemar_vs_S0": {a: RV.mcn(ok[a], ok["S0"]) for a in ARMS if a != "S0"}}
            if s == "perltqa":
                res["E2"][s]["n_canon"] = sum(e[q]["gold_canon"] is not None for q in eq)
        agg = {}
        for a in ARMS:
            us = [D["e3"][u][a] for u in D["e3"]]
            if a == "S0":
                agg[a] = {"n_units": sum(x["n_units"] for x in us), "n_rejected": sum(x["n_rejected"] for x in us),
                          "max_items": max(x["max_items"] for x in us)}
            else:
                hist = collections.Counter()
                for x in us:
                    hist.update({int(k): n for k, n in x["len_hist"].items()})
                lens = sorted(hist.elements())
                agg[a] = {"n_elems": sum(x["n_elems"] for x in us), "n_segs": sum(x["n_segs"] for x in us),
                          "len_mean": float(np.mean(lens)), "len_p50": int(np.percentile(lens, 50, method="lower")),
                          "len_p90": int(np.percentile(lens, 90, method="lower")), "len_max": max(lens),
                          "kmax_cuts": sum(x["kmax_cuts"] for x in us), "gap_cuts": sum(x["gap_cuts"] for x in us),
                          "forced_pieces": sum(x["forced_pieces"] for x in us), "max_items": max(x["max_items"] for x in us),
                          "n_rejected": 0}
        res["E3"][s] = agg
    macro = {a: float(np.mean([res["E1"][s]["mean"][a] for s in SETS])) for a in ARMS}
    star = max(("S2a", "S2b", "S2c"), key=lambda a: (macro[a], -("S2a", "S2b", "S2c").index(a)))   # 并列取先列者（θ 小），读数前定
    regress = [s for s in SETS if res["E1"][s]["vs_S0"][star]["verdict"] == "显著下降"]
    go = macro[star] > macro["S1"] and macro[star] > macro["S0"] and not regress
    res["select"] = {"macro": macro, "S2*": star, "theta": SG.THETAS[star], "gt_S1": macro[star] > macro["S1"], "gt_S0": macro[star] > macro["S0"],
                     "dev_regress_vs_S0": regress, "go_holdout": go}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "seg_dev.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = render_dev(res)
    (HERE / "results" / "seg_dev.md").write_text(md, encoding="utf-8")
    print(md)


def render_dev(res):
    f3 = lambda x: f"{x:.4f}"
    t = lambda c: f"{c['win']}/{c['loss']} p={c['p']:.3g}"
    md = ["# VSA 事件切分写入 · dev 读数（PREREG_seg §3–§4）", "",
          "## E1 VSA 检索 r@10（轮级展开；hive = 8000 字预算证据句完整率；crossproj = evidence_groups 覆盖率 r@10）", "",
          "| 集 | 题数 | S0 | S1 | S2a θ=.3 | S2b θ=.5 | S2c θ=.7 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for s in SETS:
        e = res["E1"][s]
        md.append(f"| {s} | {e['n']} | " + " | ".join(f3(e["mean"][a]) for a in ARMS) + " |")
    m = res["select"]["macro"]
    md.append("| **四集宏平均** | — | " + " | ".join(f"**{f3(m[a])}**" for a in ARMS) + " |")
    md += ["", "配对符号检验（胜/负，双侧 p）：", "", "| 集 | S1 vs S0 | S2a vs S0 | S2b vs S0 | S2c vs S0 | S2a vs S1 | S2b vs S1 | S2c vs S1 |",
           "|---|---|---|---|---|---|---|---|"]
    for s in SETS:
        e = res["E1"][s]
        md.append(f"| {s} | " + " | ".join(t(e["vs_S0"][a]) for a in ("S1", "S2a", "S2b", "S2c")) + " | "
                  + " | ".join(t(e["vs_S1"][a]) for a in ("S2a", "S2b", "S2c")) + " |")
    md += ["", "## E2 时间题解绑（J2 / PerLTQA 规范形相等；te10 候选 → 所在段痕迹解绑）", "",
           "| 集 | 题数 | S0 | S1 | S2a | S2b | S2c | S1 vs S0 | S2a vs S0 | S2b vs S0 | S2c vs S0 |", "|---|---:|---:|---:|---:|---:|---:|---|---|---|---|"]
    for s, e in res["E2"].items():
        md.append(f"| {s} | {e['n']} | " + " | ".join(f3(e["acc"][a]) for a in ARMS) + " | "
                  + " | ".join(t(e["mcnemar_vs_S0"][a]) for a in ("S1", "S2a", "S2b", "S2c")) + " |")
    md += ["", "## E3 描述性", "", "| 集 | 臂 | 元素数 | 段数 | 段长 均值/p50/p90/max | K_MAX 强制切边界 | 断层边界 | 单元素强制切片 | 段最大项数 | 拒写数 |",
           "|---|---|---:|---:|---|---:|---:|---:|---:|---:|"]
    for s in SETS:
        for a in ARMS:
            x = res["E3"][s][a]
            if a == "S0":
                md.append(f"| {s} | S0 | {x['n_units']} | {x['n_units']} | 1 | — | — | — | {x['max_items']} | {x['n_rejected']} |")
            else:
                md.append(f"| {s} | {a} | {x['n_elems']} | {x['n_segs']} | {x['len_mean']:.2f}/{x['len_p50']}/{x['len_p90']}/{x['len_max']} | "
                          f"{x['kmax_cuts']} | {x['gap_cuts']} | {x['forced_pieces']} | {x['max_items']} | 0 |")
    sel = res["select"]
    md += ["", "## §4 选臂", "", f"- S2* = **{sel['S2*']}**（θ={sel['theta']}），宏平均 {f3(m[sel['S2*']])}；S1 {f3(m['S1'])}；S0 {f3(m['S0'])}。",
           f"- 条件：> S1 {'✓' if sel['gt_S1'] else '✗'}；> S0 {'✓' if sel['gt_S0'] else '✗'}；dev 相对 S0 显著倒退集：{sel['dev_regress_vs_S0'] or '无'}。",
           f"- 判定：**{'进入保留集确认（§5）' if sel['go_holdout'] else '事件切分无增益，不碰保留集'}**。"]
    return "\n".join(md) + "\n"


# ---------------------------------------------------------------- §5 保留集
def selected(arm):
    p = HERE / "results" / "seg_dev.json"
    sel = json.loads(p.read_text(encoding="utf-8"))["select"]
    if not sel["go_holdout"]:
        raise SystemExit("§4 条件不满足：不碰保留集")
    if arm != sel["S2*"]:
        raise SystemExit(f"--arm {arm} 不是 dev 选中的 S2*={sel['S2*']}")
    return sel


def already(key):
    p = HERE / "results" / "seg_hold.json"
    if p.exists() and key in json.loads(p.read_text(encoding="utf-8")):
        raise SystemExit(f"{key} 保留集已有结果，按 §5 只问一次")


def hold_crossproj(arm):
    selected(arm); already("crossproj")
    outp = OUT / "runs" / "hold" / "seg_crossproj.json"
    if outp.exists():
        raise SystemExit(f"crossproj hold 已跑过一次（{outp}），按 §5 不再跑")
    data, h = cp_load("crossproj_zh_hold.json")
    if h != CP_HOLD_SHA:
        raise SystemExit(f"存疑：crossproj hold sha256 不符（{h}），停")
    per, agg, e3 = cp_rows(data, ["S0", arm])
    qs = sorted(per)
    sg = sign([per[q][arm] for q in qs], [per[q]["S0"] for q in qs])
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps({"sha256": h, "arm": arm, "per": per, "agg": agg, "e3": e3}, ensure_ascii=False), encoding="utf-8")
    res = {"set": "crossproj-zh hold", "sha256": h, "n": len(qs), "arm": arm, "agg_scorepy": agg,
           "mean": {"S0": float(np.mean([per[q]["S0"] for q in qs])), arm: float(np.mean([per[q][arm] for q in qs]))}, "sign_vs_S0": sg}
    res["delta"] = res["mean"][arm] - res["mean"]["S0"]
    write_hold("crossproj", res)


def reuse_files(which, arm):
    """→ reuse.py 需要的每题文件 {"per":[{"qid","arms":{VSA-S0:{r@10}, VSA-<arm>:{r@10}}}]}。只写盘，不打印、不汇总逐题。"""
    import lmeb_extra as LX
    from lme_zerokey import score
    names = {"S0": "VSA-S0", arm: f"VSA-SEG-{arm}"}
    root = os.environ.get("KMB_DATA" if which == "kmb" else "TMD_DATA") or f"/workspace/work/{which}"
    d = OUT / "reuse"; d.mkdir(parents=True, exist_ok=True)

    def unit_rows(it, qa_lists):
        pay, elems, forced = [], [], 0
        for k, (t, ss) in enumerate(zip(it["turns"], it["sess"])):
            pay.append((M.tokens(t), []))
            es, f = SG.make_elems(k, t, [], None, ss)
            elems += es; forced += f
        allq = [q for ql in qa_lists for q in ql]
        orders, e3, _ = rank_unit(pay, elems, forced, [q["question"] for q in allq], arms=["S0", arm])
        rows = [{"qid": q["qid"], "arms": {names[a]: {"r@10": score(orders[a][k], q["gold"])["r@10"]} for a in ("S0", arm)}}
                for k, q in enumerate(allq)]
        out, i = [], 0
        for ql in qa_lists:
            out.append(rows[i:i + len(ql)]); i += len(ql)
        return out, e3

    t0 = time.time()
    if which == "kmb":
        dev, hold, e3s = [], [], {}
        for (c, a), (c2, b) in zip(LX.kmb(root, "dev"), LX.kmb(root, "hold")):
            assert c == c2 and a["turns"] == b["turns"]
            (rd, rh), e3s[c] = unit_rows(a, [a["qa"], b["qa"]])
            dev += rd; hold += rh
            print(f"kmb {c} 完成（逐题不打印） {time.time() - t0:.0f}s", flush=True)
        files = {"train": d / f"kmb_dev_{arm}.json", "hold": d / f"kmb_hold_{arm}.json"}
        files["train"].write_text(json.dumps({"per": dev}, ensure_ascii=False), encoding="utf-8")
        files["hold"].write_text(json.dumps({"per": hold}, ensure_ascii=False), encoding="utf-8")
    else:
        per, e3s, k = [], {}, 0
        for sub, it in LX.tmd(root):
            (r,), e3s[f"{sub}#{k}"] = unit_rows(it, [it["qa"]]); per += r; k += 1
        print(f"tmd 完成（逐题不打印） {time.time() - t0:.0f}s", flush=True)
        files = {"md5": d / f"tmd_{arm}.json"}
        files["md5"].write_text(json.dumps({"per": per}, ensure_ascii=False), encoding="utf-8")
    return names, files, e3s


def reuse_ask(which, arm):
    selected(arm); already(which)
    names, files, e3s = reuse_files(which, arm)
    cmd = [sys.executable, "-X", "utf8", str(HERE.parent / "agm" / "lex" / "reuse.py"), "--set", which, "--arm", names[arm], "--base", names["S0"]]
    cmd += ["--md5", str(files["md5"])] if which == "tmd" else ["--train", str(files["train"]), "--hold", str(files["hold"])]
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "PYTHONUTF8": "1"})
    print(r.stdout.strip(), r.stderr.strip()[-500:])
    line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    if r.returncode != 0 or not line.startswith("{"):
        raise SystemExit(f"reuse.py 未给出答案：{line or r.stderr[-300:]}")
    ans = json.loads(line)
    e3 = {a: {"n_segs": sum(x[a]["n_segs"] for x in e3s.values()) if a != "S0" else sum(x[a]["n_units"] for x in e3s.values())} for a in ("S0", arm)}
    write_hold(which, {"set": which, "arm": arm, "reuse": ans, "files_sha256": {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in files.items()},
                       "e3": e3})


def write_hold(key, res):
    p = HERE / "results" / "seg_hold.json"
    allr = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    if key in allr:
        raise SystemExit(f"{key} 保留集已有结果，按 §5 只问一次")
    allr[key] = res
    p.write_text(json.dumps(allr, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({key: {k: v for k, v in res.items() if k != "per"}}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=SETS); ap.add_argument("--budget-secs", type=float); ap.add_argument("--summary", action="store_true")
    ap.add_argument("--hold", choices=["crossproj"]); ap.add_argument("--reuse", choices=["kmb", "tmd"]); ap.add_argument("--arm")
    a = ap.parse_args()
    if a.summary:
        return summary()
    if a.hold:
        return hold_crossproj(a.arm)
    if a.reuse:
        return reuse_ask(a.reuse, a.arm)
    t0 = time.time()
    c = Cache(f"seg_{a.set}")
    done = {"locomo": run_locomo, "hive": run_hive, "perltqa": run_perltqa, "crossproj": run_crossproj}[a.set](c, a.budget_secs, t0)
    c.save()
    print(a.set, "完成" if done else "预算到，下次同命令续跑", f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
