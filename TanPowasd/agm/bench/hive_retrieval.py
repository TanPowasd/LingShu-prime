"""AGM × hive-memory-bench · 检索面基准（零 LLM、零网络，可复跑）。

hive-memory-bench（FuRongJun-1999/hive-memory-bench）的完整评测需要外部生成器与 LLM 判官；
本脚本只测其中**不依赖 LLM 的检索面**：用主轮 92 题公开答案键（cards/*.yaml）里的
supporting_evidence（证据句，带 primary/corroborating 权重）与 must_exclude（误用片段），
在同一字符预算下比较各检索器交出的上下文里「证据句保住了几句」。

被测臂（同一切块、同一预算、同一归一化）：
  BM25      字二元组 BM25（基准里「朴素 BM25」的同类基线，非其原实现）
  AGM       AGM v0.5 联想图：BM25 种子 → 有向边（时序前强后弱 + 术语联想，非对称）上扩散激活，
            放电阈值 + k-WTA，跨章复现的术语给边加固化权重
  AGM+反射  AGM 加非条件关键词反射：题面显著关键词直接点亮含它的块作为额外种子（v0.6 §4D）
  AGM-退火  同上，扩散时按温度对弱边做 Boltzmann 抽样（v0.5 §4C；固定种子，取 5 次平均）
  随机      随机取块（下限）
读数：
  证据召回    证据句（归一化后）完整落在上下文里的比例；分 primary / 全部
  全证据题    一题的全部 primary 证据都在 → 该题记 1
  跨章题      primary 证据横跨 ≥2 章的题（「对面那一块」的代理）上的全证据率
  误用片段    must_exclude 片段被带进上下文的比例（仅记录：带进来不等于用错）
  逐字率      交出的块是否逐字取自原文——四臂都是原文切块，恒为 100%，不单列
用法：python hive_retrieval.py <hive-memory-bench 路径> [--json 输出.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import random
import re
import statistics

import yaml  # hive-memory-bench 的答案键是 YAML

CHUNK = 160          # 切块目标字数
BUDGETS = (2000, 4000, 8000)


def norm(s):
    return re.sub(r"[^\w]", "", str(s or ""), flags=re.UNICODE)


def bigrams(s):
    s = norm(s)
    return [s[i:i + 2] for i in range(len(s) - 1)]


# ---------- 语料与切块 ----------
def load_chunks(root):
    chunks = []
    for f in sorted((root / "corpus").glob("u*.json")):
        for ch in json.loads(f.read_text(encoding="utf-8"))["chapters"]:
            sents = re.split(r"(?<=[。！？!?…\n])", ch["text"])
            buf = ""
            for s in sents:
                buf += s
                if len(norm(buf)) >= CHUNK:
                    chunks.append({"cid": ch["cid"], "text": buf})
                    buf = ""
            if norm(buf):
                chunks.append({"cid": ch["cid"], "text": buf})
    for i, c in enumerate(chunks):
        c["i"], c["n"] = i, norm(c["text"])
    return chunks


def load_cards(root):
    cards = []
    for f in sorted((root / "cards").glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        cards.append(d)
    return cards


# ---------- BM25 ----------
class BM25:
    def __init__(self, chunks, k1=1.5, b=0.75):
        self.tf = [collections.Counter(bigrams(c["text"])) for c in chunks]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / len(self.len)
        df = collections.Counter(t for tf in self.tf for t in tf)
        N = len(chunks)
        self.idf = {t: math.log(1 + (N - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self.k1, self.b = k1, b

    def scores(self, q):
        qt = set(bigrams(q))
        out = []
        for tf, L in zip(self.tf, self.len):
            s = 0.0
            for t in qt:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * L / self.avg))
            out.append(s)
        return out


# ---------- AGM 联想图 ----------
class AGM:
    TOP_TERMS, OUT_DEG = 14, 8
    W_FWD, W_BWD = 0.5, 0.25           # 时序边：前向强、后向弱（v0.1 §3.4）
    W_MIN, MU = 0.12, 0.15             # 联想边下限、固化系数
    SEEDS, STEPS, DECAY, THETA, KWTA = 8, 2, 0.35, 0.04, 60

    def __init__(self, chunks, bm25):
        self.bm25, self.N = bm25, len(chunks)
        idf = bm25.idf
        # 每块的显著术语：只取在 2 块以上、但不超过 8% 的块里出现的二元组（只出现一次的连不出边，太常见的是虚词），
        # 再按 tf·idf 取前 TOP_TERMS
        df = collections.Counter(t for tf in bm25.tf for t in tf)
        hi = max(2, int(0.08 * self.N))
        self.df, self.hi = df, hi
        self.T = []
        for tf in bm25.tf:
            ranked = sorted((t for t in tf if 2 <= df[t] <= hi), key=lambda t: -tf[t] * idf[t])
            self.T.append(set(ranked[: self.TOP_TERMS]))
        # 术语跨章复现次数 → 固化权重
        chs = collections.defaultdict(set)
        for c, T in zip(chunks, self.T):
            for t in T:
                chs[t].add(c["cid"])
        inv = collections.defaultdict(list)
        for i, T in enumerate(self.T):
            for t in T:
                inv[t].append(i)
        self.out = [dict() for _ in chunks]
        for i, T in enumerate(self.T):
            mass = sum(idf[t] for t in T) or 1.0
            cand = collections.Counter()
            for t in T:
                for j in inv[t]:
                    if j != i:
                        cand[j] += idf[t]
            edges = []
            for j, shared in cand.items():
                w = shared / mass                                  # 非对称：i 的术语有多少在 j 里
                rec = sum(1 for t in T & self.T[j] if len(chs[t]) >= 3)
                w *= 1 + self.MU * min(rec, 5)                       # 反复出现的线索 → 固化
                if w >= self.W_MIN:
                    edges.append((j, min(w, 1.0)))
            for j, w in sorted(edges, key=lambda e: -e[1])[: self.OUT_DEG]:
                self.out[i][j] = w
        for i in range(self.N - 1):
            if chunks[i]["cid"] == chunks[i + 1]["cid"]:
                self.out[i][i + 1] = max(self.out[i].get(i + 1, 0), self.W_FWD)
                self.out[i + 1][i] = max(self.out[i + 1].get(i, 0), self.W_BWD)
        self.n_edges = sum(len(o) for o in self.out)

    REFLEX_THETA = 0.5

    def reflex(self, q):
        """非条件关键词反射（v0.6 §4D）：题面里的显著关键词直接点亮含它的块，不经 BM25 排名。
        增益按习惯化：关键词出现在越多块里，增益越低 1/(1+ln(1+df))；同一块多个关键词叠加，归一化后 ≥ 阈值才放电。"""
        r = collections.defaultdict(float)
        for t in set(bigrams(q)):
            d = self.df.get(t, 0)
            if 2 <= d <= self.hi:
                g = 1 / (1 + math.log1p(d))
                for j, tf in enumerate(self.bm25.tf):
                    if t in tf:
                        r[j] += g
        if not r:
            return {}
        m = max(r.values())
        return {j: v / m for j, v in r.items() if v / m >= self.REFLEX_THETA}

    def rank(self, q, T=0.0, rng=None, reflex=False):
        s = self.bm25.scores(q)
        top = sorted(range(self.N), key=lambda i: -s[i])[: self.SEEDS]
        m = s[top[0]] or 1.0
        x = {i: s[i] / m for i in top}
        if reflex:
            for j, v in self.reflex(q).items():
                x[j] = max(x.get(j, 0.0), v * 0.9)    # 反射直达，作为额外种子；略低于 BM25 头名
        a = dict(x)
        for _ in range(self.STEPS):
            nxt = collections.defaultdict(float)
            for i, ai in a.items():
                for j, w in self.out[i].items():
                    if T > 0 and rng.random() > 1 - math.exp(-w / T):    # 退火：弱边以概率被跳过
                        continue
                    nxt[j] += ai * w
            for i, v in x.items():
                nxt[i] += v
            nxt = {i: (1 - self.DECAY) * v if i not in x else v for i, v in nxt.items()}
            nxt = {i: v for i, v in nxt.items() if v >= self.THETA}       # 放电阈值
            a = dict(sorted(nxt.items(), key=lambda kv: -kv[1])[: self.KWTA])  # 侧抑制
        rest = sorted((i for i in range(self.N) if i not in a), key=lambda i: -s[i])
        return sorted(a, key=lambda i: -a[i]) + rest


# ---------- 读数 ----------
def take(order, chunks, budget):
    got, used = [], 0
    for i in order:
        L = len(chunks[i]["n"])
        if used + L > budget:
            if used:
                break
        got.append(i)
        used += L
    got.sort()
    return "|".join(chunks[i]["n"] for i in got)


def evaluate(cards, ctx_of):
    prim = allq = ex = 0
    prim_n = all_n = ex_n = 0
    full, cross, cross_n = [], 0, 0
    for c in cards:
        ctx = ctx_of(c)
        ev = c.get("supporting_evidence") or []
        ps = [norm(e["quote"]) for e in ev if e.get("weight") == "primary"]
        hit_p = [q in ctx for q in ps]
        prim += sum(hit_p); prim_n += len(ps)
        for e in ev:
            all_n += 1; allq += norm(e["quote"]) in ctx
        for e in c.get("must_exclude") or []:
            ex_n += 1; ex += norm(e["quote"]) in ctx
        ok = bool(ps) and all(hit_p)
        if ps:
            full.append(ok)
        if len({e["cid"] for e in ev if e.get("weight") == "primary"}) >= 2:
            cross_n += 1; cross += ok
    return {"primary证据召回": round(prim / prim_n, 3), "全部证据召回": round(allq / all_n, 3),
            "全证据题": round(sum(full) / len(full), 3), "跨章题全证据": round(cross / cross_n, 3),
            "误用片段带入": round(ex / ex_n, 3), "_n": {"题": len(cards), "有primary的题": len(full), "primary": prim_n, "跨章题": cross_n}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    chunks, cards = load_chunks(root), load_cards(root)
    bm, agm = BM25(chunks), None
    agm = AGM(chunks, bm)
    q = lambda c: c["question"]
    orders = {
        "BM25": {c["qid"]: sorted(range(len(chunks)), key=lambda i, s=bm.scores(q(c)): -s[i]) for c in cards},
        "AGM": {c["qid"]: agm.rank(q(c)) for c in cards},
        "AGM+反射": {c["qid"]: agm.rank(q(c), reflex=True) for c in cards},
    }
    out = {"语料": {"块": len(chunks), "平均块长": round(statistics.mean(len(c["n"]) for c in chunks)),
                  "总字数": sum(len(c["n"]) for c in chunks), "AGM边数": agm.n_edges}, "读数": {}}
    for B in BUDGETS:
        row = {}
        for name, od in orders.items():
            row[name] = evaluate(cards, lambda c: take(od[c["qid"]], chunks, B))
        runs = []
        for seed in range(5):
            rng = random.Random(seed)
            od = {c["qid"]: agm.rank(q(c), T=0.3, rng=rng) for c in cards}
            runs.append(evaluate(cards, lambda c: take(od[c["qid"]], chunks, B)))
        row["AGM-退火"] = {k: (round(statistics.mean(r[k] for r in runs), 3) if k != "_n" else runs[0][k]) for k in runs[0]}
        rr = []
        for seed in range(5):
            rng = random.Random(100 + seed)
            od = {c["qid"]: rng.sample(range(len(chunks)), len(chunks)) for c in cards}
            rr.append(evaluate(cards, lambda c: take(od[c["qid"]], chunks, B)))
        row["随机"] = {k: (round(statistics.mean(r[k] for r in rr), 3) if k != "_n" else rr[0][k]) for k in rr[0]}
        # 逐题配对：AGM vs BM25 每题 primary 证据保住的句数，谁多
        w = l = 0
        for c in cards:
            ps = [norm(e["quote"]) for e in c.get("supporting_evidence") or [] if e.get("weight") == "primary"]
            if not ps:
                continue
        for A, Bn in (("AGM", "BM25"), ("AGM+反射", "BM25"), ("AGM+反射", "AGM")):
            w = l = t = 0
            for c in cards:
                ps = [norm(e["quote"]) for e in c.get("supporting_evidence") or [] if e.get("weight") == "primary"]
                if not ps:
                    continue
                ca, cb = take(orders[A][c["qid"]], chunks, B), take(orders[Bn][c["qid"]], chunks, B)
                d = sum(x in ca for x in ps) - sum(x in cb for x in ps)
                w += d > 0; l += d < 0; t += d == 0
            n = w + l
            p = min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(w, l) + 1)) / 2 ** n) if n else 1.0
            row[f"配对_{A}对{Bn}"] = {"胜": w, "负": l, "平": t, "符号检验p": round(p, 3)}
        out["读数"][f"预算{B}字"] = row
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    print(txt)
    if a.json:
        pathlib.Path(a.json).write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
