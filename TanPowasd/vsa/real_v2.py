# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""阶段 2 真实集（PREREG_v2 §A LoCoMo dev 时间题 te 召回 + VSA 解绑；§B PerLTQA dev 中文时间题）。只跑 dev，不跑任何 test。
  python -X utf8 real_v2.py --set locomo     # → $VSA_OUT/runs/dev/v2_locomo.json
  python -X utf8 real_v2.py --set perltqa    # → $VSA_OUT/runs/dev/v2_perltqa.json
  python -X utf8 real_v2.py --summary        # → results/real_v2.json/.md
候选只读 $UMB_OUT/runs/dev/<集>/{te,bm25}.json 的 top10（不重跑、不改 agm/）；阶段 1 预测读 $VSA_OUT/runs/dev/locomo.json。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, datetime, hashlib, json, pathlib, re, time

HERE = pathlib.Path(__file__).resolve().parent
import real as R1  # noqa: E402  （导入即设好 sys.path：agm/umb、agm/bench、agm/all 只读）
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
from cleanup import DOUBT  # noqa: E402

OUT, UMB, UMB_OUT = R1.OUT, R1.UMB, R1.UMB_OUT
K_TE = 10
TD = datetime.timedelta
CFG = {"te_restrict": True, "granularity": True}     # 守卫变异通过改这里关掉对应机制


# ---------------------------------------------------------------- 作答策略
def candidates(top, m, names, restrict=None, n_all=None):
    """te 候选：只取缓存 top10（te_restrict=False 时为变异：回退到全库，候选 = top10 + 其余按写入序）。"""
    restrict = CFG["te_restrict"] if restrict is None else restrict
    cand = list(top[:K_TE])
    if not restrict:
        cand += [i for i in range(n_all if n_all is not None else len(m)) if i not in set(cand)]
    if names:
        f = [i for i in cand if m.texts[i].split(": ", 1)[0] in names]
        cand = f or cand
    return cand


def answer_time(m, cand, k):
    """显式时间优先（PREREG_v2 §A）：候选前 k 个中第一个 TIME 解绑非存疑者；否则候选第一个的 SESSION；否则存疑。→ (答案, 轮, 来源)。"""
    for i in cand[:k]:
        a = R1.decode_time(m, i)
        if a[0] not in (DOUBT, "容量拒写"):
            return a[0], i, "TIME"
    if cand:
        try:
            a = m.decode(cand[0], "SESSION")
        except H.CapacityError:
            a = ("容量拒写",)
        if a[0] not in (DOUBT, "容量拒写"):
            return a[0], cand[0], "SESSION"
    return DOUBT, None, None


def answer_time_q(m, cand, k, question):
    """正文日期 BD 作答（PREREG_body_date §1.8）：同 answer_time，只把单元 TIME 解绑换成带问句的 m.decode_q（Memory.units() 视图）。
    来源：无子痕迹 ⇒ "TIME"（≡ answer_time）；子痕迹 ⇒ "TIME:bd"；最大余弦 ≤ 0 的显式回退 ⇒ "TIME:fallback"。answer_time 不动。"""
    for i in cand[:k]:
        try:
            a = m.decode_q(i, "TIME", question)
        except H.CapacityError:
            a = ("容量拒写",) * 5
        if a[0] not in (DOUBT, "容量拒写"):
            return a[0], i, "TIME" if a[4] == "l1" else f"TIME:{a[4]}"
    if cand:
        try:
            a = m.decode(cand[0], "SESSION")
        except H.CapacityError:
            a = ("容量拒写",)
        if a[0] not in (DOUBT, "容量拒写"):
            return a[0], cand[0], "SESSION"
    return DOUBT, None, None


GRAN_Q = [("YEAR", re.compile(r"\b(what|which|in what) year\b|哪一?年", re.I)),
          ("MONTH", re.compile(r"\b(what|which|in what) month\b|哪个月|哪月|几月", re.I))]


def _d(s):
    return datetime.date.fromisoformat(s)


def anchor_date(f):
    """规范填充 → 代表日期（粗化用；PREREG_v2 §A 粗化表）。"""
    k, _, v = f.partition(":")
    if k == "DATE":
        return _d(v)
    if k == "BEFORE":
        w, _, d = v.partition(":")
        n = int(w[:-5]) if w.endswith("weeks") else 1
        return _d(d) - TD(days=7 * n) if w in ("week", "weekend") or w.endswith("weeks") else M.wd_before(_d(d), M.WEEKDAYS_EN[w])
    if k == "WEEKEND_OF":
        return _d(v)
    if k == "FEWDAYS":
        return _d(v) - TD(days=3)                  # 推断：「几天前」取中值 3
    if k == "AFTER":
        return _d(v.partition(":")[2]) + TD(days=7)
    return None


