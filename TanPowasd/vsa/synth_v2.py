# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""合成基准 v2（PREREG_v2 §C）：抽取噪声（代词 / 省略主语 / 规则内改写 / 规则外改写）+ 多跳（T4 两次解绑求交、T5 链式）。VSA vs BM25 vs 符号表。
  python -X utf8 synth_v2.py            # → results/synth_v2.json/.md
数据只在内存里生成，不落盘、不入库。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import collections, itertools, json, pathlib, random, re, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import bm25 as B  # noqa: E402
import synth as S1  # noqa: E402
from cleanup import DOUBT  # noqa: E402

SEED = "vsa-synth-v2"
N_STREAMS = 60
CLASSES = ("C0", "C1", "C2", "C3", "C4")
GENDER = {"小王": "他", "李娜": "她", "张伟": "他", "陈静": "她", "刘洋": "他", "王芳": "她", "赵磊": "他", "孙丽": "她", "周杰": "他", "吴敏": "她",
          "Alice": "She", "Bob": "He", "Carol": "She", "Dave": "He", "Erin": "She", "Frank": "He", "Grace": "She", "Heidi": "She", "Ivan": "He", "Judy": "She"}
TPL = {"zh": {"lead": "{X}{d}一早就出门了。", "C1": "{P}和{Y}去{p}{a}了。", "C2": "跟{Y}去{p}{a}了。", "C3": "{X}{d}同{Y}到{p}{a}。", "C4": "{Y}{d}陪{X}在{p}{a}。",
              "q4": "{X}和{Y}都去过哪里？", "q5": "{X}{d}的同伴{e}去了哪？", "q5b": "{Y}{e}去了哪？"},
       "en": {"lead": "{X} left home early on {d}.", "C1": "{P} went to the {p} with {Y} for {a}.", "C2": "Went to the {p} with {Y} for {a}.",
              "C3": "{X} and {Y} spent {d} at the {p}, {a}.", "C4": "{Y} joined {X} at the {p} for {a} on {d}.",
              "q4": "Which places did both {X} and {Y} go to?", "q5": "On {e}, where did the person who was with {X} on {d} go?",
              "q5b": "Where did {Y} go on {e}?"}}
Q5_RE = {"zh": re.compile(r"^(.+?)(周.)的同伴(周.)去了哪？$"), "en": re.compile(r"^On (\w+), where did the person who was with (\w+) on (\w+) go\?$")}
CFG = {"intersect": True}          # 守卫变异：多跳不求交（求并）


def gen_stream(k):
    """→ lang, sents, events[(句号, X, Y, 天号, 动作, 地点, 类)], names, rng。"""
    rng = random.Random(f"{SEED}|{k}")
    lang = "zh" if k % 2 == 0 else "en"
    L, T = (S1.ZH if lang == "zh" else S1.EN), TPL[lang]
    chats = collections.defaultdict(list)
    for _ in range(S1.N_CHAT):
        X, Y = rng.sample(L["names"], 2)
        chats[rng.randrange(7)].append([("C", rng.choice(L["chat"]).format(X=X, Y=Y, d=L["days"][rng.randrange(7)], p=rng.choice(L["places"])), None)])
    sents, events = [], []
    for d in range(7):
        ppl = rng.sample(L["names"], 2 * S1.N_PAIRS)
        units = []
        for j in range(S1.N_PAIRS):
            X, Y = ppl[2 * j], ppl[2 * j + 1]
            a, p = rng.choice(L["acts"]), rng.choice(L["places"])
            c = rng.choice(CLASSES)
            kw = dict(X=X, Y=Y, d=L["days"][d], p=p, a=a, P=GENDER[X])
            ev = (X, Y, d, a, p, c)
            if c == "C0":
                units.append([("E", rng.choice(L["ev"]).format(**kw), ev)])
            elif c in ("C1", "C2"):
                units.append([("L", T["lead"].format(**kw), None), ("E", T[c].format(**kw), ev)])
            else:
                units.append([("E", T[c].format(**kw), ev)])
        units += chats[d]
        rng.shuffle(units)
        for u in units:
            for kind, s, ev in u:
                if kind == "E":
                    events.append((len(sents),) + ev)
                sents.append(s)
    return lang, sents, events, L["names"], rng


def write_stream(sents, names, coref=True):
    m = M.Memory(H.Space("vsa-v1"))
    prev = None
    for s in sents:
        i = m.write(s, persons=names, prev=prev if coref else None)
        rs = m.roles[i]
        prev = {"AGENT": next((f for r, f, *_ in rs if r == "AGENT"), None), "TIME": next((f for r, f, *_ in rs if r == "TIME"), None)}
    return m


