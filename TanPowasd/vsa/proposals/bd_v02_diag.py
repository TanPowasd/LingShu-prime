# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""方案 body_date_v0.2 的 dev 诊断（只读 dev，零 LLM、零 key、确定性；不碰任何保留集，crossproj-zh-bodydate 不打开）。
  python -X utf8 proposals/bd_v02_diag.py --dump perltqa|locomo   # 逐题逐候选明细 → $VSA_OUT/runs/dev/bdv02_<集>.json（不入库）
  python -X utf8 proposals/bd_v02_diag.py --analyze                # 规则模拟 → proposals/bd_v02_diag.json / .md
诊断 ≠ 判定：规则是在看过 RESULTS_body_date 三类失败题之后写的（事后），这里只回答「每条候选规则在 dev 上能修哪几题、会伤哪几题」，
不据此选阈值、不宣称收益；任何实现须新写预注册、在未见过的保留集上判定。
不改 memory.py / seg.py / real_v2.py：明细由现有公开函数读出（Memory.decode / decode_unit / bd_decode / bd_cos / search_many、
seg.time_anchor_blocks、real_v2.answer_time / answer_time_q），模拟器先复现两臂已提交读数（断言逐题相同）再套规则。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import bd_real as BR  # noqa: E402
import seg_real as SR  # noqa: E402
import real as R1  # noqa: E402
import real_v2 as RV  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402
import hdc as H  # noqa: E402
from cleanup import DOUBT  # noqa: E402

BAD = (DOUBT, "容量拒写")


def cache_path(s):
    return SR.OUT / "runs" / "dev" / f"bdv02_{s}.json"


# ---------------------------------------------------------------- 明细（dump）
def cand_detail(mw, mb, u, q, ok, ucos, time_fn):
    """单个候选单元的 L1 / BD 明细。"""
    chunks = []
    for t in mw.chunks[u]:
        try:
            a = mw.decode(t, "TIME")
        except H.CapacityError:
            a = ("容量拒写", 0.0, 0.0, None)
        fills = sorted({r[1] for r in mw.roles[t] if r[0] == "TIME"})
        chunks.append({"fill": a[0], "cos": float(a[1]), "margin": float(a[2]), "time_fills": fills})
    l1 = mw.decode_unit(u, "TIME")
    d = {"unit": int(u), "ucos": float(ucos), "chunks": chunks,
         "l1": {"fill": l1[0], "margin": float(l1[2]), "ok": bool(l1[0] not in BAD and ok(RV.granularity(q, l1[0])))}}
    js = mb.bd.get(u)
    if js:
        text = mb.unit_texts[u]
        sents = SG.time_anchor_blocks(text, time_fn, M.is_zh(text))
        cs = mb.bd_cos(u, q)
        subs = []
        for j, c in zip(js, cs):
            r = mb.bd_rows[j]
            a = mb.bd_decode(j)
            subs.append({"j": int(j), "sent": int(r["sent"]), "kind": r["kind"], "fill": r["fill"], "qcos": float(c),
                         "dec": a[0], "margin": float(a[2]), "text": sents[r["sent"]][0],
                         "ok": bool(a[0] not in BAD and ok(RV.granularity(q, a[0])))})
        d["bd"] = subs
    return d


def sess_of(mw, cand, q, ok):
    if not cand:
        return None
    try:
        a = mw.decode_unit(cand[0], "SESSION")
    except H.CapacityError:
        a = ("容量拒写",)
    return {"fill": a[0], "ok": bool(a[0] not in BAD and ok(RV.granularity(q, a[0])))}


