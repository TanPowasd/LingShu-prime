# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""合成组合查询基准（PREREG_v1 §a）。确定性生成多人多天事件流，问「X 周三和谁去了哪」类问题：VSA 解绑精确作答 vs BM25 top1 句子。
  python -X utf8 synth.py              # 基准 → results/synth_v1.json/.md
  python -X utf8 synth.py --capacity   # 容量曲线（描述性）→ results/capacity_v1.json/.md
数据只在内存里生成，不落盘、不入库。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import collections, json, math, pathlib, random, re, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import bm25 as B  # noqa: E402
from cleanup import Cleanup, DOUBT  # noqa: E402

SEED = "vsa-synth-v1"
N_STREAMS, N_PEOPLE, N_PAIRS, N_CHAT = 60, 10, 3, 14
ZH = {"names": ["小王", "李娜", "张伟", "陈静", "刘洋", "王芳", "赵磊", "孙丽", "周杰", "吴敏"],
      "places": ["图书馆", "咖啡馆", "公园", "体育馆", "博物馆", "电影院", "西湖", "商场", "海边", "动物园", "面包店", "美术馆"],
      "acts": ["爬山", "看电影", "打篮球", "吃火锅", "买书", "跑步", "游泳", "散步", "下棋", "唱歌", "画画", "钓鱼"],
      "days": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
      "ev": ["{d}，{X}和{Y}去{p}{a}了。", "{X}{d}跟{Y}在{p}{a}。", "{d}{X}约了{Y}，一起到{p}{a}。", "{X}和{Y}{d}去了{p}，{a}。"],
      "chat": ["{X}说{d}的{p}人很多。", "{X}觉得{p}不错。", "{X}提到{Y}最近很忙。", "{X}说{d}想休息。"],
      "q1": "{X}{d}和谁去了哪？", "q2": "{X}哪天去了{p}？", "q3": "{X}{d}做了什么？"}
EN = {"names": ["Alice", "Bob", "Carol", "Dave", "Erin", "Frank", "Grace", "Heidi", "Ivan", "Judy"],
      "places": ["library", "museum", "park", "cafe", "stadium", "cinema", "lake", "mall", "beach", "gym", "zoo", "bakery"],
      "acts": ["hiking", "shopping", "bowling", "swimming", "sketching", "fishing", "dancing", "jogging", "chess", "karaoke", "picnic", "camping"],
      "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
      "ev": ["On {d}, {X} went to the {p} with {Y} for {a}.", "{X} and {Y} went {a} near the {p} on {d}.",
             "{X} met {Y} at the {p} on {d} to do some {a}."],
      "chat": ["{X} said the {p} was crowded on {d}.", "{X} thinks the {p} is nice.", "{X} mentioned that {Y} is busy.",
               "{X} wants to rest on {d}."],
      "q1": "Who did {X} go with on {d}, and where?", "q2": "When did {X} go to the {p}?", "q3": "What did {X} do on {d}?"}


def gen_stream(k):
    """→ (lang, sentences, events[(句号, X, Y, 天号, 动作, 地点)], questions[(类型, 问句, 金标dict, 金标句号)])。"""
    rng = random.Random(f"{SEED}|{k}")
    L = ZH if k % 2 == 0 else EN
    lang = "zh" if k % 2 == 0 else "en"
    sents, events = [], []
    chats = collections.defaultdict(list)
    for _ in range(N_CHAT):
        X, Y = rng.sample(L["names"], 2)
        chats[rng.randrange(7)].append(rng.choice(L["chat"]).format(X=X, Y=Y, d=L["days"][rng.randrange(7)], p=rng.choice(L["places"])))
    for d in range(7):
        ppl = rng.sample(L["names"], 2 * N_PAIRS)
        day = []
        for j in range(N_PAIRS):
            X, Y = ppl[2 * j], ppl[2 * j + 1]
            a, p = rng.choice(L["acts"]), rng.choice(L["places"])
            day.append(("E", rng.choice(L["ev"]).format(X=X, Y=Y, d=L["days"][d], p=p, a=a), (X, Y, d, a, p)))
        day += [("C", c, None) for c in chats[d]]
        rng.shuffle(day)
        for kind, s, ev in day:
            if kind == "E":
                events.append((len(sents),) + ev)
            sents.append(s)
    canon = (lambda a: a) if lang == "zh" else (lambda a: M.ACTIONS_EN[a])
    qs = []
    for i, X, Y, d, a, p in events:
        for me, other in ((X, Y), (Y, X)):
            qs.append(("T1", L["q1"].format(X=me, d=L["days"][d]), {"PERSON": other, "PLACE": p}, i))
            qs.append(("T3", L["q3"].format(X=me, d=L["days"][d]), {"ACTION": canon(a)}, i))
    cnt = collections.Counter((pp, e[5]) for e in events for pp in (e[1], e[2]))
    for i, X, Y, d, a, p in events:
        for me in (X, Y):
            if cnt[(me, p)] == 1:
                qs.append(("T2", L["q2"].format(X=me, p=p), {"TIME": f"WD:{d + 1}"}, i))
    return lang, sents, events, qs, L["names"]


