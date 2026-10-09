"""AGM v0.4 · 脑启发机制 参考原型（纯标准库，只验证提案 §4B 的行为方向，不是神经科学模型）。

六个机制，各给一组读数：
  1 放电阈值      —— 链上一环太弱，激活传不过去（回答「加权强度掩盖薄弱一环」）
  2 稳态突触缩放  —— 抑制赫布的「强者愈强」
  3 睡眠反向重放  —— 从终点倒着重放，长出可用于倒推的反向边
  4 三因子学习    —— 学习量 = 前 × 后 × 调质信号（意外程度）
  5 突触标记捕获  —— 弱记忆先打标记，窗口内有强事件才被固化
  6 模式分离      —— 相似输入经扩张 + 稀疏（k-WTA）编码后重叠变小
用法：python agm_brain.py → 打印读数（JSON）
"""
from __future__ import annotations

import json
import math
import random

rng = random.Random(11)


# 1 放电阈值：a_{t+1} = a_t·w 若 ≥ θ 否则 0（不放电，链断）
def propagate(ws, a0=1.0, theta=0.2):
    a, trace = a0, [a0]
    for w in ws:
        a = a * w
        a = a if a >= theta else 0.0
        trace.append(round(a, 4))
    return trace


def weighted_S(ws):
    return sum(w * w for w in ws) / sum(ws)


# 2 稳态突触缩放：每个节点出边强度总和保持预算 B
def hebb_run(scaling, steps=40, eta=0.3, budget=2.0):
    w = {"热点": 0.5, "a": 0.5, "b": 0.5, "c": 0.5}
    for _ in range(steps):
        w["热点"] += eta * (1 - w["热点"])           # 只有热点被反复共激活
        for k in w:
            w[k] *= 0.995                             # 自然衰退
        if scaling:
            tot = sum(w.values())
            if tot > budget:
                for k in w:
                    w[k] *= budget / tot
    out = {k: round(v, 3) for k, v in w.items()}
    out["出边总和"] = round(sum(w.values()), 3)
    out["热点占比"] = round(w["热点"] / sum(w.values()), 3)
    return out


# 3 睡眠反向重放
def replay_demo():
    fwd, bwd = 1.0, 0.4
    w = {}
    seq = ["出发", "路口", "桥", "目的地"]
    for a, b in zip(seq, seq[1:]):
        w[(a, b)] = fwd * 0.5
        w[(b, a)] = bwd * 0.5
    before = {f"{b}→{a}": round(w[(b, a)], 3) for a, b in zip(seq, seq[1:])}
    rev = list(reversed(seq))
    for _ in range(3):                               # 从终点倒着重放 3 次
        for a, b in zip(rev, rev[1:]):
            w[(a, b)] += 0.2 * (1 - w[(a, b)])
    after = {f"{a}→{b}": round(w[(a, b)], 3) for a, b in zip(rev, rev[1:])}
    back_chain = math.prod(w[(a, b)] for a, b in zip(rev, rev[1:]))
    return {"反向边_重放前": before, "反向边_重放后": after,
            "从目的地倒推到出发的链强度": {"重放前": round(math.prod(before.values()), 4),
                                    "重放后": round(back_chain, 4)}}


# 4 三因子：Δw = η · pre · post · M，M = |实际 − 预期|
def three_factor():
    w, expect = 0.5, 0.5
    out = []
    for outcome in [1, 1, 1, 1, 0, 1]:               # 前四次一样，第五次意外
        M = abs(outcome - expect)
        dw = 0.5 * 1.0 * 1.0 * M * (outcome - w)
        w += dw
        expect += 0.5 * (outcome - expect)
        out.append({"结果": outcome, "意外M": round(M, 3), "Δw": round(dw, 3)})
    return out


# 5 突触标记与捕获：弱记忆打标记（寿命 T），窗口内若有强事件 → 固化
def tag_capture(strong_at, T=3.0, weak_at=0.0):
    tagged = strong_at is not None and 0 <= strong_at - weak_at <= T
    return "固化" if tagged else "随标记消退"


# 6 模式分离：输入 64 维，扩张到 1024 维随机投影 + k-WTA（k=32）
def separation():
    D, H, k = 64, 1024, 32
    P = [[rng.gauss(0, 1) for _ in range(D)] for _ in range(H)]
    base = [rng.gauss(0, 1) for _ in range(D)]

    def code(x):
        h = [sum(p * v for p, v in zip(row, x)) for row in P]
        top = set(sorted(range(H), key=lambda i: -h[i])[:k])
        return top

    def cosv(a, b):
        return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))

    rows = []
    for noise in (0.2, 0.5, 1.0):
        y = [b + rng.gauss(0, noise) for b in base]
        rows.append({"噪声": noise, "输入余弦": round(cosv(base, y), 3),
                     "稀疏码重叠(Jaccard)": round(len(code(base) & code(y)) / len(code(base) | code(y)), 3)})
    return rows


def main():
    strong = [0.9, 0.8, 0.9]
    weak = [0.9, 0.1, 0.9]
    out = {
        "1_放电阈值": {"正常链 激活": propagate(strong), "中间变弱 激活": propagate(weak),
                     "对照 加权强度S": {"正常": round(weighted_S(strong), 4), "中间变弱": round(weighted_S(weak), 4)}},
        "2_稳态缩放": {"无缩放": hebb_run(False), "有缩放(出边总和≤2)": hebb_run(True)},
        "3_反向重放": replay_demo(),
        "4_三因子": three_factor(),
        "5_标记捕获": {"弱记忆后1小时有强事件": tag_capture(1.0), "后5小时才有": tag_capture(5.0),
                     "没有强事件": tag_capture(None)},
        "6_模式分离": separation(),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
