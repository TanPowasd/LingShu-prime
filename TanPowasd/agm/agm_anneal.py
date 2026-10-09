"""AGM v0.5 · 退火式探索 参考原型（纯标准库，只验证提案 §4C）。

两件事：
  A 退火游走：沿边走时按 softmax(w/T) 随机选下一步，温度 T 随尝试次数下降；
    走通了按三因子规则（M=奖励）加强路径上的边。对照：T=0 贪心、T 固定。
  B 随机跳变 + 结晶：游走中以概率 p_jump(T) 跳到一个随机节点（方向随机）；
    含跳变的游走若到达终点，这次跳变「结晶」成一条新边（初始强度 W_NEW、方向随机，之后按路径学方向）；
    睡眠期另外随机长出少量试探边，没被成功路径用上的逐日衰减，低于放电阈值就剪掉。
用法：python agm_anneal.py → 打印读数（JSON）
"""
from __future__ import annotations

import json
import math
import random

K = 8
THETA = 0.2          # 放电阈值（v0.4）：低于它的边走不通，也会被剪掉
W_NEW = 0.3          # 结晶 / 试探边初始强度
ETA_R = 0.3          # 奖励学习率
ETA_DIR = 0.25
MAX_LEN = 6


def unit(a):
    n = math.sqrt(sum(x * x for x in a)) or 1.0
    return [x / n for x in a]


class G:
    def __init__(self, seed):
        self.r = random.Random(seed)
        self.w, self.u, self.born = {}, {}, {}

    def rdir(self):
        return unit([self.r.gauss(0, 1) for _ in range(K)])

    def link(self, i, j, w, kind="原有"):
        self.w[(i, j)], self.u[(i, j)], self.born[(i, j)] = w, self.rdir(), kind

    def nodes(self):
        return sorted({n for e in self.w for n in e})

    def out(self, i):
        return [(j, w) for (a, j), w in self.w.items() if a == i and w >= THETA]

    def walk(self, s, goal, T, p_jump):
        path, jumps, cur = [s], [], s
        for _ in range(MAX_LEN):
            if cur == goal:
                break
            if p_jump > 0 and self.r.random() < p_jump:
                nxt = self.r.choice([n for n in self.nodes() if n not in path] or [cur])
                jumps.append((cur, nxt))
            else:
                opts = [(j, w) for j, w in self.out(cur) if j not in path]
                if not opts:
                    break
                if T <= 0:
                    nxt = max(opts, key=lambda o: o[1])[0]
                else:
                    z = [math.exp(w / T) for _, w in opts]
                    x, acc = self.r.random() * sum(z), 0.0
                    for (j, _), zz in zip(opts, z):
                        acc += zz
                        if acc >= x:
                            nxt = j
                            break
            path.append(nxt)
            cur = nxt
        return path, jumps, cur == goal

    def reward(self, path, jumps):
        for jp in jumps:                              # 跳变结晶成新边
            if jp not in self.w:
                self.link(*jp, W_NEW, kind="结晶")
        steps = list(zip(path, path[1:]))
        R = [0.0] * K
        for e in steps:
            R = [a + self.w[e] * b for a, b in zip(R, self.u[e])]
        Rh = unit(R)
        for e in steps:
            self.w[e] += ETA_R * (1 - self.w[e])      # 三因子：pre=post=1，M=+1
            self.u[e] = unit([(1 - ETA_DIR) * a + ETA_DIR * b for a, b in zip(self.u[e], Rh)])

    def phi(self, path):
        steps = list(zip(path, path[1:]))
        R = [0.0] * K
        for e in steps:
            R = [a + self.w[e] * b for a, b in zip(R, self.u[e])]
        return math.sqrt(sum(x * x for x in R)) / sum(self.w[e] for e in steps)


def trap_graph(seed):
    g = G(seed)
    for a, b, w in [("起点", "A", 0.9), ("A", "A1", 0.9), ("A1", "A2", 0.9),      # 诱人但死路
                    ("起点", "B", 0.5), ("B", "B1", 0.6), ("B1", "终点", 0.7)]:
        g.link(a, b, w)
    return g


