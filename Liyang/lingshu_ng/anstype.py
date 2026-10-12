# -*- coding: utf-8 -*-
"""v9（PREREG_ZH 修订 7b）：答案类型相容特征 φ(q, p) 与其线性权重（零模型、零依赖）。
「相关但不满足需求」的段落常是题面词都在、却没有题目要的那类信息（问价格却无报价、问步骤却只有介绍）。
φ = 问句类型 one-hot × 段落信息类型 + 题面覆盖度；权重在 T2Ranking 训练侧（Apache-2.0；与评测集问句、段落零重叠）
上按题内成对目标（证据段 > 相关度 1 段，RankNet 思想，Burges et al. 2005）学得，训练脚本 bench_zh/v9/anstype_fit.py。
思想来源：经典问答系统的答案类型匹配（Moldovan et al. 2000；Harabagiu et al. 2000）。"""

import re, math
QT = [("price", r"多少钱|价格|价钱|售价|报价|费用|收费|多钱|几块"), ("num", r"多少|几(个|年|天|岁|米|斤|度|次|种|号|点)|多大|多高|多长|多重|多久|多远|比例|率"),
      ("when", r"什么时候|何时|几月|哪一?年|哪天|日期|时间"), ("where", r"哪里|在哪|哪儿|什么地方|地址|位置|哪个(省|市|国家)"),
      ("how", r"怎么|如何|怎样|方法|步骤|教程|攻略|技巧"), ("why", r"为什么|为何|原因|怎么回事"), ("what", r"是什么|什么意思|指什么|含义|定义|简介|介绍"),
      ("yn", r"吗$|吗\?|能不能|可不可以|是否|会不会|有没有|好不好"), ("who", r"谁|哪位|什么人"), ("which", r"哪个|哪种|哪些|哪家|推荐")]
PT = [("digit", r"\d"), ("money", r"\d+(\.\d+)?\s*(元|块|万|¥|￥|rmb|RMB)|[¥￥]\s*\d"), ("date", r"\d{4}年|\d{1,2}月\d{1,2}日|\d{4}[-/.]\d{1,2}"),
      ("unit", r"\d+(\.\d+)?\s*(%|米|公里|千克|kg|斤|岁|天|小时|分钟|cm|mm|度|℃|个|次|年)"), ("place", r"省|市|区|县|路|街|号楼|镇"),
      ("steps", r"(^|\n|\s)(1[\.、]|一、|第一|首先|步骤)|然后|最后|接着"), ("cause", r"因为|由于|原因|导致|所以|引起"),
      ("def", r"是指|指的是|是一种|是一个|简称|又称|定义"), ("yn", r"可以|不能|不可以|能够|不会|会|是的|不是|没有|有的"), ("price0", r"暂无报价|价格面议|询价|电议"),
      ("list", r"(\n.*){8,}")]
QR = [(k, re.compile(v)) for k, v in QT]; PR = [(k, re.compile(v)) for k, v in PT]
def _bg(s: str) -> set:
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}

def phi(q: str, p: str) -> list:
    """特征向量（长度 DIM）。"""
    qt = [1.0 if r.search(q) else 0.0 for _, r in QR]; pt = [1.0 if r.search(p) else 0.0 for _, r in PR]
    qb = _bg(q); pb = _bg(p); cov = len(qb & pb) / max(1, len(qb))
    # 题面二元组首次出现位置（相对）、密度
    pos = [p.find(b) for b in qb if b in p]; first = min(pos) / max(1, len(p)) if pos else 1.0
    lp = math.log1p(len(p)) / 7.0; nd = min(1.0, len(re.findall(r"\d", p)) / 20.0)
    x = qt + pt + [cov, first, lp, nd] + [a * b for a in qt for b in pt] + [a * cov for a in qt]
    return x
DIM = len(phi("多少钱", "1元"))


def score(q: str, passages) -> list:
    """每段的答案类型相容分 w·z(φ)（越大越像「满足需求」）；权重缺失 → 全 0。"""
    try:
        from .anstype_w import MU, SD, W
    except ImportError:
        return [0.0] * len(passages)
    out = []
    for p in passages:
        x = phi(q, p)
        out.append(sum(w * (a - m) / s for w, a, m, s in zip(W, x, MU, SD)))
    return out
