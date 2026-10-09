"""AGM v0.3 · 矢量边（每条边独立学方向）与路径保留 参考原型（纯标准库，只验证提案 §3A）。

边 i→j 是矢量 v_ij = w_ij · û_ij：û_ij 每条边独立学习（正反两条边方向各自独立），w_ij 是联想强度。
路径 P 的
  合矢量   R(P) = Σ w_t · û_t                    （按权重加权的方向和）
  路径强度 S(P) = Σ w_t · w_t / Σ w_t            （按权重加权：强的一步说话分量大）
  直度     φ(P) = |R| / Σ w_t ∈ [0,1]            （1＝各步同向，思路笔直）
走过的路径完整保存；走熟了长出捷径边，其方向就是 R 的方向——捷径直接指向终点，路径仍保留。
方向学习：每走一次，各步方向朝 R 的方向转一小步（η_dir），常走的思路越走越直。
用法：python agm_vector.py → 打印读数（JSON）
"""
from __future__ import annotations

import heapq
import json
import math
import random

K = 8
ETA_DIR = 0.25
SHORTCUT_AFTER = 3


def add(a, b): return [x + y for x, y in zip(a, b)]
def scale(a, c): return [x * c for x in a]
def norm(a): return math.sqrt(sum(x * x for x in a))
def unit(a):
    n = norm(a) or 1.0
    return [x / n for x in a]
def cos(a, b): return sum(x * y for x, y in zip(unit(a), unit(b)))


class VGraph:
    def __init__(self, seed=7):
        self.rng = random.Random(seed)
        self.u = {}          # (i,j) → 单位方向（独立学习）
        self.w = {}          # (i,j) → 强度
        self.paths = {}      # id → {"nodes","uses","R","S","phi"}
        self.shortcut = {}   # (起,终) → {"w","u","path","stale"}

    def rand_dir(self):
        return unit([self.rng.gauss(0, 1) for _ in range(K)])

    def link(self, i, j, w_ij, w_ji, u_ij=None, u_ji=None):
        self.w[(i, j)], self.w[(j, i)] = w_ij, w_ji
        self.u[(i, j)] = u_ij or self.rand_dir()
        self.u[(j, i)] = u_ji or self.rand_dir()          # 反向边方向独立，不强制相反

    def v(self, i, j):
        return scale(self.u[(i, j)], self.w[(i, j)])

    def measure(self, nodes):
        steps = list(zip(nodes, nodes[1:]))
        R = [0.0] * K
        for e in steps:
            R = add(R, self.v(*e))
        ws = [self.w[e] for e in steps]
        S = sum(x * x for x in ws) / sum(ws)
        return R, S, norm(R) / sum(ws)

    def walk(self, nodes, learn=True):
        R, S, phi = self.measure(nodes)
        pid = "→".join(nodes)
        rec = self.paths.setdefault(pid, {"nodes": list(nodes), "uses": 0})
        rec["uses"] += 1
        if learn:                                   # 各步方向朝合矢量方向转一小步
            r = unit(R)
            for e in zip(nodes, nodes[1:]):
                self.u[e] = unit(add(scale(self.u[e], 1 - ETA_DIR), scale(r, ETA_DIR)))
            R, S, phi = self.measure(nodes)
        rec.update(R=R, S=S, phi=phi)
        if rec["uses"] >= SHORTCUT_AFTER:
            self.shortcut[(nodes[0], nodes[-1])] = {"w": S, "u": unit(R), "path": pid, "stale": False}
        return rec

    def best_path(self, start, target, max_len=5):
        """不靠位置：按加权路径强度 S 做最优优先搜索，返回完整路径。"""
        heap = [(-1.0, [start])]
        best = None
        while heap:
            negs, path = heapq.heappop(heap)
            if path[-1] == target:
                if best is None or -negs > best[0]:
                    best = (-negs, path)
                continue
            if len(path) > max_len:
                continue
            for (a, b) in self.w:
                if a == path[-1] and b not in path:
                    p2 = path + [b]
                    heapq.heappush(heap, (-self.measure(p2)[1], p2))
        return best

    def set_weight(self, i, j, w):
        self.w[(i, j)] = w
        for sc in self.shortcut.values():
            nodes = self.paths[sc["path"]]["nodes"]
            if (i, j) in zip(nodes, nodes[1:]):
                sc["stale"] = True

    def refresh(self, key):
        sc = self.shortcut[key]
        R, S, _ = self.measure(self.paths[sc["path"]]["nodes"])
        sc.update(w=S, u=unit(R), stale=False)
        return sc

    def cycle_residual(self, cycle):
        """闭合回路的合矢量长度 / 总强度：方向独立学习后，残差大＝这圈联想互相矛盾。"""
        R = [0.0] * K
        tot = 0.0
        for e in zip(cycle, cycle[1:] + cycle[:1]):
            R = add(R, self.v(*e)); tot += self.w[e]
        return norm(R) / tot