def targets(q):
    """疑问词规则 → 目标角色（PREREG §a）。"""
    t = []
    if re.search(r"和谁|\bwho\b.*\bwith\b", q, re.I):
        t.append("PERSON")
    if re.search(r"哪(?!天)|\bwhere\b", q, re.I):
        t.append("PLACE")
    if re.search(r"哪天|^\s*when\b", q, re.I):
        t.append("TIME")
    if re.search(r"做了什么|\bwhat did\b.*\bdo\b", q, re.I):
        t.append("ACTION")
    return t


def answer_vsa(m, q, names, tie="prereg"):
    """tie="prereg"：两探针取最高点积更大者，相等取 AGENT（PREREG_v1 原文）。
    tie="nondoubt"（事后修订 v1b，读数后加，描述性）：点积相等时优先取给出非存疑答案的探针——
    原规则在「X 是同伴、且同日有 X 作主语的闲聊句」时，AGENT 探针命中闲聊句（同样 2 项）而先被选中，解绑全存疑。"""
    roles = M.extract_roles(q, persons=names)
    person = next((f for r, f, *_ in roles if r in ("AGENT", "WITH")), None)
    given = {r: f for r, f, *_ in roles if r in ("TIME", "PLACE")}
    tg = targets(q)
    best = None
    for as_role, other in (("AGENT", "WITH"), ("WITH", "AGENT")):
        if person is None and as_role == "WITH":
            break
        g = dict(given, **({as_role: person} if person else {}))
        want = tuple(other if t == "PERSON" else t for t in tg)
        r = m.query(want, g)
        r["_map"] = {other if t == "PERSON" else t: t for t in tg}
        if tie == "prereg":           # 首次运行的实现：原始浮点点积直接比较（「相等」实际几乎不发生，同项数并列由噪声决定）
            if best is None or (r["match"] or 0) > (best["match"] or 0) + 1e-9:
                best = r
        elif best is None or (r["match"] or 0) > (best["match"] or 0) + 0.5:
            best = r
        elif abs((r["match"] or 0) - (best["match"] or 0)) <= 0.5 and best["trace"] is None and r["trace"] is not None:
            best = r                  # v1b：命中项数相同（差 < D/2）时取给出非存疑答案的探针
    ans = {best["_map"][k]: v for k, v in best["answer"].items()}
    return ans, best["trace"]


