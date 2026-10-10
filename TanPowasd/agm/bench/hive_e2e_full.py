"""e2e 流式全臂对比（16 份真实对话，零 LLM）：现有臂 + 后缀自动机 / AC / 二分阈值 / RRF / ACT-R 使用增量。

口径沿用 hive_e2e_stream / hive_e2e_v2（评分在先、学习在后，每份对话从空记忆开始），读数加两种：
  覆盖     真实下一条 AI 回复的显著二元组被上下文覆盖的比例（显著按全文件 df，沿用旧口径，含未来信息）
  窗口外   只算「整份预算的最近窗口没覆盖、本臂覆盖了」的那部分——记忆系统真正多给的东西
  在线覆盖 显著按「截至此刻的历史」df 判，不看未来
统计单位是文件（16 份），配对比较给均值差、胜负、符号检验、bootstrap 95% CI、dz。
参数全部跑前写死：近因比例 r=0.5，RRF k=60 等权，AC 睡眠间隔 50 次查询，ACT-R d=0.5、K=10，SAM 最短匹配 3 字。
用法：python hive_e2e_full.py <bench> [--files …] --json 输出
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import time

import agm_algos as X
from hive_e2e_stream import Agm, Store, bset, chunk_turn, norm, parse, take
from hive_e2e_v2 import Agm2

MIX, SLEEP, MINLEN = 0.5, 50, 3


class AgmX(Agm):
    """静态 AGM，可换种子来源、可二分阈值。"""

    def rank_from(self, sc, budget=None, bisect=False):
        if not sc:
            return []
        top = sorted(sc, key=lambda i: -sc[i])[: self.SEEDS]
        m = sc[top[0]] or 1.0
        x = {i: sc[i] / m for i in top}
        if bisect:
            a = X.bisect_theta(self.out, x, 2, self.DECAY, self.st.len, budget)
        else:
            a = X.spread(self.out, x, 2, self.DECAY, self.THETA, self.KWTA)
        rest = sorted((i for i in sc if i not in a), key=lambda i: -sc[i])
        return sorted(a, key=lambda i: -a[i]) + rest


ARMS = ["最近窗口", "BM25", "AGM-静态", "AGM-学习v1", "AGM-学习v2", "后缀自动机", "AGM-SAM种子", "AGM-AC种子",
        "近因+BM25", "近因+AGM-静态", "近因+AGM-学习v2", "近因+后缀自动机", "近因+AGM-SAM种子", "近因+AGM-AC种子",
        "近因+AGM-二分θ", "近因+AGM+ACT-R", "RRF3(近因,BM25,AGM)", "RRF4(+SAM)", "RRF5(+ACT-R)"]


def run_file(path, cards, budget):
    turns = parse(path)
    st = Store()
    all_chunks = [c for t in turns for c in chunk_turn(t)]
    dfc = collections.Counter(g for _, x in all_chunks for g in bset(x))
    capf = max(2, int(0.02 * len(all_chunks)))
    salient = lambda s: {g for g in bset(s) if dfc.get(g, 0) <= capf}

    static, learn1, learn2, learn2h = AgmX(st, False), Agm(st, True), Agm2(st), Agm2(st)
    graphs = [static, learn1, learn2, learn2h]
    sam = X.SAM()
    ngdf = collections.Counter()
    pats, pending, ac = set(), [], None
    actr_dual, actr_rrf = X.Actr(), X.Actr()
    n_q = 0
    sums = {a: collections.defaultdict(float) for a in ARMS}
    cnt = {a: collections.Counter() for a in ARMS}

    def cap():
        return max(5, int(0.05 * st.N))

    def chans(qset, qtext, t_idx):
        """一次查询的各通道排序（共享，不学习的部分只算一次）。"""
        sc = st.bm25(qset)
        o_bm = sorted(sc, key=lambda i: -sc[i])
        o_agm = static.rank_from(sc)
        s_sam = X.phrase_scores(sam.maximal_matches(qtext, MINLEN), st.text, st.inv, cap(), st.N)
        o_sam = sorted(s_sam, key=lambda i: -s_sam[i])
        s_ac = X.phrase_scores(ac.longest_matches(qtext), st.text, st.inv, cap(), st.N) if ac else {}
        o_rec = list(range(st.N - 1, -1, -1))
        return {"sc": sc, "bm": o_bm, "agm": o_agm, "s_sam": s_sam, "sam": o_sam, "s_ac": s_ac, "rec": o_rec}

    def fill(recent, order, B):
        R = set(recent)
        left = B - sum(st.len[i] for i in recent)
        return take([i for i in order if i not in R], st, left) if left > 0 else []

    def retrieve(arm, C, q, t_idx):
        """返回 (近因块, 联想块, 学习器)。"""
        rec_half = take(C["rec"], st, int(budget * MIX))
        if arm == "最近窗口":
            return take(C["rec"], st, budget), [], None
        if arm == "BM25":
            return [], take(C["bm"], st, budget), None
        if arm == "AGM-静态":
            return [], take(C["agm"], st, budget), None
        if arm == "AGM-学习v1":
            return [], take(learn1.rank(q, t_idx), st, budget), learn1
        if arm == "AGM-学习v2":
            return [], take(learn2.rank(q, t_idx), st, budget), learn2
        if arm == "后缀自动机":
            return [], take(C["sam"] + [i for i in C["bm"] if i not in C["s_sam"]], st, budget), None
        if arm == "AGM-SAM种子":
            return [], take(seeded(C["s_sam"], C), st, budget), None
        if arm == "AGM-AC种子":
            return [], take(seeded(C["s_ac"], C), st, budget), None
        if arm == "近因+BM25":
            return rec_half, fill(rec_half, C["bm"], budget), None
        if arm == "近因+AGM-静态":
            return rec_half, fill(rec_half, C["agm"], budget), None
        if arm == "近因+AGM-学习v2":
            return rec_half, fill(rec_half, learn2h.rank(q, t_idx), budget), learn2h
        if arm == "近因+后缀自动机":
            return rec_half, fill(rec_half, C["sam"] + [i for i in C["bm"] if i not in C["s_sam"]], budget), None
        if arm == "近因+AGM-SAM种子":
            return rec_half, fill(rec_half, seeded(C["s_sam"], C), budget), None
        if arm == "近因+AGM-AC种子":
            return rec_half, fill(rec_half, seeded(C["s_ac"], C), budget), None
        if arm == "近因+AGM-二分θ":
            left = budget - sum(st.len[i] for i in rec_half)
            R = set(rec_half)
            sc = {i: v for i, v in C["sc"].items() if i not in R}
            return rec_half, fill(rec_half, static.rank_from(sc, budget=left, bisect=True), budget), None
        if arm == "近因+AGM+ACT-R":
            head = C["agm"][: static.KWTA]
            sc = {}
            for r, i in enumerate(head):
                B = actr_dual.B(i, t_idx)
                sc[i] = (1 / (1 + r)) * (1 + 0.3 * min(3.0, 2.718281828 ** B) if B is not None else 1.0)
            order = sorted(sc, key=lambda i: -sc[i]) + C["agm"][static.KWTA:]
            return rec_half, fill(rec_half, order, budget), actr_dual
        if arm == "RRF3(近因,BM25,AGM)":
            return [], take(X.rrf([C["rec"], C["bm"], C["agm"]]), st, budget), None
        if arm == "RRF4(+SAM)":
            return [], take(X.rrf([C["rec"], C["bm"], C["agm"], C["sam"]]), st, budget), None
        if arm == "RRF5(+ACT-R)":
            return [], take(X.rrf([C["rec"], C["bm"], C["agm"], C["sam"], actr_rrf.ranking(t_idx)]), st, budget), actr_rrf
        raise KeyError(arm)

    def seeded(sdict, C):
        """换种子的 AGM：放电集合之后用 BM25 顺序补满（首跑漏了这一步，种子稀疏时预算填不满，已披露后修正）。"""
        o = static.rank_from(sdict) if sdict else []
        seen = set(o)
        return (o + [i for i in C["bm"] if i not in seen]) or C["agm"]

    def ctx_of(got):
        return set().union(*(st.bs[i] for i in got)) if got else set()

    card_at = collections.defaultdict(list)
    for c in cards:
        card_at[c["answer"]["human"]["line"]].append(c)
    last_chunk = None
    for t_idx, t in enumerate(turns):
        lo, hi = t["line"], (t["lines"][-1][0] if t["lines"] else t["line"])
        if t["who"] == "human" and st.N:
            for c in [c for L, cs_ in card_at.items() if lo <= L <= hi for c in cs_]:
                qtext = norm("".join(p["text"] for p in c["pre"]))
                q = set().union(*(bset(p["text"]) for p in c["pre"]))
                target = c["answer"]["human"]["text"] + ((c["answer"].get("ai_opening") or {}).get("text") or "")
                tgt = salient(target) - q
                if not tgt:
                    continue
                C = chans(q, qtext, t_idx)
                for arm in ARMS:
                    r, a, _ = retrieve(arm, C, q, t_idx)
                    sums[arm]["题卡覆盖"] += len(tgt & ctx_of(r + a)) / len(tgt); cnt[arm]["题卡覆盖"] += 1
        if t["who"] == "human" and t_idx + 1 < len(turns) and turns[t_idx + 1]["who"] == "ai" and st.N:
            q, qtext = bset(t["text"]), norm(t["text"])
            reply = turns[t_idx + 1]["text"]
            tgt = salient(reply) - q
            capo = max(2, int(0.02 * st.N))
            tgt_on = {g for g in bset(reply) - q if len(st.inv.get(g, ())) <= capo}
            if tgt:
                n_q += 1
                C = chans(q, qtext, t_idx)
                Rctx = ctx_of(take(C["rec"], st, budget))
                for arm in ARMS:
                    r, a, learner = retrieve(arm, C, q, t_idx)
                    got = r + a
                    cx = ctx_of(got)
                    sums[arm]["覆盖"] += len(tgt & cx) / len(tgt)
                    sums[arm]["窗口外"] += len((tgt & cx) - Rctx) / len(tgt)
                    if tgt_on:
                        sums[arm]["在线覆盖"] += len(tgt_on & cx) / len(tgt_on); cnt[arm]["在线覆盖"] += 1
                    cnt[arm]["覆盖"] += 1; cnt[arm]["窗口外"] += 1
                    if learner is learn1:
                        rs = salient(reply)
                        used = sorted((i for i in got if len(st.bs[i] & rs) >= 3), key=lambda i: -len(st.bs[i] & rs))
                        learn1.feedback(q, got, used, t_idx)
                    elif isinstance(learner, Agm2):
                        learner.feedback2(q, a, got, tgt, t_idx)
                    elif isinstance(learner, X.Actr):
                        pool = a if a else got
                        cc = collections.Counter(g for i in got for g in (st.bs[i] & tgt))
                        for i in pool:
                            if sum(1 for g in st.bs[i] & tgt if cc[g] == 1) >= 2:
                                learner.use(i, t_idx)
                if n_q % SLEEP == 0:          # 睡眠：把新块的显著短语收进 AC，重建
                    for i in pending:
                        pats.update(X.phrases_of(st.text[i], ngdf, st.N, cap()))
                    pending.clear()
                    if pats:
                        ac = X.AC(pats)
        prev = None
        for ln, x in chunk_turn(t):
            i = st.add(t_idx, ln, x)
            s = st.text[i]
            sam.add(s)
            ngdf.update({s[k:k + n] for n in (2, 3, 4) for k in range(len(s) - n + 1)})
            pending.append(i)
            for g in graphs:
                g.link_new(i, prev, last_chunk if prev is None else None)
            prev = i
        if prev is not None:
            last_chunk = prev
    return {a: {m: {"均值": sums[a][m] / cnt[a][m], "n": cnt[a][m]} for m in cnt[a] if cnt[a][m]} for a in ARMS}, \
        {"轮": len(turns), "块": st.N, "查询": n_q, "SAM状态": len(sam.ln), "AC模式": len(pats)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--budget", type=int, default=4000)
    ap.add_argument("--json", required=True)
    A = ap.parse_args()
    root = pathlib.Path(A.root) / "e2e"
    cards = json.loads((root / "questions" / "题卡_C型_续接预测_v0.1.json").read_text(encoding="utf-8"))
    files = A.files or sorted(p.name for p in (root / "corpus").glob("*.md"))
    out = {}
    outp = pathlib.Path(A.json)
    if outp.exists():
        out = json.loads(outp.read_text(encoding="utf-8"))
    t0 = time.time()
    for f in files:
        if f in out:
            continue
        r, meta = run_file(root / "corpus" / f, [c for c in cards if c["file"] == f], A.budget)
        out[f] = {"meta": meta, "arms": r}
        outp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f, meta, round(r["近因+AGM-静态"]["覆盖"]["均值"], 4), f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