def granularity(q, f, on=None):
    on = CFG["granularity"] if on is None else on
    if not on or not f or f == DOUBT:
        return f
    want = next((g for g, rx in GRAN_Q if rx.search(q)), None)
    if want is None:
        return f
    k = f.split(":", 1)[0]
    if want == "YEAR":
        if k == "MONTH":
            return f"YEAR:{f[6:10]}"
        d = anchor_date(f)
        return f"YEAR:{d.year}" if d else f
    if want == "MONTH" and k not in ("MONTH", "YEAR"):
        d = anchor_date(f)
        return f"MONTH:{d.year:04d}-{d.month:02d}" if d else f
    return f


# ---------------------------------------------------------------- 判定 J2（PREREG_v2 §A）
_MON3 = {k[:3]: v for k, v in M.MONTHS.items()}
_MW = r"([a-z]{3,})"


def _mon(w):
    return _MON3.get(w[:3]) if w and len(w) >= 3 else None


def _clean(s):
    s = str(s).strip().lower()
    s = re.sub(r"(\d)([a-z])", r"\1 \2", s)                 # 15April → 15 april（先拆，后去序数）
    s = re.sub(r"\b(\d{1,2}) (st|nd|rd|th)\b", r"\1", s)     # 15 th → 15
    s = re.sub(r"[.\s]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^(in|on|around|approximately|about) ", "", s)
    return s


def _full(s):
    m = re.fullmatch(r"(\d{1,2}) " + _MW + r",? (\d{4})", s) or None
    if m:
        d, mo, y = m.groups()
    else:
        m = re.fullmatch(_MW + r" (\d{1,2}),? (\d{4})", s)
        if not m:
            return None
        mo, d, y = m.groups()
    if not _mon(mo):
        return None
    try:
        return datetime.date(int(y), _mon(mo), int(d))
    except ValueError:
        return None


def canon_gold_v2(ans):
    s = _clean(ans)
    m = re.fullmatch(r"(?:the )?(" + "|".join(M.WEEKDAYS_EN) + r") before (.+)", s)
    if m and _full(m.group(2)):
        return M.t_date(M.wd_before(_full(m.group(2)), M.WEEKDAYS_EN[m.group(1)]))
    m = re.fullmatch(r"(?:the |last )?week before (.+)", s)
    if m and _full(m.group(1)):
        return f"BEFORE:week:{_full(m.group(1)).isoformat()}"
    m = re.fullmatch(r"(?:the )?weekend before (.+)", s)
    if m and _full(m.group(1)):
        return f"BEFORE:weekend:{_full(m.group(1)).isoformat()}"
    m = re.fullmatch(r"(\d+|one|two|three|four|five|six) weeks? before (.+)", s)
    if m and _full(m.group(2)):
        n = M._num(m.group(1))
        return f"BEFORE:{'week' if n == 1 else f'{n}weeks'}:{_full(m.group(2)).isoformat()}"
    m = re.fullmatch(r"(?:a )?few days before (.+)", s)
    if m and _full(m.group(1)):
        return f"FEWDAYS:{_full(m.group(1)).isoformat()}"
    m = re.fullmatch(r"the weekend of (.+)", s)
    if m and _full(m.group(1)):
        return f"WEEKEND_OF:{_full(m.group(1)).isoformat()}"
    if _full(s):
        return M.t_date(_full(s))
    m = re.fullmatch(_MW + r",? (\d{4})", s)
    if m and _mon(m.group(1)):
        return f"MONTH:{int(m.group(2)):04d}-{_mon(m.group(1)):02d}"
    if re.fullmatch(r"\d{4}", s):
        return f"YEAR:{s}"
    m = re.fullmatch(r"(\d{1,2}) " + _MW, s) or re.fullmatch(_MW + r" (\d{1,2})", s)
    if m:
        a, b = m.groups()
        d, mo = (a, b) if a.isdigit() else (b, a)
        if _mon(mo) and 1 <= int(d) <= 31:
            return f"MD:{_mon(mo):02d}-{int(d):02d}"
    m = re.fullmatch(_MW, s)
    if m and _mon(m.group(1)) and m.group(1) in M.MONTHS:
        return f"M:{_mon(m.group(1)):02d}"
    return None