def run():
    t0 = time.time()
    sp = H.Space("vsa-v1")
    per = collections.defaultdict(lambda: collections.Counter())
    examples = []
    for k in range(N_STREAMS):
        lang, sents, events, qs, names = gen_stream(k)
        m = M.Memory(sp)
        for s in sents:
            m.write(s, persons=names)
        bm = B.BM25(sents)
        for typ, q, gold, gi in qs:
            ans, tr = answer_vsa(m, q, names)
            ok = all(ans.get(r) == v for r, v in gold.items())
            ans_b, _ = answer_vsa(m, q, names, tie="nondoubt")
            top = B.order(bm.scores(q))[0]
            c = per[(lang, typ)]
            c["n"] += 1; c["vsa"] += ok; c["vsa_trace@1"] += tr == gi; c["bm25_top1"] += top == gi
            c["vsa_doubt"] += any(v == DOUBT for v in ans.values())
            c["vsa_v1b"] += all(ans_b.get(r) == v for r, v in gold.items())
            if not ok and len(examples) < 12:
                examples.append({"q": q, "gold": gold, "vsa": ans, "trace": sents[tr] if tr is not None else None, "gold_sent": sents[gi]})
    rows = {}
    for (lang, typ), c in sorted(per.items()):
        rows[f"{lang}/{typ}"] = {"n": c["n"], **{x: c[x] / c["n"] for x in ("vsa", "vsa_trace@1", "bm25_top1", "vsa_doubt", "vsa_v1b")}}
    tot = collections.Counter()
    for c in per.values():
        tot.update(c)
    rows["all"] = {"n": tot["n"], **{x: tot[x] / tot["n"] for x in ("vsa", "vsa_trace@1", "bm25_top1", "vsa_doubt", "vsa_v1b")}}
    out = {"prereg": "PREREG_v1.md §a", "seed": SEED, "space": "vsa-v1", "D": H.D, "streams": N_STREAMS, "rows": rows,
           "fail_examples": examples, "secs": round(time.time() - t0, 1)}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "synth_v1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# 合成组合查询基准 v1（PREREG_v1 §a）", "", "| 子集 | 题数 | VSA 解绑精确率（预注册规则） | VSA 痕迹@1 | BM25 top1=金标句 | VSA 存疑率 | VSA v1b（事后修订并列规则，描述性） |", "|---|---:|---:|---:|---:|---:|---:|"]
    for k, r in rows.items():
        md.append(f"| {k} | {r['n']} | {r['vsa']:.3f} | {r['vsa_trace@1']:.3f} | {r['bm25_top1']:.3f} | {r['vsa_doubt']:.3f} | {r['vsa_v1b']:.3f} |")
    md += ["", "T1=和谁去了哪（人+地点都对才算对）；T2=哪天；T3=做了什么。BM25 判对 := top1 是金标事件句（假设抽答案完美，对 BM25 有利）。",
           "v1b：两探针命中项数相同（点积差 < D/2）时优先取有非存疑答案者（读数后加的修订，非预注册；预注册实现下失败全部是「X 为同伴且同日有 X 作主语的闲聊句」，"
           "两探针都命中 2 项、由噪声决定选哪个）。若把预注册的「相等」按 D/2 并列带严格执行而不加非存疑优先，总精确率为 0.958（同日第二次运行读数）。",
           f"耗时 {out['secs']}s。复跑：`python -X utf8 TanPowasd/vsa/synth.py`"]
    (HERE / "results" / "synth_v1.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    for e in examples[:6]:
        print(e)


def capacity():
    sp = H.Space("vsa-cap", cache_max=2000)
    N, trials = 1000, 200
    names = [f"c{i}" for i in range(N)]
    cb = Cleanup(sp, names)
    rng = random.Random("cap")
    rows = []
    for k in (8, 32, 128, 221, 512, 2048):
        err_i = err_s = 0
        for t in range(trials):
            R = [sp.vec(f"R{k}_{t}_{j}") for j in range(k)]
            F = [rng.randrange(N) for _ in range(k)]
            T = H.bundle(H.bind(r, sp.vec(names[f])) for r, f in zip(R, F))
            j = rng.randrange(k)
            err_i += cb.ranked(H.unbind(T, R[j]), 1)[0][0] != names[F[j]]
            err_s += cb.ranked(H.unbind(sp.sgn(T), R[j]), 1)[0][0] != names[F[j]]
        rows.append({"k": k, "err_int": err_i / trials, "err_sign": err_s / trials, "bound_int": H.err_bound(k, N)})
        print(rows[-1], flush=True)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "capacity_v1.json").write_text(json.dumps({"N": N, "trials": trials, "D": H.D, "rows": rows}, indent=1), encoding="utf-8")
    md = ["# 容量曲线 v1（描述性，PREREG_v1 §a）", "", f"码本 N={N}，每 k {trials} 次，D={H.D}，K_MAX={H.K_MAX}", "",
          "| k | 整数叠加 argmax 错误率 | 理论上界 (N−1)Q(√(D/(2k−1))) | sign 叠加错误率 |", "|---:|---:|---:|---:|"]
    md += [f"| {r['k']} | {r['err_int']:.3f} | {min(1, r['bound_int']):.2e} | {r['err_sign']:.3f} |" for r in rows]
    (HERE / "results" / "capacity_v1.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    capacity() if "--capacity" in sys.argv else run()
