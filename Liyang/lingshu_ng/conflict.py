# -*- coding: utf-8 -*-
"""conflict · 写入期轻量矛盾检测（零 LLM）

旧设计（Q6，见 :mod:`lingshu_ng.retrieval`）：已登记的矛盾（OPPOSITE 边）随检索结果一起交付，
「聚焦检索丢失矛盾另一侧」由此关闭。但登记只能经 ``register_conflict`` 手工落账——生产写入路径
``add_perception`` 从不登记，作者基准（hive-memory-bench）里的写入因此一条矛盾边都没有。

本模块在写入（去重路径）时对**同一事物的两条短记载**做一次廉价判定：

  C1 候选：新文本里 df 最小（已存在于库中、最稀有）的至多 :data:`TOP_TERMS` 个二元组（累计倒排行数
     ≤ :data:`ROW_BUDGET`，与库规模无关），其倒排里共享 ≥ :data:`MIN_SHARED` 个的既有节点，
     按 Σ1/df 取前 :data:`NCAND` 个（长度不可比的先剔除）。df 复用去重探针刚算过的值，倒排一条语句读完。
  C2 对齐：两侧规范化正文（各 ≤ :data:`MAX_CHARS` 字）做序列对齐，相似度 ≥ :data:`MIN_RATIO`，
     且不同之处至多 :data:`MAX_SLOTS` 段——「已知命题里换了一个槽位」（novelty 的「改槽」同一概念）。
     多处不同（模板化的不同事件：编号、状态都不同）不算矛盾；不同处含编号（≥4 位数字、字母数字码、「第 N」）
     说明是不同的事物，也不算。
  C3 冲突类别（在不同之处上判定，任一成立即登记）：
       negation 一侧不同处含否定词、另一侧不含；number 两侧不同处都含数值且不同（只有数值不同时须只此一处）；
       time 时间词不同；state 状态/变更词出现在不同处。只换主体（张三→李四）不是矛盾。
  C4 取代：新文本不同处（或全文）含变更词（改为/调整为/不再/推迟到…）而旧文本不含 ⇒ 旧侧被取代，
     边记 ``auto_supersede``（source=新、target=旧），召回时旧侧降权（仍作为矛盾另一侧随交付）。
登记：OPPOSITE 边，confidence = :data:`AUTO_CONFIDENCE`、未验证，``source_evidence`` 为
``auto_conflict`` / ``auto_supersede``（与手工登记区分；不加 conflict 标签，不改节点内容与签名）。
长段落（> MAX_CHARS）不做判定：两段长叙述之间的「同一事物两处记载」词面上几乎不重叠，
零 LLM 无可靠信号（实测见 evalsuite_hard/hmbq/ITER_HMBQ.md）。
"""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .dedup import _NEG, normalize

__all__ = ["Verdict", "classify", "rare_terms", "AUTO_CONFLICT", "AUTO_SUPERSEDE", "is_auto",
           "MAX_CHARS", "TOP_TERMS", "ROW_BUDGET", "MIN_SHARED", "NCAND", "MIN_RATIO", "MAX_SLOTS"]

#: 参与判定的文本长度上限（规范化后字符数）
MAX_CHARS = 240
#: 候选展开用的稀有二元组个数
TOP_TERMS = 8
#: 候选展开读取的倒排行数上限（累计 df；读取量与库规模无关）
ROW_BUDGET = 512
#: 候选须共享的稀有二元组下限
MIN_SHARED = 2
#: 每次写入最多对齐的候选数
NCAND = 8
#: 对齐相似度下限
MIN_RATIO = 0.6
#: 不同之处的段数上限
MAX_SLOTS = 3
#: 自动登记边的置信度（手工 register_conflict 为 0.3）
AUTO_CONFIDENCE = 0.2
AUTO_CONFLICT = "auto_conflict"
AUTO_SUPERSEDE = "auto_supersede"