def norm_pred(p, weekday_to_date=True):
    """预测侧规范：BEFORE:<星期>:D → DATE（与金标同一换算）。"""
    if not p or p == DOUBT:
        return p
    k, _, v = p.partition(":")
    if weekday_to_date and k == "BEFORE":
        w, _, d = v.partition(":")
        if w in M.WEEKDAYS_EN:
            return M.t_date(M.wd_before(_d(d), M.WEEKDAYS_EN[w]))
    return p


def judge2(gold_c, pred, weekday_to_date=True):
    if gold_c is None or not pred or pred == DOUBT:
        return False
    p = norm_pred(pred, weekday_to_date)
    if gold_c.startswith("MD:"):
        return p.startswith("DATE:") and p[-5:] == gold_c[3:]
    if gold_c.startswith("M:"):
        return p.startswith("MONTH:") and p[-2:] == gold_c[2:]
    return p == gold_c


def interval(f):
    """规范填充 → 日期区间（描述性「粒度包含」用；推断性区间，见 PREREG_v2）。"""
    if not f or f == DOUBT:
        return None
    k, _, v = f.partition(":")
    try:
        if k == "DATE":
            d = _d(v); return d, d
        if k == "MONTH":
            y, mo = int(v[:4]), int(v[5:7])
            a = datetime.date(y, mo, 1); b = datetime.date(y + (mo == 12), mo % 12 + 1, 1) - TD(days=1); return a, b
        if k == "YEAR":
            return datetime.date(int(v), 1, 1), datetime.date(int(v), 12, 31)
        if k == "BEFORE":
            w, _, d = v.partition(":"); d = _d(d)
            if w == "week":
                return d - TD(days=7), d - TD(days=1)
            if w == "weekend":
                s = M.wd_before(d, 7); return s - TD(days=1), s
            if w.endswith("weeks"):
                n = int(w[:-5]); return d - TD(days=7 * n + 3), d - TD(days=7 * n - 3)
            x = M.wd_before(d, M.WEEKDAYS_EN[w]); return x, x
        if k == "WEEKEND_OF":
            d = _d(v); s = d + TD(days=(6 - d.isoweekday()) % 7) if d.isoweekday() != 7 else d - TD(days=1); return s, s + TD(days=1)
        if k == "FEWDAYS":
            d = _d(v); return d - TD(days=6), d - TD(days=2)
        if k == "AFTER":
            d = _d(v.partition(":")[2]); return d + TD(days=1), d + TD(days=7)
    except (ValueError, KeyError):
        return None
    return None


def contained(gold_c, pred):
    g, p = interval(gold_c), interval(norm_pred(pred))
    return bool(g and p and g[0] <= p[0] and p[1] <= g[1])


# ---------------------------------------------------------------- LoCoMo
def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() if pathlib.Path(p).exists() else None


def build_mem(it, conv, spk, rules):
    m = M.Memory(H.Space("vsa-v1"), chunk_long=False)   # 历史读数口径 S0（逐单元下标）
    for t, did in zip(it["turns"], it["ids"]):
        d = M.parse_en_date(conv[f"session_{int(did.split(':')[0].lstrip('D'))}_date_time"])
        s = t.split(": ", 1)[0] if ": " in t[:40] else None
        if rules == "v1":
            m.write(t, persons=spk, speaker=s, base_date=d, base_time=M.t_date(d) if d else None, weekday=False)
        else:
            m.write(t, persons=spk, speaker=s, base_date=d, weekday=False, time_rules="v2", session=M.t_date(d) if d else None)
    return m


