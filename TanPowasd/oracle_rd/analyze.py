# -*- coding: utf-8 -*-
"""R/D oracle 阶段 1 · 零 key 分析：准确率/拒答/三差值/簇自助法区间/四形态。
跑法：python -X utf8 analyze.py   （读 results.json、sample.json，写 readings.json）
缺失处理（读数后补记，非预注册）：主口径 = 三臂均判分成功的完整题（配对）；
敏感性 = 缺失记错（下界）与缺失记对（上界）两种 100 题全集口径。
"""
import json, os, random
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
B, SEED, NOISE = 10000, 20261014, 3.0
rows = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))["rows"]
sample = {q["qid"]: q for q in json.load(open(os.path.join(HERE, "sample.json"), encoding="utf-8"))["sample"]}
V = defaultdict(dict)
for r in rows:
    V[r["qid"]][r["arm"]] = r.get("verdict")
qids = sorted(sample, key=lambda q: (sample[q]["conv"], int(q.split("_q_")[1])))


def score(qid, arm, miss):
    v = V[qid].get(arm)
    return (1.0 if v == "correct" else 0.0) if v else miss


def boot(diff_by_q, qs):
    conv = defaultdict(list)
    for q in qs:
        conv[sample[q]["conv"]].append(q)
    cl = sorted(conv)
    rng = random.Random(SEED)
    pt = 100 * sum(diff_by_q[q] for q in qs) / len(qs)
    bs = []
    for _ in range(B):
        pick = [c for _ in cl for c in [rng.choice(cl)]]
        xs = [diff_by_q[q] for c in pick for q in conv[c]]
        bs.append(100 * sum(xs) / len(xs))
    bs.sort()
    return round(pt, 1), round(bs[int(0.025 * B)], 1), round(bs[int(0.975 * B) - 1], 1)


def tier(pt, lo, hi):
    if pt >= NOISE and lo > 0:
        return "高"
    if lo <= 0 <= hi or abs(pt) < NOISE:
        return "≈0"
    return "低"


def block(qs, miss=None):
    out = {"n": len(qs), "arms": {}}
    for a in ("C", "S", "R"):
        vs = [V[q].get(a) for q in qs]
        out["arms"][a] = {"correct": sum(v == "correct" for v in vs), "refused": sum(v == "refused" for v in vs),
                          "incorrect": sum(v == "incorrect" for v in vs), "missing": sum(v is None for v in vs)}
        out["arms"][a]["acc_pct"] = round(100 * sum(score(q, a, miss or 0.0) for q in qs) / len(qs), 1)
    d = {}
    for name, (x, y) in {"Δ_sys=Δ_doc (S−C)": ("S", "C"), "Δ_R (R−C)": ("R", "C"), "R−S (检索净损失)": ("R", "S")}.items():
        diff = {q: score(q, x, miss or 0.0) - score(q, y, miss or 0.0) for q in qs}
        pt, lo, hi = boot(diff, qs)
        d[name] = {"pp": pt, "ci95": [lo, hi], "档": tier(pt, lo, hi)}
    out["deltas"] = d
    return out


complete = [q for q in qids if all(V[q].get(a) for a in ("C", "S", "R"))]
res = {"primary_complete": block(complete),
       "sens_missing_as_wrong": block(qids, 0.0),
       "sens_missing_as_right": block(qids, 1.0)}
# 四形态
p = res["primary_complete"]["deltas"]
ts, tr = p["Δ_sys=Δ_doc (S−C)"]["档"], p["Δ_R (R−C)"]["档"]
up = lambda t: t == "高"
if not up(ts) and not up(tr) and ts == "≈0" and tr == "≈0":
    form = "一（写入/表示）"
elif not up(ts) and up(tr):
    form = "三（检索层 R）；D 维 doc≡sys 记不适用"
elif up(ts) and up(tr):
    form = "sys 与 R 均高：系统交付已有净增益、R 仍有余量（表外形态；doc≡sys 故非二/四）"
else:
    form = f"表外（sys={ts}, R={tr}）"
res["form"] = form
# 能红条件
res["red"] = {"1 Δ_doc−Δ_sys≤3pp": "构造性成立（doc≡sys，差恒 0）",
              "2 Δ_R>0 且 Δ_doc≈0": (p["Δ_R (R−C)"]["pp"] > 0 and p["Δ_sys=Δ_doc (S−C)"]["档"] == "≈0"),
              "3 准确率与拒答同步上升": {a: (res["primary_complete"]["arms"][a]["acc_pct"] > res["primary_complete"]["arms"]["C"]["acc_pct"]
                                     and res["primary_complete"]["arms"][a]["refused"] > res["primary_complete"]["arms"]["C"]["refused"]) for a in ("S", "R")}}
# 辅助：S 按 hit@10 拆、按 cat 拆
aux = {}
for h in (True, False):
    qs = [q for q in complete if sample[q]["hit10"] == h]
    aux[f"hit10={h}"] = {a: f"{sum(V[q][a]=='correct' for q in qs)}/{len(qs)}" for a in ("C", "S", "R")}
for c in (1, 2, 3, 4):
    qs = [q for q in complete if sample[q]["cat"] == c]
    aux[f"cat{c}"] = {a: f"{sum(V[q][a]=='correct' for q in qs)}/{len(qs)}" for a in ("C", "S", "R")}
# 配对转移：S→R
tr_ = Counter((V[q]["S"], V[q]["R"]) for q in complete)
aux["S→R 配对转移"] = {f"{k[0]}→{k[1]}": v for k, v in sorted(tr_.items())}
res["aux"] = aux
res["missing_rows"] = sorted([f"{q}:{a}" for q in qids for a in ("C", "S", "R") if not V[q].get(a)])
json.dump(res, open(os.path.join(HERE, "readings.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