_CN = "零〇一二两三四五六七八九十百千万亿"
#: 数值（作「值」用的数）：阿拉伯数字或中文数字，后接量词/单位，或前接「是/为/到/达/约…」；
#: 光秃秃的编号（「访客甲3」「张三」）不算值
_UNIT = r"(?:[级点号个元岁楼层次度年月日时分秒天周名位条项米倍成份件台辆张本人户%％]|公里|公斤|千克|小时|分钟|万|亿)"
_NUM = re.compile(rf"(?:\d+(?:\.\d+)?|[{_CN}]+)(?={_UNIT})|(?<=[是为到至达约共计有])(?:\d+(?:\.\d+)?|[{_CN}]{{2,}})")
#: 标识符样的编号（≥4 位数字且不是年份）：不同之处含编号 ⇒ 说的是不同的事物，不是矛盾
_IDENT = re.compile(rf"\d{{4,}}(?!年)|[a-z]+\d+|\d+[a-z]+|第(?:\d+|[{_CN}]+)")
#: 不同之处之间相隔不超过此字数的视为同一槽位
SLOT_GAP = 1
#: 一处不同去掉线索词后允许剩下的字数（超过 ⇒ 换了主体/属性，不是值的变化）
FILLER = 2
_NUMANY = re.compile(rf"(?:\d+(?:\.\d+)?|[{_CN}]+){_UNIT}?")
_FILL = re.compile(r"[是为到至在于成了的]")
_TIME = re.compile(r"昨天|今天|明天|前天|后天|以前|之前|之后|以后|现在|如今|目前|曾经|当年|后来|当时|原来|本来|"
                   r"上午|下午|晚上|早上|凌晨|中午|周[一二三四五六日天]|星期[一二三四五六日天]|"
                   r"\d+(?:年|月|日|号|点|时|分)|[一二三四五六七八九十]+(?:年|月|日|号|点|时)")
_STATE = re.compile(r"已经|已|不再|仍然|依然|仍|还是|变成|变为|成为|改为|改成|改到|调整|推迟|提前|取消|恢复|"
                    r"去世|死亡|活着|开始|结束|停止|暂停|关闭|开放|升级|提升|降级|降为|升为|更换|换成|迁至|搬到|撤销|废除|生效|失效")
_UPDATE = re.compile(r"改为|改成|改到|调整为|调整到|调整成|更换为|更换成|换成|变为|变成|不再|推迟到|推迟至|提前到|提前至|"
                     r"提升为|升为|降为|迁至|迁到|搬到|已经|已改|现在是|如今|目前是|更新为")


def is_auto(evidence: Optional[str]) -> bool:
    """边是否为写入期自动登记（区别于手工 register_conflict）。"""
    return bool(evidence) and str(evidence).startswith("auto_")


def rare_terms(dfs: Dict[str, int], top: int = TOP_TERMS, budget: int = ROW_BUDGET) -> List[Tuple[int, str]]:
    """C1：已存在于库中（df ≥ 1）的二元组按 (df, 词元) 升序，至多 top 个、累计 df（= 要读的倒排行数）
    不超过 budget：[(df, 词元)]。读取量因此与库规模无关。"""
    out: List[Tuple[int, str]] = []
    rows = 0
    for d, t in sorted((d, t) for t, d in dfs.items() if d > 0):
        if len(out) >= top or rows + d > budget:
            break
        out.append((d, t))
        rows += d
    return out


def score_candidates(rows: Iterable[Tuple[str, int, int]], df: Dict[str, int], grams: int) -> List[Tuple[float, int]]:
    """C1：倒排行 (词元, nkey, 正文二元组数) → 共享 ≥ MIN_SHARED、长度可比的节点按 Σ1/df 降序：
    [(分, nkey)]，至多 NCAND 个。长度比（二元组数）低于 MIN_RATIO 的不可能对齐达标，先剔除（免回表）。"""
    sc: Dict[int, float] = {}
    cnt: Dict[int, int] = {}
    for t, k, g in rows:
        if not g or min(g, grams) < MIN_RATIO * max(g, grams):
            continue
        sc[k] = sc.get(k, 0.0) + 1.0 / max(1, df.get(t, 1))
        cnt[k] = cnt.get(k, 0) + 1
    out = sorted(((s, k) for k, s in sc.items() if cnt[k] >= MIN_SHARED), key=lambda x: (-x[0], x[1]))
    return out[:NCAND]


class Verdict(tuple):
    """判定结果：(类别元组, 新侧是否取代旧侧)。"""

    __slots__ = ()

    def __new__(cls, kinds: Sequence[str], supersede: bool):
        return super().__new__(cls, (tuple(kinds), bool(supersede)))

    @property
    def kinds(self) -> Tuple[str, ...]:
        """冲突类别（negation / number / time / state 的子集，按发现顺序）。"""
        return self[0]

    @property
    def supersede(self) -> bool:
        """新侧是否取代旧侧（新侧含变更词而旧侧不含）。"""
        return self[1]


