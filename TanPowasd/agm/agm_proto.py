"""AGM 联想图记忆 · 参考原型（纯标准库，仅用于验证提案里的公式行为，不是实现）。

用法：python agm_proto.py      → 打印 5 组读数（JSON）
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict

D = 256  # 原型用字符 n-gram 哈希向量；正式系统换句向量模型


def embed(text: str):
    v = [0.0] * D
    s = f"^{text}$"
    for n in (1, 2):
        for i in range(len(s) - n + 1):
            h = int(hashlib.md5(s[i:i + n].encode()).hexdigest(), 16)
            v[h % D] += 1.0 if (h >> 9) & 1 else -1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


# ---------------- 参数（与提案 §9 参数表同名） ----------------
P = dict(tau0=1.0, psi0=0.5, kappa=1.0, eta_s=1.0, tau_s=1.0, theta_fix=3.0,
         alpha=2.0, beta=4.0, gamma=1.0, bias=-2.0,
         eta_h=0.3, lam_h=0.01, fwd=1.0, bwd=0.4,
         merge=0.92, k_link=4, steps=3, leak=0.5, topk=8)


class Node:
    __slots__ = ("id", "text", "e", "t0", "t_last", "n", "s")

    def __init__(self, nid, text, t):
        self.id, self.text, self.e = nid, text, embed(text)
        self.t0 = self.t_last = t
        self.n, self.s = 1, 0.0


class AGM:
    def __init__(self, **kw):
        self.p = dict(P, **kw)
        self.nodes = {}
        self.h = defaultdict(float)   # (i, j) 有向赫布强度 h_ij ∈ [0,1)
        self.tau = defaultdict(float)  # (i, j) 时序邻接 τ_ij
        self.last = None

    # —— 时间权重：幂律遗忘，固化越高衰减越慢 ——
    def D(self, node, t):
        psi = self.p["psi0"] / (1 + self.p["kappa"] * node.s)
        return (1 + max(0.0, t - node.t_last) / self.p["tau0"]) ** (-psi)

    # —— 固化：间隔效应，Δt 越长单次增益越大（饱和） ——
    def reinforce(self, node, t):
        dt = max(0.0, t - node.t_last)
        node.s += self.p["eta_s"] * (1 - math.exp(-dt / self.p["tau_s"]))
        node.n += 1
        node.t_last = t

    def fixed(self, node):
        return node.s >= self.p["theta_fix"]

    def W(self, i, j, t):
        a, b = self.nodes[i], self.nodes[j]
        z = (self.p["alpha"] * cos(a.e, b.e) + self.p["beta"] * self.h[(i, j)]
             + self.p["gamma"] * self.tau[(i, j)] + self.p["bias"])
        return 1 / (1 + math.exp(-z)) * self.D(b, t)

    def remember(self, text, t, context=()):
        e = embed(text)
        best = max(self.nodes.values(), key=lambda n: cos(n.e, e), default=None)
        if best is not None and cos(best.e, e) >= self.p["merge"]:
            self.reinforce(best, t)          # 反复提及 → 合并进旧节点并固化
            nid = best.id
        else:
            nid = f"m{len(self.nodes)}"
            self.nodes[nid] = Node(nid, text, t)
        if self.last and self.last != nid:   # 时序：前向强、后向弱（非对称）
            self.tau[(self.last, nid)] = min(1.0, self.tau[(self.last, nid)] + self.p["fwd"])
            self.tau[(nid, self.last)] = min(1.0, self.tau[(nid, self.last)] + self.p["bwd"])
        for c in context:                    # 共现 → 赫布
            self.hebb(c, nid, 1.0, 1.0)
        self.last = nid
        return nid

    def hebb(self, i, j, ai, aj, first=None):
        """Δh = η·a_i·a_j·(1-h) − λh；i 先于 j 激活时 i→j 得全额、j→i 得 bwd 比例。"""
        for (x, y), g in (((i, j), 1.0), ((j, i), self.p["bwd"])):
            hv = self.h[(x, y)]
            self.h[(x, y)] = hv + self.p["eta_h"] * g * ai * aj * (1 - hv) - self.p["lam_h"] * hv

    def recall(self, query, t, k=3, spread=True):
        q = embed(query)
        x = {nid: max(0.0, cos(n.e, q)) for nid, n in self.nodes.items()}
        seeds = dict(sorted(x.items(), key=lambda kv: -kv[1])[: self.p["topk"]])
        a = dict(seeds)
        if spread:   # 扩散激活：a ← (1-δ)·Wᵀa + x，侧抑制保留 top-k
            for _ in range(self.p["steps"]):
                nxt = defaultdict(float)
                for i, ai in a.items():
                    for j in self.nodes:
                        if j != i:
                            nxt[j] += ai * self.W(i, j, t)
                a = {j: (1 - self.p["leak"]) * v + seeds.get(j, 0.0) for j, v in nxt.items()}
                a = dict(sorted(a.items(), key=lambda kv: -kv[1])[: self.p["topk"]])
        ranked = sorted(a.items(), key=lambda kv: -kv[1] * self.D(self.nodes[kv[0]], t))
        return [self.nodes[i].text for i, _ in ranked[:k]]


def main():
    out = {}
    # 1 非对称联想：按顺序经历 A→B，前向权重 > 后向
    g = AGM()
    a = g.remember("早上煮咖啡", 0); b = g.remember("出门赶地铁", 0.1)
    out["asymmetry"] = {"W(咖啡→地铁)": round(g.W(a, b, 0.2), 4), "W(地铁→咖啡)": round(g.W(b, a, 0.2), 4)}
    # 2 遗忘曲线：未固化 vs 固化节点，在 t=1,10,100 的时间权重
    g = AGM(); n1 = g.nodes[g.remember("一次性记忆", 0)]
    n2 = g.nodes[g.remember("反复记忆", 0)]
    for t in (2, 6, 14, 30):
        g.reinforce(n2, t)
    n1.t_last = n2.t_last = 30
    out["forgetting"] = {f"t+{d}": {"once": round(g.D(n1, 30 + d), 3), "consolidated": round(g.D(n2, 30 + d), 3)}
                         for d in (1, 10, 100)}
    out["forgetting"]["s(consolidated)"] = round(n2.s, 3); out["forgetting"]["fixed"] = g.fixed(n2)
    # 3 间隔效应：同样 4 次复习，集中（Δt=0.1）vs 间隔（Δt=2）
    g = AGM(); m = g.nodes[g.remember("集中复习", 0)]; s = g.nodes[g.remember("间隔复习", 0)]
    for i in range(1, 5):
        g.reinforce(m, 0.1 * i); g.reinforce(s, 2.0 * i)
    out["spacing"] = {"massed_s": round(m.s, 3), "spaced_s": round(s.s, 3)}
    # 4 反复提及合并：近重复文本不新建节点
    g = AGM()
    for t, txt in enumerate(["我住在法兰克福", "我住在法兰克福", "我住在法兰克福。"]):
        g.remember(txt, t * 3)
    nn = list(g.nodes.values())
    out["merge"] = {"nodes": len(nn), "mentions": [x.n for x in nn], "s": [round(x.s, 3) for x in nn]}
    # 5 联想召回：查询与目标字面无关，纯向量召不回；经共现边扩散可召回
    g = AGM()
    ids = [g.remember(t, i) for i, t in enumerate(
        ["奶奶家的院子", "夏天的蝉鸣", "外婆做的桂花糕", "期末考试复习", "地铁换乘路线", "公司周会纪要"])]
    for _ in range(4):
        g.hebb(ids[0], ids[2], 1, 1)       # 院子 ↔ 桂花糕 多次同时想起
    q = "奶奶家的院子"
    out["association"] = {"query": q, "vector_only": g.recall(q, 6, spread=False),
                          "spreading": g.recall(q, 6, spread=True)}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