def questions(lang, events, names, rng):
    L = S1.ZH if lang == "zh" else S1.EN
    T = TPL[lang]
    canon = (lambda a: a) if lang == "zh" else (lambda a: M.ACTIONS_EN[a])
    qs = []
    for i, X, Y, d, a, p, c in events:
        for me, other in ((X, Y), (Y, X)):
            qs.append({"typ": "T1", "q": L["q1"].format(X=me, d=L["days"][d]), "gold": {"PERSON": other, "PLACE": p}, "gi": i, "cls": c})
            qs.append({"typ": "T3", "q": L["q3"].format(X=me, d=L["days"][d]), "gold": {"ACTION": canon(a)}, "gi": i, "cls": c})
    cnt = collections.Counter((pp, e[5]) for e in events for pp in (e[1], e[2]))
    for i, X, Y, d, a, p, c in events:
        for me in (X, Y):
            if cnt[(me, p)] == 1:
                qs.append({"typ": "T2", "q": L["q2"].format(X=me, p=p), "gold": {"TIME": f"WD:{d + 1}"}, "gi": i, "cls": c})
    places = collections.defaultdict(set); cls_of = collections.defaultdict(set)
    for i, X, Y, d, a, p, c in events:
        for z in (X, Y):
            places[z].add(p); cls_of[z].add(c)
    for X, Y in itertools.combinations(names, 2):
        g = places[X] & places[Y]
        if g:
            qs.append({"typ": "T4", "q": T["q4"].format(X=X, Y=Y), "gold": {"PLACES": sorted(g)}, "gi": None,
                       "cls": "含C4" if "C4" in cls_of[X] | cls_of[Y] else "C0-C3", "_xy": (X, Y)})
    by = {(z, e[3]): e for e in events for z in (e[1], e[2])}
    for i, X, Y, d, a, p, c in events:
        for me, other in ((X, Y), (Y, X)):
            days2 = sorted(dd for (z, dd) in by if z == other and dd != d)
            if not days2:
                continue
            e2 = by[(other, rng.choice(days2))]
            qs.append({"typ": "T5", "q": T["q5"].format(X=me, d=L["days"][d], e=L["days"][e2[3]]), "gold": {"PLACE": e2[5]}, "gi": None,
                       "cls": "含C4" if "C4" in (c, e2[6]) else "C0-C3"})
    return qs


# ---------------------------------------------------------------- VSA 多跳
def places_of(m, z, TM=None):
    """两次解绑：探针 AGENT=z、WITH=z 各取点积 ≥ D/2 的痕迹；ACTION 非存疑（=事件）且 PLACE 非存疑 ⇒ 收集地点。"""
    TM = TM if TM is not None else np.stack([m.trace(i) for i in range(len(m))]).astype(np.float64)
    out = set()
    for role in ("AGENT", "WITH"):
        dots = TM @ m.probe({role: z}).astype(np.float64) / m.space.dim
        for i in np.nonzero(dots >= 0.5)[0]:
            a, p = m.decode(int(i), "ACTION")[0], m.decode(int(i), "PLACE")[0]
            if a != DOUBT and p != DOUBT:
                out.add(p)
    return out


def combine(a, b):
    return (a & b) if CFG["intersect"] else (a | b)


def vsa_t4(m, X, Y, TM=None):
    return sorted(combine(places_of(m, X, TM), places_of(m, Y, TM)))


def parse_q5(lang, q):
    g = Q5_RE[lang].match(q).groups()
    return (g[0], g[1], g[2]) if lang == "zh" else (g[1], g[2], g[0])       # → (X, d1, d2)


def vsa_t5(m, lang, q, names, tie="nondoubt"):
    L, T = (S1.ZH if lang == "zh" else S1.EN), TPL[lang]
    X, d1, d2 = parse_q5(lang, q)
    a1, _ = S1.answer_vsa(m, L["q1"].format(X=X, d=d1), names, tie=tie)
    Y = a1.get("PERSON")
    if not Y or Y == DOUBT:
        return DOUBT
    a2, _ = S1.answer_vsa(m, T["q5b"].format(Y=Y, e=d2), names, tie=tie)
    return a2.get("PLACE", DOUBT)


# ---------------------------------------------------------------- 符号表（直接查规则抽取结果，无向量）
def rec(m, i):
    d = {}
    for r, f, *_ in m.roles[i]:
        d.setdefault(r, f)
    return d


def sym_places(m, z, idx=None):
    out = set()
    for i in (range(len(m)) if idx is None else idx):
        r = rec(m, i)
        if z in (r.get("AGENT"), r.get("WITH")) and "ACTION" in r and "PLACE" in r:
            out.add(r["PLACE"])
    return out