def run_locomo():
    import build_umb as BU
    tep = UMB_OUT / "runs" / "dev" / "locomo" / "te.json"
    te = json.loads(tep.read_text(encoding="utf-8"))["per"]
    v1 = json.loads((OUT / "runs" / "dev" / "locomo.json").read_text(encoding="utf-8"))["time"]
    sp = json.loads((UMB / "locomo" / "split.json").read_text(encoding="utf-8"))["dev"]
    qs = {}
    with open(UMB / "locomo" / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line); qs[o["_id"]] = o
    raw = {x["sample_id"]: x["conversation"] for x in json.loads(BU.resolve(BU.tok("UMB_LOCOMO")).read_text(encoding="utf-8"))}
    items = {it["sid"]: it for it in BU.locomo_conv_items()}
    tq = collections.defaultdict(list)
    for q in sp:
        x = items[qs[q]["sid"]]["qa"][qs[q]["qi"]]
        if R1.TIME_Q.search(x["question"]):
            tq[qs[q]["sid"]].append(q)
    per = {}
    t0 = time.time()
    for sid, ql in tq.items():
        it, conv = items[sid], raw[sid]
        spk = [conv["speaker_a"], conv["speaker_b"]]
        mem = {r: build_mem(it, conv, spk, r) for r in ("v1", "v2")}
        idx = {d: i for i, d in enumerate(it["ids"])}
        for q in ql:
            x = it["qa"][qs[q]["qi"]]
            qt = x["question"]
            gold = sorted({idx[e] for e in BU.locomo_gold(it, x)})
            names = [p for p in spk if re.search(r"\b" + re.escape(p) + r"\b", qt)]
            top = te[q]["top10"]
            row = {"q": qt, "gold": str(x["answer"]), "J1_gold": R1.canon_gold(x["answer"]), "J2_gold": canon_gold_v2(x["answer"]),
                   "te_first_is_gold": bool(top) and candidates(top, mem["v2"], names)[0] in gold,
                   "te_any_gold": any(i in gold for i in top[:K_TE])}
            row["A0"] = {"pred": v1[q]["pred"]}
            row["O1"] = {"preds": v1[q]["oracle"]}
            arms = {"A1": ("v1", names, 1, False), "A2": ("v2", names, 1, True), "A3": ("v2", names, K_TE, True), "A4": ("v2", [], K_TE, True)}
            for a, (r, nm, k, gran) in arms.items():
                ans, tr, src = answer_time(mem[r], candidates(top, mem[r], nm), k)
                row[a] = {"pred": granularity(qt, ans) if gran else ans, "raw": ans, "trace": tr, "src": src, "trace_is_gold": tr in gold}
            row["O2"] = {"preds": [granularity(qt, answer_time(mem["v2"], [g], 1)[0]) for g in gold]}
            row["A3"]["k_sweep"] = {str(k): granularity(qt, answer_time(mem["v2"], candidates(top, mem["v2"], names), k)[0]) for k in (1, 3, 10)}
            per[q] = row
        print(f"locomo {sid} q={len(ql)} n={len(it['turns'])} {time.time() - t0:.0f}s", flush=True)
    out = {"prereg": "PREREG_v2.md §A", "te_cache": "$UMB_OUT/runs/dev/locomo/te.json", "te_sha256": sha(tep),
           "v1_cache_sha256": sha(OUT / "runs" / "dev" / "locomo.json"), "per": per}
    p = OUT / "runs" / "dev" / "v2_locomo.json"; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("locomo 完成", len(per), f"{time.time() - t0:.0f}s")


# ---------------------------------------------------------------- PerLTQA（§B）
ZH_TIME_Q = re.compile(r"什么时候|何时|哪一?年|哪一?天|几月|哪个月|哪月|几号")


def perltqa_answers():
    """只读重放 agm/all/perltqa.load 的同一遍历序，取每题 Answer 文本（不改 agm/all）。"""
    import perltqa as P
    r = P.root()
    qa = json.loads((r / "perltqa.json").read_bytes())
    ans = {}
    for blk in qa:
        for name, cats in blk.items():
            k = 0
            for cat in ("profile", "social_relationship", "events", "dialogues"):
                l = cats.get(cat, [])
                items = l if isinstance(l, list) else [z for _, zs in l.items() for z in zs]
                for z in items:
                    ans[f"{name}#{cat}#{k}"] = z.get("Answer"); k += 1
    return ans


def canon_zh(s):
    t = M.extract_time_v2(str(s or ""), None, lang="zh")
    return t[0][1] if t and not t[0][1].startswith("WD:") else None


