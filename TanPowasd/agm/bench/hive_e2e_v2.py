"""AGM e2e 改进版（v0.7 候选）：在 hive_e2e_stream.py 的同一测法上加三项改进。

1 双通道预算：近因通道固定拿最近 r×预算 字，联想通道（BM25 / AGM）在剩余预算里取，排除已在窗口里的块；
2 学习信号改为边际贡献 + 预测误差：
    一块的功劳＝回复里只有它提供的显著二元组（留一法：拿掉它就没了），独占 ≥2 个记为「有用」o=1；
    每块维护「预期有用率」p，三因子调制 M = o − p（多巴胺式），固化 s += M（夹在 0..5），p 向 o 滑动；
    → 一直被用上的老块 M≈0，不再越用越热；
3 条件反射降级为带时间衰减的重排：键为（关键词, 块），V 按 Rescorla–Wagner 向 o 靠拢，
    读出时 V·exp(−Δ轮/τ)·习惯化增益，只在已被激活的候选里乘性加分，不再当种子放电。
评分口径、数据、切块与 hive_e2e_stream.py 完全相同（评分在先、学习在后）。
用法：python hive_e2e_v2.py <hive-memory-bench 路径> [--mix 0.5] [--budget 4000] [--json 输出]
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import statistics
import time

from hive_e2e_stream import Agm, Store, bset, chunk_turn, paired, parse, take


class Agm2(Agm):
    KAPPA, TAU, ALPHA2, ETA_P, MIN_UNIQUE = 0.5, 60.0, 0.3, 0.2, 2

    def __init__(self, st):
        super().__init__(st, True, ())
        self.p = collections.defaultdict(lambda: 0.2)
        self.Vt = collections.defaultdict(dict)

    def rank(self, q, t_now):
        base = super().rank(q, t_now)          # 静态扩散（parts 为空：不加固化/反射）
        if not base:
            return base
        head, rest = base[: self.KWTA], base[self.KWTA:]
        sc = {i: 1.0 / (1 + r) for r, i in enumerate(head)}   # 按名次给基础分，避免量纲问题
        bonus = collections.defaultdict(float)
        for g in self.keywords(q):
            gain = 1 / (1 + math.log1p(self.seen[g]))
            for j, v in self.V.get(g, {}).items():
                if j in sc:
                    bonus[j] = max(bonus[j], v * math.exp(-(t_now - self.Vt[g][j]) / self.TAU) * gain)
        for i in sc:
            sc[i] *= 1 + self.KAPPA * bonus[i]
            if self.s[i]:
                sc[i] *= 1 + self.MU * self.s[i] * (1 + t_now - self.last[i]) ** -self.D_EXP
        return sorted(sc, key=lambda i: -sc[i]) + rest

    def feedback2(self, q, assoc, all_got, tgt, t_now):
        cnt = collections.Counter(g for i in all_got for g in (self.st.bs[i] & tgt))
        uniq = {i: sum(1 for g in self.st.bs[i] & tgt if cnt[g] == 1) for i in assoc}
        kws = self.keywords(q)
        useful = [i for i in assoc if uniq[i] >= self.MIN_UNIQUE]
        if not useful:
            for g in kws:
                self.seen[g] += 1
        for i in assoc:
            o = 1.0 if uniq[i] >= self.MIN_UNIQUE else 0.0
            M = o - self.p[i]
            self.p[i] += self.ETA_P * (o - self.p[i])
            self.s[i] = min(5.0, max(0.0, self.s[i] + M))
            if M > 0:
                self.last[i] = t_now
            for g in kws:
                v = self.V[g].get(i, 0.0)
                if o or v:
                    self.V[g][i] = v + self.ALPHA2 * (o - v); self.Vt[g][i] = t_now
        top = sorted(useful, key=lambda i: -uniq[i])[: self.HEBB_TOP]
        for i in top:
            for j in top:
                if i != j:
                    w = self.out[i].get(j, 0.0)
                    self.out[i][j] = min(self.W_HEBB_MAX, w + self.ETA_H * (1 - w))
            if len(self.out[i]) > self.OUT_BUDGET:
                self.out[i] = dict(sorted(self.out[i].items(), key=lambda kv: -kv[1])[: self.OUT_BUDGET])


def run_file(path, cards, budget, mix):
    turns = parse(path)
    st = Store()
    all_chunks = [c for t in turns for c in chunk_turn(t)]
    dfc = collections.Counter(g for _, x in all_chunks for g in bset(x))
    cap = max(2, int(0.02 * len(all_chunks)))
    salient = lambda s: {g for g in bset(s) if dfc.get(g, 0) <= cap}

    static, learn = Agm(st, False), Agm2(st)
    # 臂：(联想排序器, 近因比例)
    arms = {"最近窗口": ("recent", 1.0), "BM25": ("bm25", 0.0), "AGM-静态": (static, 0.0), "AGM-学习v2": (learn, 0.0),
            "近因+BM25": ("bm25", mix), "近因+AGM-静态": (static, mix), "近因+AGM-学习v2": ("learn_h", mix)}
    learn_h = Agm2(st)
    graphs = [static, learn, learn_h]
    T = {k: [] for k in arms}; C = {k: [] for k in arms}
    card_at = collections.defaultdict(list)
    for c in cards:
        card_at[c["answer"]["human"]["line"]].append(c)

    def retrieve(name, q, t_idx):
        rk, r = arms[name]
        rk = learn_h if rk == "learn_h" else rk
        recent = take(range(st.N - 1, -1, -1), st, int(budget * r)) if r > 0 else []
        if r >= 1.0:
            return recent, []
        if rk == "bm25":
            sc = st.bm25(q); order = sorted(sc, key=lambda i: -sc[i])
        else:
            order = rk.rank(q, t_idx)
        R = set(recent)
        left = budget - sum(st.len[i] for i in recent)
        assoc = take([i for i in order if i not in R], st, left) if left > 0 else []
        return recent, assoc, rk

    def score(got, target, q):
        tgt = salient(target) - q
        if not tgt:
            return None, tgt
        ctx = set().union(*(st.bs[i] for i in got)) if got else set()
        return len(tgt & ctx) / len(tgt), tgt

    last_chunk = None
    for t_idx, t in enumerate(turns):
        lo, hi = t["line"], (t["lines"][-1][0] if t["lines"] else t["line"])
        if t["who"] == "human" and st.N:
            for c in [c for L, cs_ in card_at.items() if lo <= L <= hi for c in cs_]:
                q = set().union(*(bset(p["text"]) for p in c["pre"]))
                target = c["answer"]["human"]["text"] + ((c["answer"].get("ai_opening") or {}).get("text") or "")
                for name in arms:
                    res = retrieve(name, q, t_idx)
                    v, _ = score(res[0] + res[1], target, q)
                    if v is not None:
                        C[name].append(v)
        if t["who"] == "human" and t_idx + 1 < len(turns) and turns[t_idx + 1]["who"] == "ai" and st.N:
            q = bset(t["text"]); reply = turns[t_idx + 1]["text"]
            for name in arms:
                res = retrieve(name, q, t_idx)
                got = res[0] + res[1]
                v, tgt = score(got, reply, q)
                if v is not None:
                    T[name].append(v)
                if len(res) == 3 and isinstance(res[2], Agm2) and tgt:
                    res[2].feedback2(q, res[1], got, tgt, t_idx)
        prev = None
        for ln, x in chunk_turn(t):
            i = st.add(t_idx, ln, x)
            for g in graphs:
                g.link_new(i, prev, last_chunk if prev is None else None)
            prev = i
        if prev is not None:
            last_chunk = prev
    return T, C, len(turns), st.N


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--budget", type=int, default=4000)
    ap.add_argument("--mix", type=float, default=0.5, help="近因通道占预算比例")
    ap.add_argument("--json")
    A = ap.parse_args()
    root = pathlib.Path(A.root) / "e2e"
    cards = json.loads((root / "questions" / "题卡_C型_续接预测_v0.1.json").read_text(encoding="utf-8"))
    files = A.files or sorted(p.name for p in (root / "corpus").glob("*.md"))
    T = collections.defaultdict(list); C = collections.defaultdict(list); per = {}
    t0 = time.time()
    for f in files:
        ts, cs, nt, nc = run_file(root / "corpus" / f, [c for c in cards if c["file"] == f], A.budget, A.mix)
        per[f] = {"查询": len(ts["BM25"]), "题卡": len(cs["BM25"]), **{k: round(statistics.mean(v), 4) for k, v in ts.items() if v}}
        for k in ts:
            T[k] += ts[k]; C[k] += cs[k]
        print(f, per[f], f"{time.time() - t0:.0f}s", flush=True)
    pairs = (("AGM-学习v2", "AGM-静态"), ("AGM-静态", "BM25"), ("近因+AGM-静态", "最近窗口"), ("近因+AGM-静态", "近因+BM25"),
             ("近因+AGM-学习v2", "近因+AGM-静态"), ("近因+AGM-学习v2", "最近窗口"), ("近因+BM25", "最近窗口"))
    out = {"预算字数": A.budget, "近因比例": A.mix, "文件": per,
           "逐轮续接支撑(均值)": {k: round(statistics.mean(v), 4) for k, v in T.items()},
           "题卡断点支撑(均值)": {k: round(statistics.mean(v), 4) for k, v in C.items() if v},
           "_n": {"逐轮": len(T["BM25"]), "题卡": len(C["BM25"])},
           "配对_逐轮": {f"{a}对{b}": paired(T[a], T[b]) for a, b in pairs},
           "配对_题卡": {f"{a}对{b}": paired(C[a], C[b]) for a, b in pairs}}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    print(txt)
    if A.json:
        pathlib.Path(A.json).write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