def sym_t1(m, X, wd):
    for i in range(len(m)):
        r = rec(m, i)
        if r.get("TIME") == wd and X in (r.get("AGENT"), r.get("WITH")) and "ACTION" in r:
            return r, ("WITH" if r.get("AGENT") == X else "AGENT")
    return None, None


def sym_answer(m, lang, q, typ, names):
    L = S1.ZH if lang == "zh" else S1.EN
    days = {x: f"WD:{i + 1}" for i, x in enumerate(L["days"])}
    roles = M.extract_roles(q, persons=names)
    ppl = [f for r, f, *_ in roles if r in ("AGENT", "WITH")]
    tm = next((f for r, f, *_ in roles if r == "TIME"), None)
    if typ in ("T1", "T3"):
        r, other = sym_t1(m, ppl[0], tm)
        if r is None:
            return {}
        return {"PERSON": r.get(other), "PLACE": r.get("PLACE")} if typ == "T1" else {"ACTION": r.get("ACTION")}
    if typ == "T2":
        pl = next((f for r, f, *_ in roles if r == "PLACE"), None)
        for i in range(len(m)):
            r = rec(m, i)
            if ppl[0] in (r.get("AGENT"), r.get("WITH")) and r.get("PLACE") == pl and "ACTION" in r:
                return {"TIME": r.get("TIME")}
        return {}
    if typ == "T4":
        return {"PLACES": sorted(sym_places(m, ppl[0]) & sym_places(m, ppl[1]))}
    X, d1, d2 = parse_q5(lang, q)
    r, other = sym_t1(m, X, days[d1])
    Y = r.get(other) if r else None
    r2, _ = sym_t1(m, Y, days[d2]) if Y else (None, None)
    return {"PLACE": r2.get("PLACE") if r2 else None}


# ---------------------------------------------------------------- BM25 对照
def bm25_answer(m, bm, lang, qd, names):
    q, typ = qd["q"], qd["typ"]
    if typ in ("T1", "T2", "T3"):
        return B.order(bm.scores(q))[0] == qd["gi"]
    if typ == "T4":
        X, Y = qd["_xy"]
        top = B.order(bm.scores(q))[:10]
        return sorted(sym_places(m, X, top) & sym_places(m, Y, top)) == qd["gold"]["PLACES"]
    L, T = (S1.ZH if lang == "zh" else S1.EN), TPL[lang]
    X, d1, d2 = parse_q5(lang, q)
    r = rec(m, B.order(bm.scores(L["q1"].format(X=X, d=d1)))[0])
    Y = next((p for p in (r.get("AGENT"), r.get("WITH")) if p and p != X), None)
    if not Y:
        return False
    r2 = rec(m, B.order(bm.scores(T["q5b"].format(Y=Y, e=d2)))[0])
    return r2.get("PLACE") == qd["gold"]["PLACE"]


def vsa_answer(m, lang, qd, names, tie, TM):
    typ, q = qd["typ"], qd["q"]
    if typ in ("T1", "T2", "T3"):
        ans, _ = S1.answer_vsa(m, q, names, tie=tie)
        return all(ans.get(r) == v for r, v in qd["gold"].items())
    if typ == "T4":
        return vsa_t4(m, *qd["_xy"], TM=TM) == qd["gold"]["PLACES"]
    return vsa_t5(m, lang, q, names) == qd["gold"]["PLACE"]


def sign_p(w, l):
    """精确双侧符号检验（= 配对精确 McNemar，只看不一致对）。"""
    n, k = w + l, min(w, l)
    import fractions, math
    w, l = int(w), int(l)                       # numpy 整数下 2**n 会溢出成 0
    n, k = w + l, min(w, l)
    return 1.0 if n == 0 else min(1.0, float(fractions.Fraction(2 * sum(math.comb(n, i) for i in range(k + 1)), 2 ** n)))   # 大 n 时整数比再转浮点，免溢出


def mcn(a, b):
    w = int(sum(bool(x) and not bool(y) for x, y in zip(a, b))); l = int(sum(bool(y) and not bool(x) for x, y in zip(a, b)))
    return w, l, sign_p(w, l)


