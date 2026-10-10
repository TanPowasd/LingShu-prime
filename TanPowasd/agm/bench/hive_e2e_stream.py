"""AGM × hive-memory-bench 真实对话史轨（e2e）· 流式续接支撑基准（零 LLM、零网络）。

官方 C 型成绩要生成器作答 + LLM 判官；这里换一个不需要 LLM 的代理读数，并且**让系统边读边学**，
这样 AGM 的固化、条件反射、赫布边才有机会起作用（主轮检索面每题只问一次，测不到这些）。

流程（每份对话各自从头开始，按轮次时间顺序）：
  对每个「我说」轮 t：
    1 用该轮文字作查询，从**此前全部历史**（不含本轮）里按字数预算取上下文；
    2 评分：AI 在本轮之后真实的回复里，「显著二元组」有多少比例出现在取到的上下文里
      （显著＝本文件内只在 ≤2% 的块中出现；先剔除查询本身已有的二元组——只算历史额外提供的支撑）；
    3 评分之后才学习：AI 回复里真正用到了哪些取回块（与回复共享 ≥3 个显著二元组）→ 加强。
  另在 C 型题卡的断点处（答案行之前截断），以题卡 pre 轮作查询，按同法给「真实下文（人类下一句 + AI 恢复开头）」打分。
被测臂：
  最近窗口   直接取断点前最近的 N 字（「不用记忆系统，接着往下聊」的朴素做法）
  BM25       二元组 BM25（集合版）
  AGM-静态   BM25 种子 + 时序边/对话邻接边上扩散，放电阈值，不学习
  AGM-学习   在静态之上：使用固化（被用上的块 salience 升高、按距上次使用的轮数幂律衰减）、
             条件关键词反射（查询关键词 → 被用上的块，Rescorla–Wagner 习得/消退）、共用块之间的赫布边
用法：python hive_e2e_stream.py <hive-memory-bench 路径> [--files 文件名…] [--budget 4000] [--json 输出]
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import re
import statistics
import time

CHUNK = 300
SPEAKERS = {"**我说：**": "human", "**DeepSeek说：**": "ai"}


def norm(s):
    return re.sub(r"[^\w]", "", s, flags=re.UNICODE)


def bset(s):
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def parse(path):
    turns, cur = [], None
    for ln, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        st = line.strip()
        if st in SPEAKERS:
            cur = {"who": SPEAKERS[st], "line": ln, "lines": []}
            turns.append(cur)
        elif cur is not None:
            cur["lines"].append((ln, line))
    for t in turns:
        t["text"] = "\n".join(x for _, x in t["lines"])
    return turns


def chunk_turn(t):
    out, buf, start = [], "", None
    for ln, x in t["lines"]:
        if start is None:
            start = ln
        buf += x + "\n"
        if len(norm(buf)) >= CHUNK:
            out.append((start, buf)); buf, start = "", None
    if norm(buf):
        out.append((start, buf))
    return out


class Store:
    """共享的块存储与倒排索引；各臂在其上维护各自的学习状态。"""

    def __init__(self):
        self.text, self.bs, self.len, self.turn, self.line = [], [], [], [], []
        self.inv = collections.defaultdict(list)

    def add(self, turn_idx, line, text):
        i = len(self.text)
        b = bset(text)
        self.text.append(norm(text)); self.bs.append(b); self.len.append(len(norm(text)))
        self.turn.append(turn_idx); self.line.append(line)
        for g in b:
            self.inv[g].append(i)
        return i

    @property
    def N(self):
        return len(self.text)

    def bm25(self, q):
        N = self.N
        if not N:
            return {}
        cap = max(5, int(0.05 * N))
        avg = sum(self.len) / N
        sc = collections.defaultdict(float)
        for g in q:
            post = self.inv.get(g)
            if not post or len(post) > cap:
                continue
            idf = math.log(1 + (N - len(post) + 0.5) / (len(post) + 0.5))
            for i in post:
                sc[i] += idf
        for i in sc:
            sc[i] /= 0.25 + 0.75 * self.len[i] / avg
        return sc


def take(order, st, budget):
    got, used = [], 0
    for i in order:
        if used + st.len[i] > budget and used:
            break
        got.append(i); used += st.len[i]
    return got


class Agm:
    SEEDS, DECAY, THETA, KWTA = 8, 0.35, 0.05, 80
    W_FWD, W_BWD, W_QA = 0.5, 0.25, 0.4
    MU, D_EXP = 0.5, 0.5                  # 固化增益、幂律衰减指数
    ALPHA, BETA, TH_REFLEX = 0.25, 0.15, 0.5
    ETA_H, W_HEBB_MAX, HEBB_TOP, OUT_BUDGET = 0.1, 0.3, 3, 8

    def __init__(self, st, learn, parts=("固化", "反射", "赫布")):
        self.st, self.learn, self.parts = st, learn, set(parts) if learn else set()
        self.out = collections.defaultdict(dict)
        self.s = collections.defaultdict(float)      # 使用固化
        self.last = {}
        self.V = collections.defaultdict(dict)       # 关键词 → {块: 反射强度}
        self.seen = collections.Counter()

    def link_new(self, i, prev_same_turn, prev_turn_last):
        if prev_same_turn is not None:
            self.out[prev_same_turn][i] = self.W_FWD; self.out[i][prev_same_turn] = self.W_BWD
        elif prev_turn_last is not None:          # 对话邻接：上一轮最后一块 → 本轮第一块
            self.out[prev_turn_last][i] = self.W_QA; self.out[i][prev_turn_last] = self.W_BWD

    def keywords(self, q):
        N = self.st.N
        cap = max(5, int(0.02 * N))
        return [g for g in q if 1 <= len(self.st.inv.get(g, ())) <= cap]

    def rank(self, q, t_now):
        sc = self.st.bm25(q)
        if not sc:
            return []
        top = sorted(sc, key=lambda i: -sc[i])[: self.SEEDS]
        m = sc[top[0]] or 1.0
        x = {i: sc[i] / m for i in top}
        if "反射" in self.parts:
            r = collections.defaultdict(float)
            for g in self.keywords(q):
                gain = 1 / (1 + math.log1p(self.seen[g]))
                for j, v in self.V.get(g, {}).items():
                    r[j] = max(r[j], v * gain)
            for j, v in r.items():
                if v >= self.TH_REFLEX:
                    x[j] = max(x.get(j, 0), v)
        a = dict(x)
        for _ in range(2):
            nxt = collections.defaultdict(float)
            for i, ai in a.items():
                for j, w in self.out[i].items():
                    nxt[j] += ai * w
            for i, v in x.items():
                nxt[i] += v
            nxt = {i: (v if i in x else (1 - self.DECAY) * v) for i, v in nxt.items()}
            a = dict(sorted(((i, v) for i, v in nxt.items() if v >= self.THETA), key=lambda kv: -kv[1])[: self.KWTA])
        if "固化" in self.parts:
            for i in a:
                if self.s[i]:
                    D = (1 + t_now - self.last[i]) ** -self.D_EXP
                    a[i] *= 1 + self.MU * self.s[i] * D
        rest = sorted((i for i in sc if i not in a), key=lambda i: -sc[i])
        return sorted(a, key=lambda i: -a[i]) + rest

    def feedback(self, q, got, used, t_now):
        if not self.learn:
            return
        kws = self.keywords(q)
        U = set(used)
        if not U:                       # 习惯化只记「出现了却没有后果」的次数（v0.6 §4D.3）
            for g in kws:
                self.seen[g] += 1
        for i in got:
            for g in kws:
                v = self.V[g].get(i, 0.0)
                if i in U:
                    self.V[g][i] = v + self.ALPHA * (1 - v)
                elif v:
                    self.V[g][i] = v - self.BETA * v
        if "固化" in self.parts:
            for i in used:
                self.s[i] = min(5.0, self.s[i] + 1.0); self.last[i] = t_now
        top = used[: self.HEBB_TOP] if "赫布" in self.parts else []   # 只连最相关的几块，防止成团
        for i in top:
            for j in top:
                if i != j:
                    w = self.out[i].get(j, 0.0)
                    self.out[i][j] = min(self.W_HEBB_MAX, w + self.ETA_H * (1 - w))
            if len(self.out[i]) > self.OUT_BUDGET:                # 出边预算（稳态，v0.4 §4B-2）
                keep = sorted(self.out[i].items(), key=lambda kv: -kv[1])[: self.OUT_BUDGET]
                self.out[i] = dict(keep)


def run_file(path, cards, budget):
    turns = parse(path)
    st = Store()
    # 本文件的显著二元组（评分口径）：先整体切块数 df
    all_chunks = [c for t in turns for c in chunk_turn(t)]
    dfc = collections.Counter(g for _, x in all_chunks for g in bset(x))
    cap = max(2, int(0.02 * len(all_chunks)))
    salient = lambda s: {g for g in bset(s) if dfc.get(g, 0) <= cap}

    arms = {"最近窗口": None, "BM25": None, "AGM-静态": Agm(st, False), "AGM-学习": Agm(st, True)}
    turn_scores = {k: [] for k in arms}
    card_scores = {k: [] for k in arms}
    card_at = collections.defaultdict(list)
    for c in cards:
        card_at[c["answer"]["human"]["line"]].append(c)
    last_chunk_of_turn = None

    def order_for(name, q, t_idx):
        if name == "最近窗口":
            return list(range(st.N - 1, -1, -1))
        if name == "BM25":
            sc = st.bm25(q)
            return sorted(sc, key=lambda i: -sc[i])
        return arms[name].rank(q, t_idx)

    def score(got, target, q):
        tgt = salient(target) - q
        if not tgt:
            return None
        ctx = set().union(*(st.bs[i] for i in got)) if got else set()
        return len(tgt & ctx) / len(tgt)

    for t_idx, t in enumerate(turns):
        # 断点题卡：在把这一轮写入之前作答（截断到答案行前）
        lo, hi = t["line"], (t["lines"][-1][0] if t["lines"] else t["line"])
        hit = [c for L, cs_ in card_at.items() if lo <= L <= hi for c in cs_] if t["who"] == "human" else []
        for c in hit:
            q = set().union(*(bset(p["text"]) for p in c["pre"]))
            target = c["answer"]["human"]["text"] + ((c["answer"].get("ai_opening") or {}).get("text") or "")
            for name in arms:
                got = take(order_for(name, q, t_idx), st, budget)
                v = score(got, target, q)
                if v is not None:
                    card_scores[name].append(v)
        if t["who"] == "human" and t_idx + 1 < len(turns) and turns[t_idx + 1]["who"] == "ai" and st.N:
            q = bset(t["text"])
            reply = turns[t_idx + 1]["text"]
            rs = salient(reply)
            for name in arms:
                got = take(order_for(name, q, t_idx), st, budget)
                v = score(got, reply, q)
                if v is not None:
                    turn_scores[name].append(v)
                if isinstance(arms[name], Agm):
                    used = sorted((i for i in got if len(st.bs[i] & rs) >= 3), key=lambda i: -len(st.bs[i] & rs))
                    arms[name].feedback(q, got, used, t_idx)
        # 写入本轮
        prev = None
        for ln, x in chunk_turn(t):
            i = st.add(t_idx, ln, x)
            for a in arms.values():
                if isinstance(a, Agm):
                    a.link_new(i, prev, last_chunk_of_turn if prev is None else None)
            prev = i
        if prev is not None:
            last_chunk_of_turn = prev
    return turn_scores, card_scores, len(turns), st.N


def paired(a, b):
    w = sum(x > y for x, y in zip(a, b)); l = sum(x < y for x, y in zip(a, b)); n = w + l
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(w, l) + 1)) / 2 ** n) if n else 1.0
    return {"胜": w, "负": l, "平": len(a) - n, "符号检验p": round(p, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--budget", type=int, default=4000)
    ap.add_argument("--parts", default="固化,反射,赫布", help="AGM-学习启用哪些学习部件（消融用）")
    ap.add_argument("--json")
    A = ap.parse_args()
    Agm.__init__.__defaults__ = (tuple(p for p in A.parts.split(",") if p),)
    root = pathlib.Path(A.root) / "e2e"
    cards = json.loads((root / "questions" / "题卡_C型_续接预测_v0.1.json").read_text(encoding="utf-8"))
    files = A.files or sorted(p.name for p in (root / "corpus").glob("*.md"))
    T = collections.defaultdict(list); C = collections.defaultdict(list); per = {}
    t0 = time.time()
    for f in files:
        ts, cs, nt, nc = run_file(root / "corpus" / f, [c for c in cards if c["file"] == f], A.budget)
        per[f] = {"轮": nt, "块": nc, "查询": len(ts["BM25"]), "题卡": len(cs["BM25"]),
                  **{k: round(statistics.mean(v), 4) for k, v in ts.items() if v}}
        for k in ts:
            T[k] += ts[k]; C[k] += cs[k]
        print(f, per[f], f"{time.time() - t0:.0f}s", flush=True)
    out = {"预算字数": A.budget, "学习部件": A.parts, "文件": per,
           "逐轮续接支撑(均值)": {k: round(statistics.mean(v), 4) for k, v in T.items()},
           "题卡断点支撑(均值)": {k: round(statistics.mean(v), 4) for k, v in C.items() if v},
           "_n": {"逐轮": len(T["BM25"]), "题卡": len(C["BM25"])},
           "配对_逐轮": {f"{a}对{b}": paired(T[a], T[b]) for a, b in
                      (("AGM-学习", "AGM-静态"), ("AGM-学习", "BM25"), ("AGM-静态", "BM25"), ("BM25", "最近窗口"), ("AGM-学习", "最近窗口"))},
           "配对_题卡": {f"{a}对{b}": paired(C[a], C[b]) for a, b in
                      (("AGM-学习", "AGM-静态"), ("AGM-学习", "BM25"), ("BM25", "最近窗口"))}}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    print(txt)
    if A.json:
        pathlib.Path(A.json).write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
