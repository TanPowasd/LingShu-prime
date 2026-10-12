# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""联想基准：零词面重合合成集（确定性，seed 固定，零模型）。

每个场景 = 题面两条线索 A、X；目标记忆只含 B、Y，与题面在分词后**零重合**（生成时逐题校验，不过即重抽）。
  桥1：A ↔ B        桥2：X ↔ Y        目标：B + Y（金标）
  诱饵：B + Y'、B' + Y、B3 + Y'（各 n_dec 条；B3 是 A 的另一条桥，只吃到一条线索，汇流才能分开）
  另有填充记忆，以及在桥/诱饵/填充里高频出现、但不在目标里的中枢词（「记录」「今天」）。
题型 two_cue（两线索汇流，主集）；one_cue（单线索别名：题面只给 A，目标含 B，无诱饵）。
"""
from __future__ import annotations

import random

from assoc import tokens

POOL = ("岚澜柏桦岫崟珂琚瑾璇琨瑛璋珩玹琮瓒骐骥骁驰麒麟鸾鹤鹭鸥凫鹂莺燕雁鹄鸿"
        "棠桐梓楸槐榆樟楠桂杉柘桧枫楝杏梅桃李柿栗橙橘柚榴荔棣芷蘅蘼芸萱蓁蔚"
        "汀洲渚沚泓涧溪潭漪澈淇沅湘漓泾渭汾洛淮泗沂沭濉颍汝汶浍涡滁岷沱嘉"
        "砚墨笺简牍卷轴琴瑟笙箫筝笛鼓钟磬埙铃螺贝珠玑琳琅瑶琼璞瑕瑜珏玦")
FRAME_BRIDGE1 = ["{A}的搭档是{B}", "{A}平时管{B}叫老伙计", "{A}介绍{B}给大家认识"]
FRAME_BRIDGE2 = ["{X}又叫{Y}", "{X}其实就是{Y}", "人们把{X}称作{Y}"]
FRAME_TARGET = ["{B}上周带着{Y}出了远门", "{B}最近常常提到{Y}", "{B}答应过照看{Y}"]
FRAME_Q2 = ["{A}跟{X}那回怎么样？", "想问{A}与{X}之间发生过什么", "{A}和{X}有啥故事"]
FRAME_Q1 = ["{A}那位老朋友后来如何？", "说说{A}身边那个人"]
HUBS = ["今天记录", "顺便备忘"]


def _words(rng, k):
    seen, out = set(), []
    while len(out) < k:
        w = "".join(rng.sample(POOL, 2))
        if w not in seen and not (set(w) & set("".join(HUBS))):
            seen.add(w); out.append(w)
    return out


def build(n_two=60, n_one=20, n_fill=1000, n_dec=4, seed=13):
    rng = random.Random(seed)
    W = iter(_words(rng, (n_two * (6 + 4 * n_dec) + n_one * 3 + n_fill * 2) * 2))
    mems, qs = [], []

    def add(text, hub):
        if hub:
            text += "，" + rng.choice(HUBS)
        mems.append(text)
        return len(mems) - 1

    def fresh(*avoid):
        while True:
            w = next(W)
            if not any(set(w) & set(a) for a in avoid):
                return w

    while len(qs) < n_two:
        A = next(W); X = fresh(A); B = fresh(A, X); Y = fresh(A, X)
        q = rng.choice(FRAME_Q2).format(A=A, X=X)
        tgt = rng.choice(FRAME_TARGET).format(B=B, Y=Y)
        if tokens(q) & tokens(tgt):
            continue
        add(rng.choice(FRAME_BRIDGE1).format(A=A, B=B), True)
        add(rng.choice(FRAME_BRIDGE2).format(X=X, Y=Y), True)
        g = add(tgt, False)
        B3 = fresh(A, X)                                   # A 的第二个熟人：同一线索的另一条桥，制造歧义
        add(rng.choice(FRAME_BRIDGE1).format(A=A, B=B3), True)
        for _ in range(n_dec):                             # 只吃到一条线索的诱饵
            add(rng.choice(FRAME_TARGET).format(B=B, Y=fresh(A, X)), True)
            add(rng.choice(FRAME_TARGET).format(B=fresh(A, X), Y=Y), True)
            add(rng.choice(FRAME_TARGET).format(B=B3, Y=fresh(A, X)), True)
        qs.append(dict(type="two_cue", q=q, gold=g))
    n1 = 0
    while n1 < n_one:
        A = next(W); B = fresh(A); Z = fresh(A, B)
        q = rng.choice(FRAME_Q1).format(A=A)
        tgt = rng.choice(FRAME_TARGET).format(B=B, Y=Z)
        if tokens(q) & tokens(tgt):
            continue
        add(rng.choice(FRAME_BRIDGE1).format(A=A, B=B), True)
        g = add(tgt, False)
        qs.append(dict(type="one_cue", q=q, gold=g)); n1 += 1
    for _ in range(n_fill):
        a, b = next(W), next(W)
        add(rng.choice(FRAME_TARGET + FRAME_BRIDGE2).format(B=a, Y=b, X=a), rng.random() < .5)
    # 打乱记忆顺序，金标随之重映射（避免「金标总在桥后面」之类位置泄漏）
    order = list(range(len(mems))); rng.shuffle(order)
    pos = {old: new for new, old in enumerate(order)}
    mems = [mems[o] for o in order]
    for x in qs:
        x["gold"] = pos[x["gold"]]
    return mems, qs


def shuffled(mems, seed=7):
    """反面对照：保持每条记忆的词数，把所有词在记忆之间随机重排（打断联想边）。"""
    rng = random.Random(seed)
    toks = [sorted(tokens(m)) for m in mems]
    flat = [t for ts in toks for t in ts]
    rng.shuffle(flat)
    out, i = [], 0
    for ts in toks:
        out.append(" ".join(flat[i:i + len(ts)])); i += len(ts)
    return out