def dump_perltqa():
    import perltqa as P
    sys.path.insert(0, str(HERE))
    import body_date_diag as DG
    sys.path.pop(0)
    BR.install()
    data, _ = P.load()
    A = RV.perltqa_answers()
    te = json.loads((SR.UMB_OUT / "runs" / "dev" / "perltqa" / "te.json").read_text(encoding="utf-8"))["per"]
    out = {}
    for nm in sorted(data):
        if P.split_of(nm) != "dev" or not data[nm]["qs"]:
            continue
        d = data[nm]
        tq = [(k, q, x, g) for k, (q, x, g) in enumerate(d["qs"]) if RV.ZH_TIME_Q.search(x)]
        if not tq:
            continue
        pay, elems, forced = [], [], 0
        for u, t in enumerate(d["texts"]):
            pay.append((M.tokens(t), SR.zh_time(t)))
            es, f = SG.make_elems(u, t, None, None, u, sentence_split=True, role_fn=SR.zh_time)
            elems += es; forced += f
        _, _, mems = BR.rank_unit(pay, elems, forced, [x for _, x, _ in d["qs"]], texts=d["texts"], need_mem=True)
        mw, mb = mems["L1"].m, mems["_bd"]
        S = mw.search_many([x for _, _, x, _ in tq], beta=SR.BETA)
        for (k, q, x, gold), sc in zip(tq, S):
            gc = RV.canon_zh(A.get(q))
            ok = lambda p, gc=gc: gc is not None and p == gc
            cls = DG.classify(gc, [[f for _, _, f in DG.all_times(d["texts"][i], None, True)] for i in sorted(gold)],
                              lambda a, f, x=x: RV.granularity(x, f) == a)
            cand = RV.candidates(te[q]["top10"], mems["L1"], [], n_all=len(mems["L1"]))
            row = BR.e2_row(mems, cand, x, ok)
            ucos = {}
            for t, s in enumerate(sc):
                v = mw.unit_of[t]; ucos[v] = max(ucos.get(v, -9), float(s))
            tf = BR.time_fn_of(None, SR.zh_time, None)
            out[q] = {"q": x, "gold": A.get(q), "gold_canon": gc, "cls": cls, "gold_units": sorted(int(i) for i in gold),
                      "L1": row["L1"], "BD": row["BD"],
                      "cands": [dict(cand_detail(mw, mb, i, x, ok, ucos[i], tf), rank=r, is_gold=i in gold) for r, i in enumerate(cand[:RV.K_TE])],
                      "session_fallback": sess_of(mw, cand, x, ok)}
        print(nm, len(tq), flush=True)
    cache_path("perltqa").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("perltqa 题数", len(out))


def dump_locomo():
    import build_umb as BU
    BR.install()
    sp = json.loads((SR.UMB / "locomo" / "split.json").read_text(encoding="utf-8"))["dev"]
    qs = {}
    with open(SR.UMB / "locomo" / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line); qs[o["_id"]] = o
    raw = {x["sample_id"]: x["conversation"] for x in json.loads(BU.resolve(BU.tok("UMB_LOCOMO")).read_text(encoding="utf-8"))}
    te = json.loads((SR.UMB_OUT / "runs" / "dev" / "locomo" / "te.json").read_text(encoding="utf-8"))["per"]
    by = collections.defaultdict(list)
    for q in sp:
        by[qs[q]["sid"]].append(q)
    out = {}
    for it in BU.locomo_conv_items():
        sid = it["sid"]
        if sid not in by:
            continue
        conv = raw[sid]
        pay, elems, forced, spk = SR.locomo_elems(it, conv)
        idx = {d: i for i, d in enumerate(it["ids"])}
        qa = [it["qa"][qs[q]["qi"]] for q in by[sid]]
        _, _, mems = BR.rank_unit(pay, elems, forced, [x["question"] for x in qa], texts=it["turns"], need_mem=True)
        mw, mb = mems["L1"].m, mems["_bd"]
        for q, x in zip(by[sid], qa):
            if not R1.TIME_Q.search(x["question"]):
                continue
            qt = x["question"]
            names = [p for p in spk if re.search(r"\b" + re.escape(p) + r"\b", qt)]
            gc = RV.canon_gold_v2(x["answer"])
            ok = lambda p, gc=gc: RV.judge2(gc, p)
            gold = {idx[e] for e in BU.locomo_gold(it, x)}
            cand = RV.candidates(te[q]["top10"], mems["L1"], names)
            row = BR.e2_row(mems, cand, qt, ok)
            sc = mw.search_many([qt], beta=SR.BETA)[0]
            ucos = {}
            for t, s in enumerate(sc):
                v = mw.unit_of[t]; ucos[v] = max(ucos.get(v, -9), float(s))
            sess = sess_of(mw, cand, qt, ok)
            out[q] = {"q": qt, "gold": str(x["answer"]), "J2_gold": gc, "cls": None, "gold_units": sorted(int(i) for i in gold),
                      "L1": row["L1"], "BD": row["BD"], "session_fallback": sess,
                      "cands": [dict(cand_detail(mw, mb, i, qt, ok, ucos[i], None), rank=r, is_gold=i in gold) for r, i in enumerate(cand[:RV.K_TE])]}
        print(sid, flush=True)
    cache_path("locomo").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("locomo 题数", len(out))