def run_perltqa():
    import perltqa as P
    data, _ = P.load()
    A = perltqa_answers()
    tops = {a: json.loads((UMB_OUT / "runs" / "dev" / "perltqa" / f"{a}.json").read_text(encoding="utf-8"))["per"] for a in ("te", "bm25")}
    per = {}
    t0 = time.time()
    for nm in sorted(data):
        if P.split_of(nm) != "dev":
            continue
        d = data[nm]
        ql = [(q, x, g) for q, x, g in d["qs"] if ZH_TIME_Q.search(x)]
        if not ql:
            continue
        m = M.Memory(H.Space("vsa-v1"), chunk_long=False)   # 历史读数口径 S0（逐单元下标）
        for t in d["texts"]:
            m.write(t, roles=M.extract_time_v2(t, None, lang="zh"))       # 只写 TIME（PREREG_v2 §B）
        for q, x, g in ql:
            gc = canon_zh(A.get(q))
            row = {"q": x, "gold": A.get(q), "gold_canon": gc}
            for a in ("te", "bm25"):
                ans, tr, _ = answer_time(m, candidates(tops[a][q]["top10"], m, [], n_all=len(m)), K_TE)
                row[a] = {"pred": granularity(x, ans), "trace_is_gold": tr in g}
            row["oracle"] = [granularity(x, answer_time(m, [i], 1)[0]) for i in sorted(g)]
            per[q] = row
        print(f"perltqa {nm} q={len(ql)} n={len(d['texts'])} {time.time() - t0:.0f}s", flush=True)
    p = OUT / "runs" / "dev" / "v2_perltqa.json"; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"prereg": "PREREG_v2.md §B", "te_sha256": sha(UMB_OUT / "runs" / "dev" / "perltqa" / "te.json"),
                             "per": per}, ensure_ascii=False), encoding="utf-8")
    print("perltqa 完成", len(per), f"{time.time() - t0:.0f}s")


# ---------------------------------------------------------------- 汇总
def mcn(a, b):
    w = sum(x and not y for x, y in zip(a, b)); l = sum(y and not x for x, y in zip(a, b))
    return {"win": w, "loss": l, "p": R1.sign_p(w, l),
            "verdict": "显著提升" if R1.sign_p(w, l) < 0.05 and w > l else "显著下降" if R1.sign_p(w, l) < 0.05 and l > w else "无显著差异"}


