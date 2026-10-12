# -*- coding: utf-8 -*-
"""speaker · gen r10 F4 说话人意图先验（PREREG_GEN_v3 修订 11 R11.3；默认关）

两件纯标准库的小判别器，只服务 densefuse 的头部重排（只在注入语义模型且 ``sp > 0`` 时被调用）：

- :func:`query_intent`：英文查询指向谁说过的话。
  +1 = 助手（「you recommended / you mentioned / you said / your suggestion …」：第二人称 + 过去式陈述动词，问的是助手先前的话）；
  −1 = 用户（其余含第一人称 I / my / me 的查询：问的是用户自己说过的事、偏好、处境）；0 = 不判（第三人称问句，如 LoCoMo「What did Caroline …」）。
- :func:`doc_speaker`：一条对话轮是谁说的。有通用角色前缀（user/assistant/human/ai/bot/system/me/you + 冒号）直接读；
  否则（W0 无前缀写入）用**伪说话人推断**：只看文本结构特征（长度、列表/markdown 标记、助手式开场与客套、第一人称占比），
  固定规则打分；+1 助手 / −1 用户 / 0 不判。不看写入位置奇偶，不用任何数据集字段。

思想来源：对话记忆基准（LongMemEval，Wu et al., ICLR 2025 的 single-session-user / single-session-assistant 题型区分；
ConvoMem，Salesforce 2025 的 user / assistant 证据类别）显示「问谁说过」决定证据轮的角色；本实现为自研规则，不含其代码。
"""
from __future__ import annotations

import re

__all__ = ["query_intent", "doc_speaker", "has_role"]

_ROLE = re.compile(r"^\s*(user|assistant|human|ai|bot|system|me|you)\s*:\s*", re.I)
_ASSIST_ROLE = {"assistant", "ai", "bot", "system", "you"}

#: 助手指向：第二人称 + 过去式/完成式「说过、推荐过」类动词，或 your + 建议类名词
_Q_ASSIST = re.compile(
    r"\byou(?:'ve| have| had)?\s+(?:\w+ly\s+)?(?:recommended|suggested|mentioned|said|told|gave|given|proposed|listed|shared|"
    r"described|explained|outlined|provided|offered|advised|named|noted|pointed out|came up with|brought up|"
    r"helped me (?:with|come up|pick|choose|find|draft|write)|wrote|drafted|created|put together|laid out|walked me through|"
    r"calculated|estimated|identified|highlighted|showed|shown|included|picked|chose|chosen)\b"
    r"|\byour (?:previous |earlier |last |original )?(?:recommendation|suggestion|advice|list|answer|response|explanation|tip|idea)s?\b",
    re.I)
_Q_FIRST = re.compile(r"\b(?:i|i'm|i've|i'd|i'll|my|me|mine|myself)\b", re.I)

_A_OPEN = re.compile(
    r"^\s*(?:sure|absolutely|of course|certainly|great|good|excellent|that's|that is|that sounds|this is|what a|it's great|"
    r"it sounds|congratulations|happy to|glad|i'm glad|i'm sorry|i understand|i hear you|you're|you are|here(?:'s| is| are)|"
    r"thanks for|thank you for|okay|ok|yes|no problem|wow|oh)\b", re.I)
_A_PHRASE = re.compile(
    r"\b(?:you might|you may want|you could|you can|you should|i recommend|i'd recommend|i would recommend|i suggest|i'd suggest|"
    r"consider|let me know|feel free|hope this helps|here are|here's|keep in mind|it's important to|it's a good idea|"
    r"don't hesitate|good luck|for example|such as)\b", re.I)
_A_LIST = re.compile(r"(?:^|\n)\s*(?:[-*•]|\d+[.)])\s+\S|\*\*[^*\n]+\*\*|(?:^|\n)#{1,4} ")
_U_FIRST = re.compile(r"\b(?:i|i'm|i've|i'd|i'll|my|me|mine|myself|we|we're|our|us)\b", re.I)
_A_SECOND = re.compile(r"\b(?:you|you're|you've|you'd|you'll|your|yours|yourself)\b", re.I)


def has_role(text: str) -> bool:
    """是否带通用角色前缀（user: / assistant: …）。"""
    return bool(text) and _ROLE.match(text) is not None


def query_intent(q: str) -> int:
    """+1 助手 / −1 用户 / 0 不判。"""
    if not q or not q.strip():
        return 0
    if _Q_ASSIST.search(q):
        return 1
    return -1 if _Q_FIRST.search(q) else 0


def doc_speaker(text: str) -> int:
    """+1 助手 / −1 用户 / 0 不判（显式角色前缀优先；否则伪说话人推断）。"""
    if not text:
        return 0
    m = _ROLE.match(text)
    if m:
        return 1 if m.group(1).lower() in _ASSIST_ROLE else -1
    t = text.strip()
    a = u = 0
    n = len(t)
    if n >= 600:
        a += 2
    elif n >= 300:
        a += 1
    elif n < 160:
        u += 1
    if _A_LIST.search(t):
        a += 2
    if _A_OPEN.match(t):
        a += 1
    a += min(2, len(_A_PHRASE.findall(t)))
    a += min(3, len(_A_SECOND.findall(t)))
    u += min(3, len(_U_FIRST.findall(t)))
    d = a - u
    return 1 if d >= 1 else (-1 if d <= -1 else 0)