# ---------------------------------------------------------------- 回声度（白箱）
_SPK = re.compile(r"^[^\s:：]{1,16}[:：]\s*")
_KEEP = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")


def norm(s):
    """去说话人前缀，只留汉字 / 字母 / 数字（小写）。"""
    return "".join(_KEEP.findall(_SPK.sub("", s, count=1))).lower()


def bigrams(s):
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def echo_j(sent, q):
    """回声度 = 字符二元组 Jaccard(子痕迹句, 问句)，∈ [0,1]。"""
    a, b = bigrams(sent), bigrams(q)
    return len(a & b) / len(a | b) if a | b else 0.0


def echo_c(sent, q):
    """回声度（包含式）= |句∩问| / |问| 的二元组覆盖率：问句有多少被该句复述。"""
    a, b = bigrams(sent), bigrams(q)
    return len(a & b) / len(b) if b else 0.0


IS_Q = re.compile(r"[？?]\s*$|[吗呢么]\s*[？?。！!]?\s*$")


# ---------------------------------------------------------------- 模拟器
def unit_bd_choice(c, q, echo=None, echo_mode=None):
    """单元内 BD 选择（§1.7 复现）+ 可选回声抑制。→ (填充|存疑, ok, 选中子痕迹 dict|None, 来源)。
    echo：None 或 (度量函数, 阈值, 是否要求问句形, 是否要求无本句日期)；echo_mode ∈ skip / next。"""
    subs = c["bd"]
    if max(s["qcos"] for s in subs) <= 0:
        return c["l1"]["fill"], c["l1"]["ok"], None, "fallback"
    order = sorted(range(len(subs)), key=lambda k: -subs[k]["qcos"])
    flagged = set()
    if echo:
        fn, tau, need_q, need_nodate = echo
        for k, s in enumerate(subs):
            if (fn is None or fn(s["text"], q) >= tau) and (not need_q or IS_Q.search(s["text"])) and (not need_nodate or s["kind"] in ("inherit", "pre")):
                flagged.add(k)
    if flagged and echo_mode == "next":
        # 回声句 ⇒ 用句序上紧随其后的第一个非回声句替代（问—答结构里的回答）
        new = []
        for k in order:
            if k in flagged:
                nxt = next((m for m in range(k + 1, len(subs)) if m not in flagged and subs[m]["sent"] > subs[k]["sent"]), None)
                if nxt is not None and nxt not in new:
                    new.append(nxt)
            elif k not in new:
                new.append(k)
        order = new
    elif flagged:
        order = [k for k in order if k not in flagged]
        if not order:
            return c["l1"]["fill"], c["l1"]["ok"], None, "fallback_echo"
    for k in order:
        s = subs[k]
        if s["dec"] not in BAD:
            return s["dec"], s["ok"], s, "bd"
    return DOUBT, False, None, "bd"


def l1_interf(c):
    """L1 存疑是否由多 TIME 干扰造成：某块角色并集含 ≥2 个不同 TIME 填充（可审计，来自写入角色）。"""
    return any(len(ch["time_fills"]) >= 2 for ch in c["chunks"])