def main():
    g = VGraph()
    for a, b, f, r in [("家", "院子", 0.9, 0.5), ("院子", "桂花树", 0.8, 0.6), ("桂花树", "桂花糕", 0.9, 0.3),
                       ("家", "厨房", 0.7, 0.7), ("厨房", "桂花糕", 0.4, 0.2), ("家", "地铁", 0.6, 0.6),
                       ("地铁", "公司", 0.9, 0.8)]:
        g.link(a, b, f, r)
    out = {}
    v1, v2 = g.v("桂花树", "桂花糕"), g.v("桂花糕", "桂花树")
    out["edges_independent"] = {"|v(树→糕)|": round(norm(v1), 3), "|v(糕→树)|": round(norm(v2), 3),
                                "cos(正反方向)": round(cos(v1, v2), 3)}
    chain = ["家", "院子", "桂花树", "桂花糕"]
    R, S, phi = g.measure(chain)
    out["path_before_learning"] = {"S(按权重加权)": round(S, 4), "乘积(对照)": round(0.9 * 0.8 * 0.9, 4),
                                   "算术平均(对照)": round((0.9 + 0.8 + 0.9) / 3, 4), "直度φ": round(phi, 3)}
    phis = []
    for _ in range(5):
        phis.append(round(g.walk(chain)["phi"], 3))
    out["straightening_phi_per_walk"] = phis
    sc = g.shortcut[("家", "桂花糕")]
    R, _, _ = g.measure(chain)
    out["shortcut"] = {"w": round(sc["w"], 4), "cos(捷径方向, 路径合矢量)": round(cos(sc["u"], R), 6),
                       "via_path": sc["path"], "path_still_stored": sc["path"] in g.paths}
    s, p = g.best_path("家", "桂花糕")
    out["best_path(家→桂花糕)"] = {"path": p, "S": round(s, 4)}
    g.set_weight("院子", "桂花树", 0.1)
    st = g.shortcut[("家", "桂花糕")]["stale"]
    new = g.refresh(("家", "桂花糕"))
    s2, p2 = g.best_path("家", "桂花糕")
    out["after_mid_edge_weakened"] = {"stale_detected": st, "shortcut_w_refreshed": round(new["w"], 4),
                                      "best_path_now": p2, "S": round(s2, 4)}
    # 回路残差：一致的回路（方向首尾相接可闭合）vs 随机方向的回路
    h = VGraph(seed=3)
    d1, d2 = h.rand_dir(), h.rand_dir()
    d3 = unit(scale(add(d1, d2), -1))
    h.link("A", "B", 1.0, 0.5, d1); h.link("B", "C", 1.0, 0.5, d2); h.link("C", "A", math.sqrt(2 + 2 * sum(x * y for x, y in zip(d1, d2))), 0.5, d3)
    h.link("X", "Y", 1.0, 0.5); h.link("Y", "Z", 1.0, 0.5); h.link("Z", "X", 1.0, 0.5)
    out["cycle_residual"] = {"一致回路 A→B→C→A": round(h.cycle_residual(["A", "B", "C"]), 4),
                             "随机方向回路 X→Y→Z→X": round(h.cycle_residual(["X", "Y", "Z"]), 4)}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
