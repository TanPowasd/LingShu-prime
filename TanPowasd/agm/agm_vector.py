"""AGM v0.2 · 矢量边与路径保留 参考原型（纯标准库，只验证提案 §3A 的行为）。

每个节点在「联想空间」里有一个位置 p_i ∈ R^k。
一条边 i→j 是一个矢量：方向 û_ij = (p_j − p_i)/|p_j − p_i|，大小 = 联想强度 w_ij。
同一对节点正反两条边方向相反、大小各自独立（w_ij ≠ w_ji）。
路径的合位移 Σ(p_{t+1} − p_t) 恰好等于 p_终 − p_起：合矢量直接指向终点，
而路径本身（每一步的节点与矢量）完整保存，可随时拆回。
用法：python agm_vector.py → 打印读数（JSON）
"""
from __future__ import annotations

import json
import math
import random

K = 8


def sub(a, b): return [x - y for x, y in zip(a, b)]
def add(a, b): return [x + y for x, y in zip(a, b)]
def norm(a): return math.sqrt(sum(x * x for x in a))
def unit(a):
    n = norm(a) or 1.0
    return [x / n for x in a]
def cos(a, b): return sum(x * y for x, y in zip(unit(a), unit(b)))


class VGraph:
    def __init__(self, seed=7):
        self.rng = random.Random(seed)
        self.p = {}          # 节点位置
        self.w = {}          # (i,j) → 强度
        self.paths = {}      # 路径 id → {"nodes", "steps":[(i,j,向量,强度)], "uses"}
        self.shortcut = {}   # (起,终) → {"w", "path", "stale"}
        self.SHORTCUT_AFTER = 3

    def node(self, name, near=None, spread=1.0):
        base = self.p[near] if near else [0.0] * K
        self.p[name] = [b + self.rng.gauss(0, spread) for b in base]

    def link(self, i, j, w_ij, w_ji):
        self.w[(i, j)], self.w[(j, i)] = w_ij, w_ji

    def vec(self, i, j):
        """边矢量 = 强度 × 方向。"""
        return [self.w.get((i, j), 0.0) * x for x in unit(sub(self.p[j], self.p[i]))]

    def walk(self, nodes):
        """沿给定节点序列走一遍：记录路径（不压缩），返回合位移与路径强度。"""
        steps = [(a, b, self.vec(a, b), self.w[(a, b)]) for a, b in zip(nodes, nodes[1:])]
        pid = "→".join(nodes)
        rec = self.paths.setdefault(pid, {"nodes": list(nodes), "steps": steps, "uses": 0})
        rec["steps"] = steps
        rec["uses"] += 1
        disp = [0.0] * K
        for a, b in zip(nodes, nodes[1:]):
            disp = add(disp, sub(self.p[b], self.p[a]))
        strength = math.prod(s[3] for s in steps)
        if rec["uses"] >= self.SHORTCUT_AFTER:   # 反复走同一条路 → 长出捷径边，但路径保留
            key = (nodes[0], nodes[-1])
            self.shortcut[key] = {"w": strength, "path": pid, "stale": False}
        return {"path": pid, "displacement": disp, "strength": strength}

    def navigate(self, start, target, max_steps=6):
        """目标导向：每步选 w_ij · cos(û_ij, p_target − p_now) 最大的出边；返回完整路径。"""
        now, seen, route = start, {start}, [start]
        for _ in range(max_steps):
            if now == target:
                break
            want = sub(self.p[target], self.p[now])
            cand = [(self.w[(a, b)] * cos(sub(self.p[b], self.p[a]), want), b)
                    for (a, b) in self.w if a == now and b not in seen]
            if not cand:
                break
            score, nxt = max(cand)
            if score <= 0:
                break
            route.append(nxt); seen.add(nxt); now = nxt
        return route

    def set_weight(self, i, j, w):
        """中途某条边变了：依赖它的捷径标记为过期，路径记录不动。"""
        self.w[(i, j)] = w
        for key, sc in self.shortcut.items():
            steps = self.paths[sc["path"]]["steps"]
            if any(a == i and b == j for a, b, _, _ in steps):
                sc["stale"] = True


def main():
    g = VGraph()
    g.node("家")
    g.node("院子", near="家"); g.node("桂花树", near="院子"); g.node("桂花糕", near="桂花树")
    g.node("厨房", near="家"); g.node("地铁", spread=3.0); g.node("公司", near="地铁")
    for a, b, f, r in [("家", "院子", 0.9, 0.5), ("院子", "桂花树", 0.8, 0.6), ("桂花树", "桂花糕", 0.9, 0.3),
                       ("家", "厨房", 0.7, 0.7), ("厨房", "桂花糕", 0.4, 0.2), ("家", "地铁", 0.6, 0.6),
                       ("地铁", "公司", 0.9, 0.8)]:
        g.link(a, b, f, r)
    out = {}
    # 1 正反两条边：方向相反、大小不同
    v1, v2 = g.vec("桂花树", "桂花糕"), g.vec("桂花糕", "桂花树")
    out["opposite_edges"] = {"|v(树→糕)|": round(norm(v1), 3), "|v(糕→树)|": round(norm(v2), 3),
                             "cos(两者方向)": round(cos(v1, v2), 3)}
    # 2 合矢量指向终点：路径合位移 vs 起点→终点直线位移
    chain = ["家", "院子", "桂花树", "桂花糕"]
    r = g.walk(chain)
    direct = sub(g.p["桂花糕"], g.p["家"])
    out["resultant_points_to_end"] = {"cos(合位移, 起→终)": round(cos(r["displacement"], direct), 6),
                                      "残差|合位移−(p终−p起)|": round(norm(sub(r["displacement"], direct)), 9),
                                      "路径强度(各步相乘)": round(r["strength"], 4)}
    # 3 路径保留：拆回每一步
    out["path_kept"] = [{"from": a, "to": b, "w": w, "|v|": round(norm(v), 3)}
                        for a, b, v, w in g.paths[r["path"]]["steps"]]
    # 4 导航：只给终点，按方向一步步走，返回完整中途路径
    out["navigate(家→桂花糕)"] = g.navigate("家", "桂花糕")
    out["navigate(家→公司)"] = g.navigate("家", "公司")
    # 5 捷径：同一路径走满 3 次长出 家→桂花糕 捷径边，路径记录仍在
    g.walk(chain); g.walk(chain)
    sc = g.shortcut.get(("家", "桂花糕"))
    out["shortcut"] = {"exists": sc is not None, "w": round(sc["w"], 4), "via_path": sc["path"],
                       "path_still_stored": sc["path"] in g.paths, "uses": g.paths[sc["path"]]["uses"]}
    # 6 中途边变化 → 捷径过期，路径不丢
    g.set_weight("院子", "桂花树", 0.1)
    out["after_mid_edge_change"] = {"shortcut_stale": g.shortcut[("家", "桂花糕")]["stale"],
                                    "path_steps": len(g.paths[sc["path"]]["steps"])}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