def simulate(rec, rule):
    """rule 字段：
       arm: L1 / BD
       cross: first（现行：首个非存疑）/ X1（L1 存疑候选仍存疑：BD 只换 L1 已非存疑候选内的日期）/
              X2（选句边距：top1 与「不同日期的最高句」余弦差 < delta ⇒ 该候选存疑）/
              X3（全候选比较：非存疑候选中取「作答句余弦」最大者；L1 候选用单元检索余弦）
       echo: None 或 (fn, tau, need_q, need_nodate)；echo_mode: skip / next"""
    q = rec["q"]
    for c in rec["cands"]:
        c.setdefault("_", {})
    pool = []
    for c in rec["cands"]:
        if rule["arm"] == "L1" or "bd" not in c:
            f, ok = c["l1"]["fill"], c["l1"]["ok"]
            conf = c["ucos"]; src = "l1"
            if f in BAD:
                continue
        else:
            if rule.get("cross") == "X1" and c["l1"]["fill"] in BAD:
                continue
            f, ok, s, src = unit_bd_choice(c, q, rule.get("echo"), rule.get("echo_mode"))
            if f in BAD:
                continue
            conf = s["qcos"] if s else c["ucos"]
            if rule.get("cross") == "X4" and src == "bd" and c["l1"]["fill"] in BAD:
                # L1 本会跳过此候选（存疑）落到 j = 其后第一个 L1 非存疑候选；BD 仅当 ucos(此候选) ≥ ucos(j) 才可抢答
                later = [x for x in rec["cands"] if x["rank"] > c["rank"] and x["l1"]["fill"] not in BAD]
                if later and c["ucos"] < later[0]["ucos"]:
                    continue
            if rule.get("cross") == "X2" and s is not None:
                other = [x["qcos"] for x in c["bd"] if x["dec"] != s["dec"] and x is not s]
                if other and s["qcos"] - max(other) < rule["delta"]:
                    continue
        pool.append((c["rank"], f, ok, conf, src, c))
        if rule.get("cross") != "X3":
            break
    if pool:
        if rule.get("cross") == "X3":
            pool.sort(key=lambda p: (-p[3], p[0]))
        r, f, ok, conf, src, c = pool[0]
        return {"pred": f, "ok": bool(ok), "rank": r, "src": src, "gold_cand": bool(c["is_gold"])}
    s = rec.get("session_fallback")
    if s and s["fill"] not in BAD:
        return {"pred": s["fill"], "ok": s["ok"], "rank": 0, "src": "SESSION", "gold_cand": None}
    return {"pred": DOUBT, "ok": False, "rank": None, "src": None, "gold_cand": None}


ECHO_FNS = {"J": echo_j, "C": echo_c, "Q": None}


def rules():
    R = {"L1": {"arm": "L1"}, "BD": {"arm": "BD", "cross": "first"}}
    R["X1"] = {"arm": "BD", "cross": "X1"}
    for d in (0.02, 0.05, 0.10):
        R[f"X2(δ={d})"] = {"arm": "BD", "cross": "X2", "delta": d}
    R["X3"] = {"arm": "BD", "cross": "X3"}
    for nm, fn in ECHO_FNS.items():
        if fn is None:
            continue
        for tau in (0.3, 0.4, 0.5, 0.6):
            R[f"E1-{nm}≥{tau}"] = {"arm": "BD", "cross": "first", "echo": (nm, tau, False, False), "echo_mode": "skip"}
        R[f"E2-{nm}≥0.5+问句形+无本句日期"] = {"arm": "BD", "cross": "first", "echo": (nm, 0.5, True, True), "echo_mode": "skip"}
        R[f"E3-{nm}≥0.5+问句形→下一句"] = {"arm": "BD", "cross": "first", "echo": (nm, 0.5, True, True), "echo_mode": "next"}
    R["X4"] = {"arm": "BD", "cross": "X4"}
    R["E4-问句形+无本句日期(无相似度门槛)"] = {"arm": "BD", "cross": "first", "echo": ("Q", 0.0, True, True), "echo_mode": "skip"}
    R["X4+E2-J"] = {"arm": "BD", "cross": "X4", "echo": ("J", 0.5, True, True), "echo_mode": "skip"}
    R["X4+E3-J"] = {"arm": "BD", "cross": "X4", "echo": ("J", 0.5, True, True), "echo_mode": "next"}
    R["X4+E4"] = {"arm": "BD", "cross": "X4", "echo": ("Q", 0.0, True, True), "echo_mode": "skip"}
    R["X1+E2-J"] = {"arm": "BD", "cross": "X1", "echo": ("J", 0.5, True, True), "echo_mode": "skip"}
    R["X1+E3-J"] = {"arm": "BD", "cross": "X1", "echo": ("J", 0.5, True, True), "echo_mode": "next"}
    R["X2(δ=0.05)+E2-J"] = {"arm": "BD", "cross": "X2", "delta": 0.05, "echo": ("J", 0.5, True, True), "echo_mode": "skip"}
    return R


