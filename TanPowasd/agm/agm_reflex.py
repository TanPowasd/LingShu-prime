"""AGM v0.6 · 关键词神经反射 参考原型（纯标准库，只验证提案 §4D 的行为方向）。

反射弧：感受器（关键词检测）→ 单突触直连 → 效应（直接点亮记忆节点），不经扩散、不等多步传递。
  非条件反射  出厂就有：强调词「记住/重要」→ 抬高写入 salience；否定词「不是/没有」→ 抑制
  条件反射    关键词与某记忆被「一起用上」反复出现 → 长出反射边（Rescorla–Wagner 式习得）
  消退        关键词出现、记忆却没被用上 → 反射边减弱；隔一段时间部分自发恢复
  习惯化      关键词出现得越频繁、越没有后果，反射增益越低（生物学上的 IDF）
  敏化        刚发生过强事件（高 salience），短时间内所有反射增益抬高
用法：python agm_reflex.py → 打印读数（JSON）
"""
from __future__ import annotations

import json
import math

ALPHA = 0.25         # 习得率
EXT = 0.15           # 消退率
RECOVER = 0.4        # 自发恢复：休息后找回被消退掉的那部分的比例
THETA_REFLEX = 0.5   # 反射边超过它才会「直接放电」


class Reflex:
    def __init__(self):
        self.v = {}          # (关键词, 节点) → 反射强度 V
        self.lost = {}       # 被消退掉、可自发恢复的量
        self.seen = {}       # 关键词出现次数（习惯化用）
        self.sens = 0.0      # 敏化水平，随时间衰减

    def gain(self, kw):      # 习惯化：出现越多增益越低，再乘敏化
        n = self.seen.get(kw, 0)
        return (1 / (1 + math.log1p(n))) * (1 + self.sens)

    def trial(self, kw, node, used):
        """一次「关键词出现」：used=该记忆这次是否被用上（无条件刺激 US）。"""
        self.seen[kw] = self.seen.get(kw, 0) + 1
        V = self.v.get((kw, node), 0.0)
        if used:
            V += ALPHA * (1 - V)
        else:
            d = EXT * V
            V -= d
            self.lost[(kw, node)] = self.lost.get((kw, node), 0.0) + d
        self.v[(kw, node)] = V
        return V

    def rest(self, kw, node):    # 一段时间不出现 → 自发恢复
        r = RECOVER * self.lost.pop((kw, node), 0.0)
        self.v[(kw, node)] = self.v.get((kw, node), 0.0) + r
        return self.v[(kw, node)]

    def fire(self, kw, node):
        V = self.v.get((kw, node), 0.0) * self.gain(kw)
        return V if V >= THETA_REFLEX else 0.0


def main():
    R = Reflex()
    acq = [round(R.trial("桂花", "奶奶的院子", True), 3) for _ in range(8)]
    fires_at = next(i + 1 for i, v in enumerate(acq) if v >= THETA_REFLEX)
    ext = [round(R.trial("桂花", "奶奶的院子", False), 3) for _ in range(8)]
    rec = round(R.rest("桂花", "奶奶的院子"), 3)
    relearn = [round(R.trial("桂花", "奶奶的院子", True), 3) for _ in range(2)]

    H = Reflex()
    hab = []
    for n in (0, 1, 5, 20, 100):
        H.seen["的"] = n
        hab.append({"已出现次数": n, "增益": round(H.gain("的"), 3)})

    S = Reflex()
    S.v[("下雨", "带伞")] = 0.6
    base = round(S.fire("下雨", "带伞"), 3)
    S.seen["下雨"] = 3
    habituated = round(S.fire("下雨", "带伞"), 3)
    S.sens = 1.5
    sensitized = round(S.fire("下雨", "带伞"), 3)

    # 时延：反射 1 步直达；扩散要沿链走 L 步（每步一次传递）
    latency = {"反射": 1, "扩散(链长3)": 3, "扩散(链长5)": 5}

    print(json.dumps({
        "条件反射_习得(8次配对)": acq, "第几次起能直接放电": fires_at,
        "消退(8次只出现不用上)": ext, "休息后自发恢复": rec, "再习得2次": relearn,
        "习惯化_增益": hab,
        "敏化": {"基线": base, "习惯化后(已见3次)": habituated, "强事件后敏化(+1.5)": sensitized},
        "时延_传递步数": latency,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