def _diffs(a: str, b: str) -> Tuple[float, List[Tuple[int, int, int, int]]]:
    """对齐相似度 + 逐处不同（未合并）：[(i1, i2, j1, j2)]。"""
    sm = SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < MIN_RATIO or sm.quick_ratio() < MIN_RATIO:
        return 0.0, []                                 # 上界已不达标（字符多重集交），免做完整对齐
    return sm.ratio(), [(i1, i2, j1, j2) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]


def _merge(spans: List[Tuple[int, int, int, int]]) -> List[List[int]]:
    """相隔 ≤ SLOT_GAP 字的不同之处合并为一个槽位。"""
    out: List[List[int]] = []
    for i1, i2, j1, j2 in spans:
        if out and i1 - out[-1][1] <= SLOT_GAP and j1 - out[-1][3] <= SLOT_GAP:
            out[-1][1], out[-1][3] = i2, j2
        else:
            out.append([i1, i2, j1, j2])
    return out


def _context(s: str, i1: int, i2: int, w: int = 2) -> str:
    """不同之处 s[i1:i2] 两侧各带 w 字（「九点」被切成「九」与「点」、「7项→75项」只插入「5」时仍能认出）。"""
    return s[max(0, i1 - w):i2 + w]


def _residue(x: str) -> str:
    """去掉全部冲突线索词（否定/数值/单位/时间/状态/系词）后剩下的字。"""
    for rx in (_STATE, _TIME, _NEG, _NUMANY, _FILL):
        x = rx.sub("", x)
    return x


def _slot_kind(x: str, y: str, cx: str, cy: str) -> Optional[List[str]]:
    """一处不同的冲突类别（x/y 为两侧片段，cx/cy 带上下文）。
    返回 [] = 无线索的短填充（≤ FILLER 字，如「上午/下午」被切开的半边、「阶段」）；
    返回 None = 不是值的变化（去掉线索词后仍有较长的不同——换了主体或属性）。
    否定只认「去掉否定词后两侧相同」（「不由」对「由」；实体名里的「无」字不算）。"""
    if len(_residue(x)) > FILLER or len(_residue(y)) > FILLER:
        return None
    out: List[str] = []
    nx, ny = _NEG.sub("", x), _NEG.sub("", y)
    if (nx != x or ny != y) and nx == ny:
        out.append("negation")
    na, nb = _NUM.findall(cx), _NUM.findall(cy)
    if na and nb and na != nb:
        out.append("number")
    ta, tb = _TIME.findall(cx), _TIME.findall(cy)
    if (ta or tb) and ta != tb:
        out.append("time")
    if _STATE.search(x) or _STATE.search(y):
        out.append("state")
    return out


def classify(new_text: str, old_text: str) -> Optional[Verdict]:
    """C2–C4：两条记载是否为同一事物上的矛盾；不是返回 None。纯函数。"""
    a, b = normalize(new_text), normalize(old_text)
    if not a or not b or a == b or len(a) > MAX_CHARS or len(b) > MAX_CHARS:
        return None
    if min(len(a), len(b)) / max(len(a), len(b)) < MIN_RATIO:
        return None                                    # ratio ≤ 2·min/(min+max)，长度悬殊不可能达标
    ratio, raw = _diffs(a, b)
    if ratio < MIN_RATIO or not raw:
        return None
    kinds: List[str] = []
    for i1, i2, j1, j2 in raw:
        x, y = a[i1:i2], b[j1:j2]
        k = _slot_kind(x, y, _context(a, i1, i2), _context(b, j1, j2))
        if k is None:
            return None                                # 有一处不同不是值的变化（换了主体/属性）⇒ 不是同一事物
        kinds.extend(k)
    slots = _merge(raw)
    if not kinds or len(slots) > MAX_SLOTS:
        return None
    da = "|".join(_context(a, i1, i2) for i1, i2, _, _ in slots)
    db = "|".join(_context(b, j1, j2) for _, _, j1, j2 in slots)
    if _IDENT.search(da) or _IDENT.search(db):
        return None
    kinds = list(dict.fromkeys(kinds))
    if kinds == ["number"] and len(slots) > 1:
        return None                                    # 只有数值不同且不止一处：更像不同编号的同模板记载
    sup = bool(_UPDATE.search(da) or _UPDATE.search(a)) and not _UPDATE.search(b)
    return Verdict(kinds, sup)