def resolve(rule):
    r = dict(rule)
    if r.get("echo"):
        nm, tau, nq, nd = r["echo"]
        r["echo"] = (ECHO_FNS[nm], tau, nq, nd)
    return r


def analyze():
    res = {"note": "诊断 ≠ 判定：规则事后写成（看过 RESULTS_body_date 三类失败题），阈值网格只为看敏感度，不据此选值；保留集 crossproj-zh-bodydate 未打开。",
           "sets": {}}
    RU = rules()
    for s in ("perltqa", "locomo"):
        p = cache_path(s)
        if not p.exists():
            continue
        D = json.loads(p.read_text(encoding="utf-8"))
        qs = sorted(D)
        # 0. 模拟器复现：L1 / BD 逐题 ≡ answer_time / answer_time_q
        for q in qs:
            for arm in ("L1", "BD"):
                sim = simulate(D[q], resolve(RU[arm]))
                assert sim["pred"] == D[q][arm]["pred"] or RV.granularity(D[q]["q"], sim["pred"]) == D[q][arm]["pred"], (s, q, arm, sim, D[q][arm])
                assert sim["ok"] == D[q][arm]["ok"], (s, q, arm, sim, D[q][arm])
        S = {"n": len(qs), "replicate_L1_BD": True, "rules": {}, "l1_formal": {}, "echo_scan": []}
        # 1. L1「存疑落到下一候选」形式化
        F = collections.Counter(); lst = collections.defaultdict(list)
        for q in qs:
            r = D[q]; sim = simulate(r, resolve(RU["L1"]))
            if not sim["ok"]:
                continue
            key = "rank1" if sim["rank"] == 0 else None
            if key is None and sim["rank"] is not None:
                skipped = r["cands"][:sim["rank"]]
                if any(l1_interf(c) for c in skipped):
                    key = "skip_via_interference"
                else:
                    key = "skip_via_no_time"
            if key is None:
                key = "session"
            F[(r.get("cls") or "-", key)] += 1; lst[key].append(q)
        S["l1_formal"] = {"by_cls_key": {f"{a}|{b}": n for (a, b), n in sorted(F.items())}, "lists": dict(lst)}
        # 2. 规则逐题
        base = {q: simulate(D[q], resolve(RU["L1"])) for q in qs}
        bd = {q: simulate(D[q], resolve(RU["BD"])) for q in qs}
        for nm, rule in RU.items():
            out = {q: simulate(D[q], resolve(rule)) for q in qs}
            fix = [q for q in qs if out[q]["ok"] and not bd[q]["ok"]]
            hurt_bd = [q for q in qs if bd[q]["ok"] and not out[q]["ok"]]
            hurt_l1 = [q for q in qs if base[q]["ok"] and not out[q]["ok"]]
            win_l1 = [q for q in qs if out[q]["ok"] and not base[q]["ok"]]
            first_hurt = [q for q in hurt_l1 if D[q].get("cls") == "first"]
            S["rules"][nm] = {"spec": {k: (list(v[:1]) + list(v[1:]) if isinstance(v, tuple) else v) for k, v in rule.items()},
                              "correct": sum(out[q]["ok"] for q in qs), "vs_L1_win": win_l1, "vs_L1_loss": hurt_l1,
                              "vs_BD_fix": fix, "vs_BD_hurt": hurt_bd, "first_L1ok_now_wrong": first_hurt,
                              "mcn_vs_L1": RV.mcn([out[q]["ok"] for q in qs], [base[q]["ok"] for q in qs]),
                              "changed_vs_L1": {q: {"L1": base[q]["pred"], "rule": out[q]["pred"], "ok": out[q]["ok"], "src": out[q]["src"]}
                                                for q in qs if out[q]["pred"] != base[q]["pred"]}}
        # 3. 回声扫描：每题被 BD 选中的子痕迹 + 全部子痕迹里回声度最高者（描述性）
        for q in qs:
            r = D[q]
            for c in r["cands"]:
                if "bd" not in c:
                    continue
                top = max(c["bd"], key=lambda x: x["qcos"])
                hj = max(c["bd"], key=lambda x: echo_j(x["text"], r["q"]))
                S["echo_scan"].append({"q": q, "rank": c["rank"], "is_gold": c["is_gold"], "top_qcos": round(top["qcos"], 3),
                                       "top_J": round(echo_j(top["text"], r["q"]), 3), "top_C": round(echo_c(top["text"], r["q"]), 3),
                                       "top_isq": bool(IS_Q.search(top["text"])), "top_kind": top["kind"], "top_text": top["text"][:80],
                                       "max_J": round(echo_j(hj["text"], r["q"]), 3), "max_J_text": hj["text"][:80]})
        # 4. 回声规则波及面：te10 内全部子痕迹（去重）里被各回声规则标记的句数（描述性）
        seen, fl = set(), collections.Counter()
        for q in qs:
            r = D[q]
            for c in r["cands"]:
                for x in c.get("bd", []):
                    key = (q, x["j"])
                    if key in seen:
                        continue
                    seen.add(key); fl["total"] += 1
                    isq, nod, J, C = bool(IS_Q.search(x["text"])), x["kind"] in ("inherit", "pre"), echo_j(x["text"], r["q"]), echo_c(x["text"], r["q"])
                    fl["E4 问句形+无本句日期"] += isq and nod
                    fl["E2 J≥0.5+问句形+无本句日期"] += isq and nod and J >= 0.5
                    fl["E1 J≥0.5"] += J >= 0.5
                    fl["E1 C≥0.5"] += C >= 0.5
        S["echo_flag_counts_qxsub"] = dict(fl)
        res["sets"][s] = S
    (HERE / "bd_v02_diag.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# body_date v0.2 dev 诊断（描述性；不是判定）", "", res["note"], ""]
    for s, S in res["sets"].items():
        md += [f"## {s}（{S['n']} 时间题）", "", "L1 答对题的来源：" + json.dumps(S["l1_formal"]["by_cls_key"], ensure_ascii=False), "",
               "| 规则 | 对 | 胜/负 vs L1 | 修 BD 错 | 伤 BD 对 | first 类 L1 对→错 |", "|---|---:|---|---|---|---|"]
        for nm, x in S["rules"].items():
            md.append(f"| {nm} | {x['correct']} | {len(x['vs_L1_win'])}/{len(x['vs_L1_loss'])} | {', '.join(x['vs_BD_fix']) or '—'} | "
                      f"{', '.join(x['vs_BD_hurt']) or '—'} | {', '.join(x['first_L1ok_now_wrong']) or '—'} |")
        md.append("")
    (HERE / "bd_v02_diag.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", choices=["perltqa", "locomo"]); ap.add_argument("--analyze", action="store_true")
    a = ap.parse_args()
    if a.dump == "perltqa":
        dump_perltqa()
    elif a.dump == "locomo":
        dump_locomo()
    if a.analyze:
        analyze()


if __name__ == "__main__":
    main()