def run_A(mode, seed, n=60):
    g = trap_graph(seed)
    hits = []
    for k in range(n):
        T = {"贪心T=0": 0.0, "固定T=0.5": 0.5, "退火T=1→0.02": max(0.02, 1.0 * 0.92 ** k)}[mode]
        path, _, ok = g.walk("起点", "终点", T, 0.0)
        hits.append(ok)
        if ok:
            g.reward(path, [])
    first = next((i + 1 for i, h in enumerate(hits) if h), None)
    return first, sum(hits[-20:]) / 20


def cluster_graph(seed):
    g = G(seed)
    X = ["起点", "x1", "x2", "x3"]
    Y = ["y1", "y2", "y3", "终点"]
    for C in (X, Y):
        for a in C:
            for b in C:
                if a != b and g.r.random() < 0.6:
                    g.link(a, b, round(g.r.uniform(0.3, 0.9), 2))
    return g


def run_B(seed, days=10, queries=10, sprout=3):
    g = cluster_graph(seed)
    rows = []
    for d in range(days):
        T = max(0.05, 0.8 * 0.7 ** d)
        p_jump = 0.3 * T / 0.8
        ok_n = 0
        for _ in range(queries):
            path, jumps, ok = g.walk("起点", "终点", T, p_jump)
            if ok:
                ok_n += 1
                g.reward(path, jumps)
        # 睡眠：随机长试探边；未被加强的新边衰减，跌破阈值剪掉
        ns = g.nodes()
        for _ in range(sprout):
            a, b = g.r.sample(ns, 2)
            if (a, b) not in g.w:
                g.link(a, b, W_NEW, kind="试探")
        pruned = 0
        for e in [e for e, k in g.born.items() if k != "原有"]:
            g.w[e] *= 0.6
            if g.w[e] < THETA:
                del g.w[e], g.u[e], g.born[e]
                pruned += 1
        bridges = [e for e in g.w if (e[0] in ("起点", "x1", "x2", "x3")) != (e[1] in ("起点", "x1", "x2", "x3"))]
        rows.append({"天": d + 1, "T": round(T, 3), "p_jump": round(p_jump, 3), "成功率": ok_n / queries,
                     "剪掉": pruned, "跨簇桥": len(bridges)})
    # 末了：关掉随机性，只靠留下来的边能不能走到
    path, _, ok = g.walk("起点", "终点", 0.0, 0.0)
    return rows, {"无随机性还能走到": ok, "路径": path if ok else None,
                  "直度": round(g.phi(path), 3) if ok else None,
                  "留下的新边": sum(1 for k in g.born.values() if k != "原有")}


def main():
    A = {}
    for mode in ("贪心T=0", "固定T=0.5", "退火T=1→0.02"):
        res = [run_A(mode, s) for s in range(50)]
        firsts = [f for f, _ in res if f]
        A[mode] = {"50次里找到终点的": len(firsts),
                   "首次走通平均尝试数": round(sum(firsts) / len(firsts), 1) if firsts else None,
                   "最后20次成功率(平均)": round(sum(r for _, r in res) / len(res), 3)}
    rows, end = run_B(seed=3)
    # B 的稳健性：多个种子
    multi = [run_B(seed=s)[1]["无随机性还能走到"] for s in range(30)]
    no_jump = []
    for s in range(30):
        g = cluster_graph(s)
        no_jump.append(any(g.walk("起点", "终点", 0.5, 0.0)[2] for _ in range(100)))
    print(json.dumps({"A_退火游走(陷阱图)": A,
                      "B_跳变结晶(两簇无桥, 种子3逐日)": rows, "B_结束时": end,
                      "B_30个种子": {"不跳变、走100次能到": sum(no_jump), "跳变+结晶后无随机性能到": sum(multi)}},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