def summary():
    res, md = {}, ["# VSA 阶段 2 · 真实集 dev 读数（PREREG_v2 §A §B）", ""]
    p = OUT / "runs" / "dev" / "v2_locomo.json"
    if p.exists():
        D = json.loads(p.read_text(encoding="utf-8")); P = D["per"]; qs = list(P)
        n = len(qs)
        ok = {}
        for a in ("A0", "A1", "A2", "A3", "A4"):
            ok[("J1", a)] = [P[q]["J1_gold"] is not None and P[q][a]["pred"] == P[q]["J1_gold"] for q in qs]
            ok[("J2", a)] = [judge2(P[q]["J2_gold"], P[q][a]["pred"]) for q in qs]
            ok[("包含", a)] = [contained(P[q]["J2_gold"], P[q][a]["pred"]) for q in qs]
        for a in ("O1", "O2"):
            ok[("J1", a)] = [P[q]["J1_gold"] is not None and P[q]["J1_gold"] in P[q][a]["preds"] for q in qs]
            ok[("J2", a)] = [any(judge2(P[q]["J2_gold"], x) for x in P[q][a]["preds"]) for q in qs]
            ok[("包含", a)] = [any(contained(P[q]["J2_gold"], x) for x in P[q][a]["preds"]) for q in qs]
        acc = {f"{j}/{a}": sum(v) / n for (j, a), v in ok.items()}
        comp = {}
        for j in ("J1", "J2"):
            for x, y in (("A3", "A0"), ("O2", "O1"), ("A1", "A0"), ("A2", "A1"), ("A3", "A2"), ("A4", "A3")):
                comp[f"{j}:{x}vs{y}"] = mcn(ok[(j, x)], ok[(j, y)])
        ks = {k: sum(judge2(P[q]["J2_gold"], P[q]["A3"]["k_sweep"][k]) for q in qs) / n for k in ("1", "3", "10")}
        res["locomo"] = {"n": n, "acc": acc, "mcnemar": comp, "te_sha256": D["te_sha256"],
                         "J1_canon": sum(P[q]["J1_gold"] is not None for q in qs), "J2_canon": sum(P[q]["J2_gold"] is not None for q in qs),
                         "te_first_is_gold": sum(P[q]["te_first_is_gold"] for q in qs) / n, "te_any_gold": sum(P[q]["te_any_gold"] for q in qs) / n,
                         "fuse_first_is_gold_v1": None, "A3_trace_is_gold": sum(P[q]["A3"]["trace_is_gold"] for q in qs) / n,
                         "A3_src": dict(collections.Counter(P[q]["A3"]["src"] or "存疑" for q in qs)), "A3_k_sweep_J2": ks}
        f3 = lambda x: f"{x:.3f}"
        md += ["## (A) LoCoMo dev 时间题（50 题；te 缓存 sha256 `" + (D["te_sha256"] or "存疑")[:16] + "…`）", "",
               f"金标可规范化：J1 {res['locomo']['J1_canon']}/{n}，J2 {res['locomo']['J2_canon']}/{n}。te10 首候选=金标轮 {f3(res['locomo']['te_first_is_gold'])}，"
               f"te10 含金标轮 {f3(res['locomo']['te_any_gold'])}；A3 解绑所用轮=金标轮 {f3(res['locomo']['A3_trace_is_gold'])}；A3 答案来源 {res['locomo']['A3_src']}。", "",
               "| 臂 | 候选 | 规则 | K | J1（v1 判定） | **J2（v2 判定）** | 粒度包含（描述性） |", "|---|---|---|---:|---:|---:|---:|"]
        desc = {"A0": ("fuse", "v1", "1"), "A1": ("te10", "v1", "1"), "A2": ("te10", "v2", "1"), "A3": ("te10", "v2", "10"), "A4": ("te10 无说话人过滤", "v2", "10"),
                "O1": ("金标证据轮", "v1", "—"), "O2": ("金标证据轮", "v2", "—")}
        for a, (c, r, k) in desc.items():
            b = "**" if a == "A3" else ""
            md.append(f"| {b}{a}{b} | {c} | {r} | {k} | {f3(acc['J1/' + a])} | {b}{f3(acc['J2/' + a])}{b} | {f3(acc['包含/' + a])} |")
        md += ["", "配对精确 McNemar（胜/负，双侧 p，判定）：", "", "| 比较 | J1 | J2 |", "|---|---|---|"]
        for x, y in (("A3", "A0"), ("O2", "O1"), ("A1", "A0"), ("A2", "A1"), ("A3", "A2"), ("A4", "A3")):
            t = lambda c: f"{c['win']}/{c['loss']} p={c['p']:.3g} {c['verdict']}"
            md.append(f"| {x} vs {y}{'（主）' if x == 'A3' and y == 'A0' else ''} | {t(comp['J1:' + x + 'vs' + y])} | {t(comp['J2:' + x + 'vs' + y])} |")
        md += ["", "A3 的 K 扫描（J2，描述性）：" + "，".join(f"K={k} {f3(v)}" for k, v in ks.items())]
    p = OUT / "runs" / "dev" / "v2_perltqa.json"
    if p.exists():
        P = json.loads(p.read_text(encoding="utf-8"))["per"]; qs = list(P); n = len(qs)
        canon = [q for q in qs if P[q]["gold_canon"]]
        okt = [P[q]["gold_canon"] is not None and P[q]["te"]["pred"] == P[q]["gold_canon"] for q in qs]
        okb = [P[q]["gold_canon"] is not None and P[q]["bm25"]["pred"] == P[q]["gold_canon"] for q in qs]
        oko = [P[q]["gold_canon"] is not None and P[q]["gold_canon"] in P[q]["oracle"] for q in qs]
        c = mcn(okt, okb)
        res["perltqa"] = {"n": n, "n_canon": len(canon), "te10": sum(okt) / max(1, n), "bm25_10": sum(okb) / max(1, n), "oracle": sum(oko) / max(1, n),
                          "te10_canon": sum(okt) / max(1, len(canon)), "bm25_10_canon": sum(okb) / max(1, len(canon)), "oracle_canon": sum(oko) / max(1, len(canon)),
                          "te_vs_bm25": c, "te_trace_is_gold": sum(P[q]["te"]["trace_is_gold"] for q in qs) / max(1, n)}
        r = res["perltqa"]
        md += ["", "## (B) PerLTQA dev 中文时间题（描述性，未参与规则设计）", "",
               "| 题数 | 金标可规范化 | te10+VSA | bm25-10+VSA | oracle | te10 /可规范化 | bm25-10 /可规范化 | oracle /可规范化 | te10 解绑轮=金标 | te vs bm25 胜/负 p |",
               "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
               f"| {n} | {len(canon)} | {r['te10']:.3f} | {r['bm25_10']:.3f} | {r['oracle']:.3f} | {r['te10_canon']:.3f} | {r['bm25_10_canon']:.3f} | {r['oracle_canon']:.3f} | "
               f"{r['te_trace_is_gold']:.3f} | {c['win']}/{c['loss']} p={c['p']:.3g} |"]
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "real_v2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "results" / "real_v2.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["locomo", "perltqa"]); ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        return summary()
    {"locomo": run_locomo, "perltqa": run_perltqa}[a.set]()


if __name__ == "__main__":
    main()