def run(n_streams=N_STREAMS):
    t0 = time.time()
    rows = collections.defaultdict(lambda: collections.defaultdict(list))
    for k in range(n_streams):
        lang, sents, events, names, rng = gen_stream(k)
        qs = questions(lang, events, names, rng)
        m = write_stream(sents, names, coref=True)
        m0 = write_stream(sents, names, coref=False)
        TM = np.stack([m.trace(i) for i in range(len(m))]).astype(np.float64)
        TM0 = np.stack([m0.trace(i) for i in range(len(m0))]).astype(np.float64)
        bm = B.BM25(sents)
        for qd in qs:
            key = (lang, qd["typ"], qd["cls"])
            sym = sym_answer(m, lang, qd["q"], qd["typ"], names)
            r = rows[key]
            r["vsa"].append(vsa_answer(m, lang, qd, names, "prereg" if qd["typ"] != "T5" else "nondoubt", TM))
            r["vsa_v1b"].append(vsa_answer(m, lang, qd, names, "nondoubt", TM))
            r["vsa_nocoref"].append(vsa_answer(m0, lang, qd, names, "prereg" if qd["typ"] != "T5" else "nondoubt", TM0))
            r["bm25"].append(bm25_answer(m, bm, lang, qd, names))
            r["sym"].append(all(sym.get(x) == v for x, v in qd["gold"].items()))
        print(f"stream {k} {lang} sents={len(sents)} q={len(qs)} {time.time() - t0:.0f}s", flush=True)
    return rows, time.time() - t0


def report(rows, secs):
    def agg(sel):
        c = collections.defaultdict(list)
        for key, r in rows.items():
            if sel(key):
                for a, v in r.items():
                    c[a] += v
        return c
    groups = [("全部", lambda k: True)]
    for typ in ("T1", "T2", "T3"):
        for cl in CLASSES:
            groups.append((f"{typ}/{cl}", (lambda t, c: lambda k: k[1] == t and k[2] == c)(typ, cl)))
    for typ in ("T4", "T5"):
        for cl in ("C0-C3", "含C4"):
            groups.append((f"{typ}/{cl}", (lambda t, c: lambda k: k[1] == t and k[2] == c)(typ, cl)))
    for lang in ("zh", "en"):
        for typ in ("T1", "T2", "T3", "T4", "T5"):
            groups.append((f"{lang}/{typ}", (lambda l, t: lambda k: k[0] == l and k[1] == t)(lang, typ)))
    out = {}
    md = ["# 合成基准 v2（PREREG_v2 §C）：抽取噪声 + 多跳", "",
          "| 子集 | 题数 | **VSA** | BM25 | VSA vs BM25 胜/负 p | 符号表 | VSA v1b 并列规则 | VSA 关 coref（消融） |", "|---|---:|---:|---:|---|---:|---:|---:|"]
    for name, sel in groups:
        c = agg(sel)
        n = len(c["vsa"])
        if not n:
            continue
        w, l, p = mcn(c["vsa"], c["bm25"])
        o = {"n": n, **{a: sum(v) / n for a, v in c.items()}, "vsa_vs_bm25": {"win": w, "loss": l, "p": p}}
        out[name] = o
        md.append(f"| {name} | {n} | **{o['vsa']:.3f}** | {o['bm25']:.3f} | {w}/{l} p={p:.2g} | {o['sym']:.3f} | {o['vsa_v1b']:.3f} | {o['vsa_nocoref']:.3f} |")
    md += ["", "C0 干净（v1 模板）；C1 代词；C2 省略主语；C3 规则内改写；C4 规则外改写（陪/joined，刻意不加规则）。T4 两次解绑求交；T5 链式两跳。",
           "T1–T3：VSA 主报用 v1 预注册并列规则（同 v1）；T5 两跳用 v1b 并列规则（PREREG_v2 §C）。BM25：T1–T3 判 top1=金标句（对 BM25 有利）；T4 top10 句+同一抽取求交；T5 两跳 top1。",
           "符号表：直接在规则抽取结果上做同一查询（无向量），检验 VSA 代数相对精确符号查找的损失。",
           f"耗时 {secs:.0f}s。复跑：`python -X utf8 TanPowasd/vsa/synth_v2.py`"]
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "synth_v2.json").write_text(json.dumps({"prereg": "PREREG_v2.md §C", "seed": SEED, "streams": N_STREAMS, "rows": out,
                                                                "secs": round(secs, 1)}, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "results" / "synth_v2.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    tmp = pathlib.Path(os.environ.get("VSA_OUT") or (HERE / "data")) / "synth_v2_rows.json"     # 逐子集判对向量（缓存，不入库）
    if "--report" in sys.argv:                  # 只从缓存重出报表（不重跑）
        d = json.loads(tmp.read_text(encoding="utf-8"))
        report({tuple(k.split("|")): v for k, v in d["rows"].items()}, d["secs"])
        sys.exit(0)
    rows, secs = run()
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps({"secs": secs, "rows": {"|".join(k): {a: [bool(x) for x in v] for a, v in r.items()} for k, r in rows.items()}}), encoding="utf-8")
    report(rows, secs)
