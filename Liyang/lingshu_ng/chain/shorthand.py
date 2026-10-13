# -*- coding: utf-8 -*-
"""速记体 / 中英夹杂版本事件抽取（chain-r10 · v10 · 零 LLM · 写入期）。

严格句式表认不出、且句子带「速记信号」（英文变更动词、箭头、冒号字段写法、方括号标签、TBD/pending 等）时，
先把句子**规范化**成「主体 · 属性 · 动作 · 值 · 起因」五段再登记，最后做一遍**抽取后自检**。认的写法举例：
  「流明项目：依赖名 switch 到 rocksdb（线上故障复盘）。」      set
  「[变更] 织女项目·缓存模块 有效期秒数: 1h，reason: 灰度观测。」  set（值按属性单位归一为 3600）
  「Updated 流明项目's 配置值 to batch_size: 64 due to 代码评审意见。」 set（键值对齐为 batch_size=64）
  「沈砚 mv → 粮仓。」 / 「杜衡 location 定 pin 在 祠堂。」           set（属性＝位置）
  「织女项目：有效期秒数 deprecate，no value retained。」             retire
  「陆平 位置 两个值并存：祠堂 与 驿站，TBD pending。」              unresolve
  「流明项目·同名者: 配置值 pin 为 batch_size=128，争议定案。」       resolve

四步（思想来源见下，均为自研实现）：
  1. 规范化：去方括号标签/引号/全半角差异，起因片段（括注、因/reason:/due to/…导致）先剥离；
  2. 切分：在第一个变更动词（中英、箭头）处把句子切成「头（主体+属性）」与「尾（值）」；英文动词在句首时按
     「Verb S('s|的) A to V」切；没有动词、只有「S A: V」字段写法时把冒号当赋值；
  3. 归一与字段对齐：千分位去逗号、属性名带时间单位（秒/分钟/小时/天/毫秒）时把值的单位换算到属性单位；
     「key: 16 / key = 16 / key 16」对齐为 key=16；英文属性名 location/position/place → 位置；
  4. 自检：主体/属性/原始值须逐字出现在原句，主体、属性、值的字符形态与黑名单检查，值不得是动词或起因，
     主体≠属性≠值；任一不过即放弃本句（宁漏勿错，交给宽松抽取/锚定）。
参考的开源思想（只学思路，不含其代码）：Graphiti/Zep 把事实写成带有效期的实体-属性边、先抽取再做「边是否成立」的
校验；mem0 的「新事实对旧记忆是 ADD/UPDATE/DELETE/NOOP」判定（本模块的 set/retire/unresolve/resolve 四动作）；
A-Mem 写入时把笔记规范化成结构化字段。
不含任何特定语料的实体/属性/值词表；只含通用的中英变更动词、单位与标签词。
开关：环境变量 LINGSHU_NG_CHAIN_SHORT=0 关闭（关闭时与 v9 逐事件相同）。"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

SHORT = os.environ.get("LINGSHU_NG_CHAIN_SHORT", "1").strip().lower() not in ("0", "false", "no", "off")

_CJK = r"\u4e00-\u9fff"
_QUOTES = str.maketrans({"「": " ", "」": " ", "『": " ", "』": " ", "“": " ", "”": " ", "\"": " ", "‘": "'", "’": "'",
                         "*": "", "＊": "", "`": " ", "：": ":", "，": ",", "；": ";", "（": "(", "）": ")",
                         "【": "[", "】": "]", "＝": "=", "　": " ", "⇒": "→", "➡": "→", "⟶": "→"})
_EN_VERB = (r"set(?:s|ting)?|switch(?:ed|es)?|bump(?:ed|s)?|update[ds]?|upd|pin(?:ned|s)?|move[ds]?|mv|change[ds]?|chg|"
            r"roll(?:ed)?\s*back|rollback|revert(?:ed|s)?|upgrade[ds]?|downgrade[ds]?|migrate[ds]?|replace[ds]?|swap(?:ped)?|"
            r"flip(?:ped)?|reset|lock(?:ed)?|fix(?:ed)?|adopt(?:ed)?|configured|modif(?:y|ied)|init(?:ialized)?|relocate[ds]?|"
            r"transfer(?:red)?|shift(?:ed|s)?|turn(?:ed|s)?|decided|made|revise[ds]?|alter(?:ed)?|amend(?:ed)?|became|becomes|goes|went|now|is\s+now|decided|finali[sz]ed|settled|resolved|confirmed|"
            r"assigned|settle[ds]?|changed\s+over|use[ds]?|using|default(?:ed)?|defined|established|initial(?:ly)?|first")
_ZH_VERB = (r"尘埃落定|裁定为|裁定|已定|定稿|初定|先定|拍板为|定下了|定下|改成了|改成|改为|改到|改用|改|切换到|切换为|切换成|切到|切成|切|换成|换到|换为|换|升到|升至|升|降到|降至|降|"
            r"设为|设成|设置为|设定为|设|定为|定在|定成|定了|定|锁定为|锁定在|锁定|锁|更新为|更新到|更新|变更为|变更到|变成|变为|"
            r"迁到|迁至|迁往|搬到|搬去|搬进|移到|移至|挪到|挪去|调到|调至|调为|调成|调|落地|落定|初值|初始值|首定|拍板|定案|回滚到|回滚至|回滚")
_ARROW = r"->|=>|→|>>"
_ZH_ONE = r"改|切|换|升|降|设|定|锁|调|转"
_VERB_RE = re.compile(r"(?:(?<![A-Za-z_])(?:" + _EN_VERB + r")(?![A-Za-z_])|(?:(?<=[\s:,\]])|^)(?:" + _ZH_VERB.replace("|改|", "|").replace("|切|", "|")
                      .replace("|换|", "|").replace("|升|", "|").replace("|降|", "|").replace("|设|", "|").replace("|定|", "|")
                      .replace("|锁|", "|").replace("|调|", "|") + r")(?:(?<=[为到成至在了下往])|(?=[\s:,(\[A-Za-z0-9_]|$))|(?:(?<=[\s:,\]])|^)(?:" + _ZH_ONE + r")(?=\s|[为到成在了下]|$)|" + _ARROW + ")", re.I)
_CONN = re.compile(r"^\s*(?:(?:to|into|as|at|in|from\s+\S+\s+to|初版|首版|初始|起初|最初|最终|后来|是|->|=>|→|>>|=|:|到了|到|为|成|至|在|初值|初始值|新值|值|value|new|now|"
                   r"again|over|成为|改为|定为|设为|(?<![A-Za-z_])(?:" + _EN_VERB + r")(?![A-Za-z_])|" + _ZH_VERB + r")\s*)+", re.I)
_MOVE_VERB = re.compile(r"^(?:move[ds]?|mv|relocate[ds]?|transfer(?:red)?|went|goes|迁到|迁至|迁往|搬到|搬去|搬进|移到|移至|挪到|挪去|→|->|=>|>>)$", re.I)
_LOC_ATTR = re.compile(r"^(?:location|loc|position|place|where|pos|位置|地点|所在地|所在)$", re.I)
_RETIRE = re.compile(r"(?<![A-Za-z_])(?:no\s+longer|deprecated?|deprecating|drop(?:ped|s)?|removed?|rm|deleted?|retired?|unset|cleared?|"
                     r"n/a|null|none|no\s+value(?:\s+retained|\s+kept)?|revoked?|cancel(?:l?ed)?|disabled?|dead)(?![A-Za-z_])|"
                     r"不再保留|不再有|不再留|不留值|不保留|清空|作废|废弃|废止|撤掉|撤了|撤销|撤除|撤|移除|删除|删掉|下线|取消|弃用|停用|置空|无值|没值|失效", re.I)
_UNRES = re.compile(r"(?<![A-Za-z_])(?:tbd|pending|undecided|unresolved|coexisting|co-existing|not\s+(?:yet\s+)?decided|no\s+decision)(?![A-Za-z_])|"
                    r"并存|两个值|两种值|两值|俩值|两个\s*value|待定|未定|待议|未决|尚未|还没定|没定|悬而未决|二选一", re.I)
_RESOLVE = re.compile(r"(?<![A-Za-z_])(?:dispute[ds]?|settle[ds]?|resolved|final(?:i[sz]e[ds]?)?|verdict|ruling)(?![A-Za-z_])|"
                      r"争议|分歧|裁定|定案|落定|拍板|定论|一锤定音|仲裁", re.I)
_RESOLVE_STRONG = re.compile(r"(?i)(?<![A-Za-z_])(?:settle[ds]?|resolved|final(?:i[sz]e[ds]?)?|verdict|ruling)(?![A-Za-z_])|裁定|定案|落定|拍板|定论|一锤定音|仲裁")
_PRE = re.compile(r"[A-Za-z:：→\[【=「『]|[\u4e00-\u9fff」』]\s+[\u4e00-\u9fff「『]")
_MSG_PREFIX = re.compile(r"(?i)^(?:@\S+|(?:fyi|update|upd|sync|cc|ps|note|heads\s*up|btw)(?![A-Za-z_])|"
                         r"(?:今早|今天|昨天|昨晚|早上|上午|中午|下午|晚上|今晚|刚刚|刚才|方才|补充|备注|提醒|同步)(?:同步|更新|说一下|说下|一下|下)?(?=[\s,:：，]))"
                         r"\s*[,:：，]?\s*")
_GLUE_VERB = r"改成了|改成|改为|改到|换成了|换成|换为|定成了|定成|定为|设为|设成|挪到|迁到|搬到|切到|更新为|变成了|变成|变为|定下了|定下|拍板定成|拍板"
_CAUSE_HEAD = re.compile(r"^\s*(?:reason|cause|why|rationale|because\s+of|because|due\s+to|owing\s+to|thanks\s+to|caused\s+by|as\s+a\s+result\s+of|as\s+required\s+by|as\s+per|"
                         r"(?:and\s+)?(?:this\s+is\s+|it\s+is\s+)?due\s+to|in\s+response\s+to|b/c|per|after|following|triggered\s+by|"
                         r"driven\s+by|based\s+on|起因是|起因|因着|原因是|原因|缘由|因为|因|由于|出于|鉴于|根据|基于|源于|缘于|来自|据)\s*[:=]?\s*", re.I)
_CAUSE_TAIL = re.compile(r"\s*(?:(?:导致|所致|引起|引发|触发|驱动|带来|带出来|促成|推动|造成|提出|之故|而起|使然)(?:的)?(?:了)?|(?:拍板|定下|决定|拍)的)\s*$")
_CAUSE_INLINE = re.compile(r"\s+(?:(?:and\s+)?(?:this\s+is\s+|it\s+is\s+|all\s+)?(?:due\s+to|because\s+of|owing\s+to|thanks\s+to|as\s+a\s+result\s+of|as\s+required\s+by|"
                           r"as\s+per|in\s+response\s+to|caused\s+by)|because|b/c|per|after|following|triggered\s+by|driven\s+by|based\s+on|reason\s*:)\s+"
                           r"(?=[^\s]*[" + _CJK + r"])", re.I)
_TAG = re.compile(r"^\s*(?:\[[^\]]{1,16}\]|#[A-Za-z" + _CJK + r"_\-]{1,12}\s|[-*•>]+\s+|\d+[.)、]\s*|"
                  r"(?:fix|feat|chore|refactor|docs|ops|update|upd|chg|change|changelog|note|log|cfg|config|wip|done|ok|fyi|sync)\s*(?:\([^)]{0,16}\))?\s*:\s*)", re.I)
_TAG_WORDS = re.compile(r"^(?:变更|更新|修复|调整|同步|通知|记录|备注|状态|进度|决议|决定|结论|公告|日志|工单|交接|提醒|变动|配置变更|字段变更|"
                        r"定|裁定|定案|撤销|作废|废弃|未决|待定|并存|搬迁|迁移|移动|新增|初始|初始化|首定|首次|创建|新建|删除|"
                        r"fix|feat|chore|change|changes|changelog|update|upd|chg|mv|rm|set|init|new|note|log|ops|wip|done|ok|fyi|sync|jira|ticket|todo|tbd|"
                        r"resolved?|settled?|deprecated?|removed?|pending|moved?)$", re.I)
_TRAIL = re.compile(r"(?:\s+(?:now|again|done|ok|already|for\s+now|asap|init|initial|new|✅|✔)|了|啦|吧|呢|哈|的|咯|嘛|呀|啊|喽|哦|呗)+\s*$", re.I)
_BAD_ENT = re.compile(r"^(?:我|你|他|她|它|我们|你们|他们|大家|这|那|这个|那个|此|其|本|该|有人|谁|什么|怎么|如果|但是|然后|所以|因为|"
                      r"已经|现在|目前|今天|昨天|明天|之前|之后|later|then|so|and|but|we|i|you|he|she|it|they|this|that|the|a|an)$", re.I)
_ENT_OK = re.compile(r"^[" + _CJK + r"A-Za-z0-9_·\-./]{1,24}$")
_ATTR_OK = re.compile(r"^[" + _CJK + r"A-Za-z_]{1,12}$")
_HAS_CJK = re.compile(r"[" + _CJK + r"]")
_KV = re.compile(r"^(?P<k>[A-Za-z_][A-Za-z0-9_]*)\s*(?:=|:|\s)\s*(?P<n>[\d,]+(?:\.\d+)?)$")
_NUM_UNIT = re.compile(r"^(?P<n>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<f>\d+))?\s*(?P<u>ms|msec|毫秒|s|sec|secs|seconds?|秒|m|min|mins|minutes?|分钟|分|"
                       r"h|hr|hrs|hours?|小时|d|days?|天)?$", re.I)
_UNIT_SEC = {"ms": 0.001, "msec": 0.001, "毫秒": 0.001, "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "秒": 1,
             "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "分钟": 60, "分": 60,
             "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "小时": 3600, "d": 86400, "day": 86400, "days": 86400, "天": 86400}
_ATTR_UNIT = (("毫秒", 0.001), ("秒", 1), ("分钟", 60), ("小时", 3600), ("天数", 86400))
#: 速记信号：没有这些信号的句子不走本模块（散文交给宽松抽取，免得把叙述当变更）
_CUE = re.compile(r"(?<![A-Za-z_])(?:" + _EN_VERB + r"|deprecated?|drop(?:ped)?|removed?|rm|tbd|pending|n/a|unset|revoked?|retired?|deleted?|cleared?|coexist(?:ing|s)?|no\s+longer)(?![A-Za-z_])|"
                  r"->|=>|→|>>|^\s*\[|^[^:]{1,30}:|[" + _CJK + r"]\s+[" + _CJK + r"A-Za-z][^\s]*\s+[" + _CJK + r"]|(?<=[" + _CJK + r"A-Za-z0-9)])\s+[" + _CJK + r"]{2,12}\s*:", re.I)


_STRONG = re.compile(r"(?<![A-Za-z_])(?:" + _EN_VERB + r"|deprecated?|drop(?:ped)?|removed?|rm|tbd|pending|n/a|unset|revoked?|retired?|deleted?|cleared?|coexist(?:ing|s)?|no\s+longer)(?![A-Za-z_])|"
                     r"->|=>|→|>>|^\s*[\[【]|^[^:：，,]{1,30}[:：]", re.I)


_EXPL_CAUSE_W = re.compile(r"(?i)(?<![A-Za-z_])(?:reason|cause|because|due\s+to|b/c)(?![A-Za-z_])|起因|原因|因为|因|由于|导致|所致")
TAGGED = [False]
MOVETAG = [False]
NORM = [""]
TAGS = [""]
_EXPL_CAUSE = re.compile(r"(?i)(?<![A-Za-z_])(?:reason|cause|because|due\s+to|b/c)(?![A-Za-z_])|起因|原因|因为|因|由于|导致|所致|[（(][^）)]*[" + _CJK + r"]")


def strong_cue(sent: str) -> bool:
    """强速记信号（英文变更动词、箭头、方括号标签、句首字段冒号）：有则先走本模块，否则先让宽松抽取试。"""
    return bool(_STRONG.search(sent))


_EN_FILL = re.compile(r"(?i)(?<![A-Za-z_])(?:the|was|were|has\s+been|have\s+been|had\s+been|has\s+its|have\s+its|is|are|been|gets|got|"
                      r"currently|officially|now\s+officially|for\s+the\s+first\s+time|at\s+first|initially|finally|eventually|ultimately)(?![A-Za-z_'])")


def _en_norm(t: str) -> Tuple[str, bool]:
    """英文句式框架归一：「For S, the A was changed to V」→「S 的 A changed to V」；冠词/助动词/时间副词去掉。返回 (句子, 是否带首次信号)。"""
    first = bool(re.search(r"(?i)for\s+the\s+first\s+time|\bat\s+first\b|\binitially\b|\bfirst\s+(?:set|defined|established)", t))
    m = re.match(r"(?i)^\s*(?:for|regarding|re|on)\s+(?P<s>[^,，]+?)\s*,\s*(?P<r>.+)$", t)
    if m and _HAS_CJK.search(m.group("s")):
        t = m.group("s") + " 的 " + m.group("r")
    if re.search(r"[A-Za-z]{2,}", t):
        t = re.sub(r"(?i)^\s*(?:after|following)\s+(?:the\s+)?(?:dispute|debate|disagreement)\s*,\s*", "dispute settled , ", t)
        t = re.sub(r"(?i)(?<![A-Za-z_])(?:the\s+)?(?:dispute|debate|disagreement)\s+(?:over|on|about|regarding)\s+", "", t) + (" , dispute settled" if re.search(r"(?i)dispute\s+(?:over|on|about|regarding)", t) else "")
        t = _EN_FILL.sub(" ", t)
        t = re.sub(r"(?i)(?<![A-Za-z_])(?:has|have|had)(?:\s+(?:its|their))?(?=\s+[A-Za-z" + _CJK + r"])", " ", t)
        t = re.sub(r"(?i)(?<![A-Za-z_])(?:since|from\s+then\s+on|thereafter|subsequently)(?![A-Za-z_])", " ", t)
        t = re.sub(r"(?i)(?<![A-Za-z_])(?:of|for)\s+(?=[" + _CJK + r"])", " of ", t)
    return re.sub(r"\s+", " ", t).strip(), first


def _strip_cause(t: str) -> Tuple[str, Optional[str]]:
    """剥离起因片段，返回 (主干, 起因)。括注（非标识符后紧跟的、含中文的括号）与起因分句都算。"""
    reason = None
    def paren(m):
        nonlocal reason
        inner = m.group(1).strip()
        r = _CAUSE_HEAD.sub("", inner).strip()
        if reason is None and r:
            reason = r
        return " , "
    t = re.sub(r"\s*\(([^()]*[" + _CJK + r"][^()]*)\)", paren, t)
    t = re.sub(r"(?:(?<=[\s" + _CJK + r"])|^)\(\s*[A-Za-z][A-Za-z ]{0,24}\)", " ", t)
    t = re.sub(r"\(\s*(?:=|≈|~|i\.e\.?|aka|即|约|也就是)\s*[^()]{1,16}\)", " ", t)                 # 「7200（=2h）」等值注释
    t = re.sub(r"(?<=[\dsmhd])\s*\(\s*\d+(?:\.\d+)?\s*(?:ms|s|sec|secs|seconds?|min|mins|minutes?|h|hr|hrs|hours?|d|days?|秒|分钟|小时|天)\s*\)", "", t)   # 「10800（3h）」          # 非标识符后的纯英文括注（first time）
    t = re.sub(r"\s*:\s*(?=(?:reason|cause|because|due\s+to)\b|起因|原因|因为|因|由于|鉴于|根据|基于|依据)", " , ", t, flags=re.I)
    t = re.sub(r"\(([^()]*)\)", lambda m: "(" + m.group(1).replace(",", "\x01") + ")", t)   # 标识符括号里的逗号（签名参数）先保护
    m = _CAUSE_INLINE.search(t)
    if m:
        rest = t[m.end():]
        reason = reason or re.split(r"[,;]", rest)[0].strip()
        t = t[:m.start()] + " , " + rest.split(",", 1)[1] if "," in rest else t[:m.start()]
    parts = [p.strip() for p in re.split(r"[,;]|\s\|\s", t)]
    keep = []
    for k, p in enumerate(parts):
        if not p:
            continue
        if (k > 0 or len(parts) > 1) and (_CAUSE_HEAD.match(p) and _CAUSE_HEAD.sub("", p) != p or _CAUSE_TAIL.search(p)):
            reason = reason or _CAUSE_TAIL.sub("", _CAUSE_HEAD.sub("", p)).strip()
            continue
        keep.append(p)
    return " , ".join(keep), reason


_ADV_TAIL = re.compile(r"(?:\s*(?:首次|首度|初次|第一次|最初|起初|初始|最终|最后|终于|现在|如今|目前|之后|此后|后来|现|已|已经|再次|重新|正式|直接|"
                       r"initially|initial|first|finally|now|again|officially))+\s*$", re.I)


_ADV_HEAD = re.compile(r"^\s*(?:(?:首次|初次|第一次|最初|起初|最终|最后|现在|如今|目前|initial|first|final)\s*)+", re.I)


def _clean_tok(x: str) -> str:
    x = re.sub(r"\s+", " ", x).strip(" ,:;=-|")
    x = _ADV_HEAD.sub("", x).strip(" ,:;=-|")
    x = _ADV_TAIL.sub("", x).strip(" ,:;=-|")
    x = re.sub(r"(?:'s|’s)$", "", x).strip()
    return re.sub(r"的$", "", x).strip()


def _split_head(head: str) -> Tuple[Optional[str], Optional[str]]:
    """头 → (主体, 属性)；属性缺省返回 None。"""
    h = _clean_tok(head)
    if not h:
        return None, None
    m = re.match(r"^(?P<s>.+?)\s*(?:'s|’s)\s+(?P<a>.+)$", h)
    if m:
        return _clean_tok(m.group("s")), _clean_tok(m.group("a"))
    m = re.match(r"^(?P<a>[" + _CJK + r"A-Za-z_]{1,12})\s+(?:of|for)\s+(?P<s>.+)$", h, re.I)
    if m:
        return _clean_tok(m.group("s")), _clean_tok(m.group("a"))
    if ":" in h:
        s, a = h.split(":", 1)
        return _clean_tok(s), (_clean_tok(a) or None)
    if "的" in h:
        s, a = h.split("的", 1)
        return _clean_tok(s), (_clean_tok(a) or None)
    toks = h.split()
    if len(toks) == 1:
        return toks[0], None
    return toks[0], _clean_tok(" ".join(toks[1:]))


def _attr_unit(attr: Optional[str]) -> Optional[float]:
    for w, u in _ATTR_UNIT:
        if attr and w in attr:
            return u
    return None


def norm_value(v: str, attr: Optional[str]) -> str:
    """数值/单位/键值对归一（字段对齐）。不认的写法原样返回。"""
    v = v.strip()
    parts = [p.strip() for p in re.split(r"\s*(?:[(/]|\bor\b|或)\s*", v.rstrip(")").strip()) if p.strip()]
    if len(parts) == 2 and all(_NUM_UNIT.match(p) for p in parts):
        nv = {norm_value(p, attr) for p in parts}
        if len(nv) == 1 and next(iter(nv)).isdigit():
            return nv.pop()                                  # 「6h（21600s）」「3h / 10800s」：两种写法等值时取归一值
    m = _KV.match(v)
    if m and "=" not in v or (m and re.search(r"\s=\s", v)):
        return f"{m.group('k')}={m.group('n').replace(',', '')}"
    m = _NUM_UNIT.match(v)
    if not m:
        return v
    n = float(m.group("n").replace(",", "") + ("." + m.group("f") if m.group("f") else ""))
    u = (m.group("u") or "").lower()
    au = _attr_unit(attr)
    if u and au is not None:
        x = n * _UNIT_SEC.get(u, _UNIT_SEC.get(m.group("u"), 1)) / au
        if abs(x - round(x)) < 1e-9:
            return str(int(round(x)))
        return v
    if u:
        return v                                             # 属性不带单位：保留原写法（不臆造换算）
    return str(int(n)) if not m.group("f") else f"{n:g}"


def _clean_value(v: str) -> str:
    v = v.replace("\x01", ",")
    v = _TRAIL.sub("", v.strip().strip(" ,:;=|"))
    return v.strip().strip(" ,:;=|").strip()


def _ok_ent(e: Optional[str]) -> bool:
    from .loose import _clean_subj
    if e and (not _HAS_CJK.search(e) or re.match(r"^\d", e)):
        return False                                         # 纯英文主体（代码标识、专名）不登记：精度优先，已知召回边界
    if e and _HAS_CJK.search(e) and (len(e) > 16 or _FUNC.search(e.replace("·", ""))):
        return False
    if e and _HAS_CJK.search(e) and (len(e) < 2 or _clean_subj(e) != e or re.search(r"那边|这边|那里|这里|方面|听说|据说|现在|如今|因为|由于", e)):
        return False
    return bool(e) and bool(_ENT_OK.match(e)) and not _BAD_ENT.match(e) and not _VERB_RE.fullmatch(e) \
        and (bool(_HAS_CJK.search(e)) or len(e) >= 3) and not _TAG_WORDS.match(e) and not e.isdigit()


def _ok_attr(a: Optional[str]) -> bool:
    if a and _HAS_CJK.search(a) and (len(a) > 8 or len(a) < 2 or _FUNC.search(a)):
        return False
    return a is None or (bool(_ATTR_OK.match(a)) and not _VERB_RE.fullmatch(a) and not _BAD_ENT.match(a)
                         and not _RETIRE.fullmatch(a) and not _UNRES.fullmatch(a))


def _ok_val(v: Optional[str]) -> bool:
    if v and _HAS_CJK.search(v) and (len(v) > 8 or len(v) < 2 or _FUNC.search(v) or " " in v):
        return False                                         # 中文取值须是短名词（≤8 字、无虚词）
    if not v or len(v) > 40 or _VERB_RE.fullmatch(v) or _CONN.fullmatch(v) or _BAD_ENT.match(v):
        return False
    if re.search(r"[,;]|\s{2,}", re.sub(r"\([^()]*\)", "()", v)) or _CAUSE_HEAD.match(v) and _CAUSE_HEAD.sub("", v) != v:
        return False
    if _UNRES.fullmatch(v) or _RETIRE.fullmatch(v) or _RESOLVE.fullmatch(v):
        return False
    return True


def _verbatim(x: Optional[str], src: str) -> bool:
    src = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", src)
    return x is None or re.sub(r"\s+", "", x) in re.sub(r"\s+", "", src)


def _two_values(tail: str) -> Optional[Tuple[str, str]]:
    tail = re.sub(r"(?<![A-Za-z_])(?:tbd|pending|undecided|open|unresolved|wip)(?![A-Za-z_])|待定|未定|尚未定|尚未|还没定|悬而未决", " ", tail, flags=re.I)
    tail = tail.split(",")[0]
    m = re.match(r"^\s*(?P<a>[^\s,/|&]+?)\s*(?:与|和|及|跟|、|/|\||&|\bvs\.?|\bor\b|\band\b|或)\s*(?P<b>[^\s,/|&]+?)\s*$", tail, re.I)
    if not m:
        return None
    return _clean_value(m.group("a")), _clean_value(m.group("b"))


def extract_shorthand(sent: str) -> Optional[dict]:
    """返回 dict(op, entity, attr, value, alt, reason, first) 或 None。attr＝None 表示「位置」。"""
    src = sent.strip()
    if not _PRE.search(src):
        return None                                          # 便宜的前置过滤：无英文字母/冒号/箭头/方括号/等号/中文词间空格的句子直接跳过
    if not src or len(src) > 160 or re.search(r"[？?]\s*$", src) or src.count("|") > 2:
        return None
    if _CODE.search(src.replace("n/a", "").replace("->", "→").replace("=>", "→").replace(">>", "→")) or "**" in src or re.match(r"^\s*>", src) or len(re.findall(_ARROW, src)) > 1 or re.search(r"[“”]", src):
        return None                                          # markdown 强调/引用、多级箭头链、带中文引号的叙述：不是变更速记
    t = src.translate(_QUOTES).rstrip("。.!！ ").strip()
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)                 # 千分位逗号先并回，免得被当分句
    t = re.sub(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(\d+)(?![\d:])", r"\1=\2", t)   # 字段对齐：key: 16 → key=16（先于冒号切分）
    NORM[0] = t
    if not _CUE.search(t):
        return None
    TAGGED[0] = False
    TAGS[0] = ""
    MOVETAG[0] = False
    for _ in range(3):
        m = _TAG.match(t)
        if not m:
            break
        tag = m.group(0)
        inner = tag.strip()[1:-1].strip() if tag.strip().startswith("[") else ""
        if inner and not _TAG_WORDS.match(inner) and _ok_ent(inner) and not _VERB_RE.search(inner):
            t = inner + " " + t[m.end():]                     # [主体] 写法：方括号里是主体而不是标签（不算标签语境）
            break
        TAGS[0] += " " + inner
        if re.fullmatch(r"(?i)mv|move[ds]?|moving|relocated?|搬迁|迁移|移动|搬家|调动", inner or ""):
            MOVETAG[0] = True
        TAGGED[0] = TAGGED[0] or not re.match(r"^\s*(?:[-*•>]+\s+|\d+[.)、]\s*)$", tag)   # 列表符/序号不算标签
        t = t[m.end():]
    t = re.sub(r"\s+", " ", t).strip()
    for _ in range(3):
        t2 = _MSG_PREFIX.sub("", t).strip()
        if t2 == t:
            break
        t = t2
        TAGGED[0] = True                                     # FYI/update/@oncall 等消息前缀：状态同步语境，等同标签
    t = re.sub(r"(?<=[" + _CJK + r"A-Za-z0-9_)\]])\s*(?:这边|那边|这里|那里|方面|这头|那头)\s*(?:的\s*)?", " 的 ", t)   # 「S 这边 A」→「S 的 A」
    if TAGGED[0] or _STRONG.search(t):
        t = re.sub(r"(?<=[" + _CJK + r"])(?=(?:" + _GLUE_VERB + r"))", " ", t)      # 「依赖名改成了」：粘连的多字变更动词前补空格（只在消息/标签/速记语境）
    t = re.sub(r"(首次|初次|最终|最后|争议|分歧|已经|重新|再次|正式)(?=(?:" + _ZH_VERB + r"))", r"\1 ", t)
    t, en_first = _en_norm(t)
    body, reason = _strip_cause(t)
    first = en_first or bool(re.search(r"(?<![A-Za-z_])(?:init(?:ial(?:ly)?|ialized)?|first|new)(?![A-Za-z_])|初值|初始|首定|首次|起始|一开始", t, re.I))
    clauses = [c.strip() for c in body.split(" , ") if c.strip()]
    if not clauses:
        return None
    extra = [c for c in clauses[1:] if not _cue_only(c)]
    if len(extra) > 1 or any(len(c) > 16 for c in extra):
        return None                                          # 自检：主干之外最多一个短的裸起因分句（其余须是 TBD/未定/不再保留取值 之类提示）
    main = clauses[0]
    whole = " , ".join(clauses) + ((" , " + TAGS[0].strip()) if TAGS[0].strip() else "")
    # —— 动作判定（mem0 式 ADD/UPDATE/DELETE 的四分：set / retire / unresolve / resolve）
    rm = next((m for m in _RETIRE.finditer(main) if not _HAS_CJK.match(m.group(0)) or m.start() == 0 or m.group(0).startswith("不再")
               or re.match(r"[\s:,\]]", main[m.start() - 1])), None)
    vm = None
    for m in _VERB_RE.finditer(main):
        if m.start() > 0 and main[:m.start()].strip():
            vm = m; break
    if rm and rm.start() == 0 and not _HAS_CJK.match(rm.group(0)):   # 「deprecate S 的 A，不再保留取值」：英文撤销词在句首
        s_, a_ = _split_head(main[rm.end():])
        if a_:
            return _check("retire", s_, a_, None, None, reason, False, src)
    if vm is None:                                            # 动词在句首：「Updated S's A to V」「mv S → V」
        m0 = _VERB_RE.match(main)
        if m0:
            rest = main[m0.end():]
            mm = re.search(r"\s+(?:to|into|as|→|->|=>|=)\s+|\s*(?:→|->|=>|=)\s*|\s+(?:为|到|成)\s*|(?<=[" + _CJK + r"])(?:为|到|成)", rest, re.I)
            if mm and rest[:mm.start()].strip():
                return _finish("set", rest[:mm.start()], rest[mm.end():], m0.group(0), reason, first, src, whole)
            return None
    if rm and (vm is None or rm.start() <= vm.start()) and not _RESOLVE.search(whole):
        head = main[:rm.start()]
        s, a = _split_head(head)
        if not a and s and ":" in main[:rm.start()]:
            pass
        return _check("retire", s, a, None, None, reason, False, src)
    if _UNRES.search(whole) and not _RESOLVE_STRONG.search(whole):
        return _unresolve(clauses, reason, src)
    op = "resolve" if _RESOLVE.search(whole) else "set"
    if vm is None and ":" not in main and len(clauses) > 1 and _VERB_RE.match(clauses[1]):
        main = main + " " + clauses[1]                       # 「S 的 A 争议聊完了，定了 V」：动词在下一分句
        vm = next((m for m in _VERB_RE.finditer(main) if m.start() > 0), None)
    if vm is None:                                            # 字段写法「S A: V」：冒号当赋值
        mm = list(re.finditer(r":", main)) or list(re.finditer(r"(?<![A-Za-z0-9_])=", main))
        if not mm:
            m3 = re.match(r"^(?P<h>.+?)\s+(?P<v>[A-Za-z_][A-Za-z0-9_]*=\d+|[A-Za-z_][A-Za-z0-9_]*\([^()]*\)|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\s*[A-Za-z]+)?)$", main)
            if not (m3 and TAGGED[0] and len(clauses) <= 2):
                return None                                  # 「FYI S A <英文记号>」：消息/标签语境下，属性后直接跟取值记号
            return _finish(op, m3.group("h"), m3.group("v"), ":", reason, first, src, whole)
        k = mm[-1]
        head, tail = main[:k.start()], main[k.end():]
        if op == "resolve":
            head = re.sub(r"(?:争议|分歧|dispute)\s*(?:落定|定案|裁定|settled|resolved)?\s*$", "", head, flags=re.I)
        ctx = TAGGED[0] or (reason and _EXPL_CAUSE.search(t)) or re.fullmatch(r"\s*[A-Za-z0-9_][^" + _CJK + r"]*", tail or "")
        bare = [c for c in clauses[1:] if not _cue_only(c) or (not _EXPL_CAUSE.search(c) and not re.search(r"(?i)tbd|pending|未定|待定|定案|落定", c))]
        if not ctx or (bare and not (TAGGED[0] and len(bare) == 1 and len(bare[0]) <= 14)):
            return None                                      # 无动词字段写法须有标签/显式起因/英文数值取值作语境，且不带裸分句
        return _finish(op, head, tail, ":", reason, first, src, whole)
    head, tail = main[:vm.start()], main[vm.end():]
    if not _CONN.sub("", tail, count=1).strip(" :=") and len(clauses) > 1:   # 「A 改了，= V」「A 改了，现在 = V」：取值落在下一分句
        nxt = re.sub(r"^(?:现在|目前|如今|now)?\s*[:=]?\s*", "", clauses[1], flags=re.I)
        if nxt and not _CAUSE_HEAD.match(clauses[1]):
            tail = " " + nxt
    if op == "resolve":
        head = re.sub(r"(?:的)?\s*(?:争议|分歧|dispute)\s*(?:(?:最终|final|finally|finali[sz]ed?|落定|定案|裁定|settled?|resolved|closed|尘埃|聊完了|定了)\s*)*$", "", head, flags=re.I)
        if not tail.strip() or _RESOLVE.fullmatch(tail.strip(" :")):
            for c in clauses[1:]:
                if not _RESOLVE.search(c):
                    tail = c; break
    return _finish(op, head, tail, vm.group(0), reason, first, src, whole)


_CUE_ONLY = re.compile(r"(?:\s*(?:(?<![A-Za-z_])(?:tbd|pending|undecided|unresolved|wip|deprecated?|no\s+value(?:\s+retained|\s+kept)?|n/a|null|none|final|"
                       r"settled|resolved|done|ok|dispute\s+settled|since\s+then|thereafter|from\s+then\s+on|anymore|no\s+(?:longer|value|decision)[A-Za-z\s]*|"
                       r"(?:with\s+)?no\s+value\s+(?:retained|remains|kept)[A-Za-z\s]*)(?![A-Za-z_])|不再保留取值|不再保留|不保留取值|不留值|无值|未定|待定|尚未定|尚未裁定|还没定|没定|悬而未决|"
                       r"争议定案|争议落定|定案|落定|已裁定|裁定|拍板|尘埃落定|[" + _CJK + r"]{2,14}(?:导致|所致|引起|引发|触发|驱动)?)\s*)+", re.I)
# —— _CUE_ONLY.fullmatch 的无灾难回溯等价实现（chain-r20）。原式 (?:\s*(?:…|[CJK]{2,14}…)\s*)+ 在长串上失败时
#    指数回溯（一段 259 字带标点的散文 >20 分钟）。等价改写：①字母表预检——串里有任一字符不可能出现在任何单元里 ⇒ 必不匹配；
#    ②短串（≤ _CUE_SHORT）直接用原式（回溯有界）；③长串用「单元可达位置」动态规划，单元 = 原式 + 号内的一节，逐位置求所有可能终点。
_CUE_UNIT = re.compile(_CUE_ONLY.pattern[len("(?:"):-len(")+")], re.I)
_CUE_ALPHA = re.compile(r"[A-Za-z\s/" + _CJK + r"]", re.I)
_CUE_SHORT = 24


def _cue_only(c: str) -> bool:
    """与 bool(_CUE_ONLY.fullmatch(c)) 逐条相同，但最坏 O(n²) 次有界单元匹配。"""
    n = len(c)
    if n == 0:
        return False
    for ch in set(c):
        if not _CUE_ALPHA.match(ch):
            return False
    if n <= _CUE_SHORT:
        return bool(_CUE_ONLY.fullmatch(c))
    reach = [False] * (n + 1); reach[0] = True
    for i in range(n):
        if not reach[i]:
            continue
        for j in range(n, i, -1):
            if not reach[j] and _CUE_UNIT.fullmatch(c, i, j):
                reach[j] = True
        if reach[n]:
            return True
    return reach[n]


_FUNC = re.compile(r"[的了是在把被也都很就还着过呢吗每让使而又才这那么如果我你他她它不没]")
_CODE = re.compile(r"[{}\\<>]|//|\b(?:def|class|return|yield|import|None|True|False|null|var|let|const)\b|^\s*[.#/$]")
_UCUE = re.compile(r"(?<![A-Za-z_])(?:tbd|pending|undecided|open|unresolved|either|both|wip|values?|vals?|two|coexisting|co-existing|competing|"
                   r"has|have|with|options?|candidates?|a\s+final\s+decision|final\s+decision|decision|yet|not\s+decided|no\s+decision)(?![A-Za-z_])|"
                   r"(?:现在)?有俩值|俩值|两个\s*value|两(?:个|种)?(?:取)?值|两个|两种|并存|待定|未定|待议|未决|尚未定|尚未|还没定|没定|悬而未决|二选一|同时有", re.I)
_PAIR = re.compile(r"(?P<a>[^\s,:+]+?)\s*(?:与|和|及|跟|、|/|\||&|\+|(?<![A-Za-z_])(?:vs\.?|or|and|versus)(?![A-Za-z_])|或)\s*(?P<b>[^\s,:]+)", re.I)


def _unresolve(clauses, reason, src):
    """并存未决：去掉未决提示词后找第一对「V1 与/vs/或 V2」，其前为主体+属性。"""
    for k, c in enumerate(clauses):
        x = re.sub(r"\s+", " ", _UCUE.sub(" ", c)).strip()
        for m in _PAIR.finditer(x):
            a, b = _clean_value(m.group("a")), _clean_value(m.group("b"))
            if not (_ok_val(a) and _ok_val(b)) or _VERB_RE.fullmatch(a) or _VERB_RE.fullmatch(b):
                continue
            head = x[:m.start()]
            if k > 0 and not _ok_ent(_split_head(head)[0]):
                head = re.sub(r"\s+", " ", _UCUE.sub(" ", clauses[0]))
            head = re.sub(r"(?:" + _ARROW + r"|(?<![A-Za-z_])(?:set|is|are|=)(?![A-Za-z_]))\s*$", "", head.strip(" :"), flags=re.I)
            sj, aj = _split_head(head)
            if aj is None and sj and " " not in sj:
                pass
            r = _check("unresolve", sj, aj, a, b, reason, False, src)
            if r:
                return r
            break
    return None


def _finish(op, head, tail, verb, reason, first, src, whole):
    tail = _CONN.sub("", tail, count=1) if _CONN.match(tail) else tail
    tail = re.split(r"\s+,\s+|,", tail)[0]
    if not _KV.match(tail.strip()):
        tail = re.split(r"\s*:\s*(?=[" + _CJK + r"])", tail)[0] if re.match(r"^\s*[^:\s]", tail) else tail
    raw = _clean_value(re.sub(r"(?:,?\s*)?(?:争议|分歧)?(?:落定|定案|裁定|拍板)$", "", tail))
    if op == "resolve":
        head = re.sub(r"(?:的)?\s*(?:争议|分歧|dispute)\s*(?:(?:最终|final|finally|finali[sz]ed?|落定|定案|裁定|settled?|resolved|closed|尘埃|聊完了|定了)\s*)*$", "", head, flags=re.I)
    s, a = _split_head(head)
    loc_explicit = bool(a and _LOC_ATTR.match(a)) or (a is None and MOVETAG[0])
    if verb == ":" and not (s and a and _HAS_CJK.search(s) and (_HAS_CJK.search(a) or _LOC_ATTR.match(a))):
        return None
    if a is None and raw and verb != ":":                   # 「S: bump A → V」：属性在动词之后（字段对齐容错）
        mm = re.match(r"^(?P<a>[" + _CJK + r"]{2,8})\s*(?:→|->|=>|=|:|\s(?:to|为|到|成)\s)\s*(?P<v>.+)$", raw)
        if mm:
            a, raw = mm.group("a"), _clean_value(mm.group("v"))
    if a and _LOC_ATTR.match(a):
        a = None
    if re.fullmatch(_ARROW, verb.strip()) and (not (TAGGED[0] or reason and _EXPL_CAUSE_W.search(src) or re.match(r"^\s*[A-Za-z0-9_]", raw or ""))
                                               or len(re.split(r"\s*,\s*", whole.replace(TAGS[0].strip(), "").rstrip(" ,"))) > 2):
        return None                                          # 「S：A → V」多是流程笔记；裸箭头只认「S A → V」
    if a is None and not loc_explicit and re.fullmatch(_ARROW, verb.strip()):
        return None                                          # 裸箭头无属性：不臆定为位置（散文里「A → B」多是流程/因果）
    if verb == ":" and not (s and a and _HAS_CJK.search(s) and _HAS_CJK.search(a)) or verb == ":" and re.search(r"[=/]", raw or "") and not _KV.match(raw or ""):
        return None                                          # 无动词的「S A: V」字段写法：主体、属性都须是中文名词
    if a is None and not loc_explicit and not (_MOVE_VERB.match(verb.strip()) or _LOC_ATTR.match(_clean_tok(head).split()[-1] if _clean_tok(head) else "")):
        return None                                          # 无属性时只认移动类动词（属性＝位置）
    if a is None and not (_HAS_CJK.search(raw or "") and len(raw) <= 12):
        return None
    val = norm_value(raw, a) if raw else raw
    return _check(op, s, a, val, None, reason, first, src, raw)


def _check(op, s, a, v, alt, reason, first, src, raw=None):
    """抽取后自检（Graphiti 式「先抽再验」的自研版）：任一不过即放弃。"""
    if not _ok_ent(s) or not _ok_attr(a) or (a is not None and a == s):
        return None
    if op == "retire" and a is None:                         # 撤销须有属性（不臆定为位置）
        return None
    if a is not None and _LOC_ATTR.match(a):
        a = None
    if op in ("set", "resolve"):
        rv = raw if raw is not None else v
        if not _ok_val(v) or v in (s, a) or not (_verbatim(rv, src) or _verbatim(rv, NORM[0])):
            return None
    if op == "unresolve":
        if not (_ok_val(v) and _ok_val(alt)) or v == alt or not (_verbatim(v, src) and _verbatim(alt, src)):
            return None
    if not (_verbatim(s, src.translate(_QUOTES)) and _verbatim(a, src.translate(_QUOTES))):
        return None
    return {"op": op, "entity": s, "attr": a, "value": v, "alt": alt, "reason": reason, "first": first}


_DECIDE = re.compile(r"(?i)定|最终|拍板|落定|裁定|(?<![A-Za-z_])(?:final(?:ly)?|settle[ds]?|decided|confirm(?:ed)?|resolved)(?![A-Za-z_])")


def decides(sent: str) -> bool:
    """句中有「决定/最终」类信号（未决后的新值据此才判为裁定）。"""
    return bool(_DECIDE.search(sent or ""))


def anchored_ok(sent: str, a: dict) -> bool:
    """词表锚定结果的自检（只在速记信号句上用）：值须是句中完整记号、不是标签/提示词/起因；主体不得是更长点分名的前缀。"""
    t = (sent or "").translate(_QUOTES)
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)
    for x in (a.get("value"), a.get("alt")):
        if not x:
            continue
        if _TAG_WORDS.match(x) or _MSG_PREFIX.fullmatch(x) or _UCUE.fullmatch(x) or _VERB_RE.fullmatch(x) or (a.get("reason") and x == a["reason"]) or x[-1] in ":=：":
            return False
        rs = _strip_cause(re.sub(r"\s+", " ", t).rstrip("。. "))[1]
        if rs and x in rs:
            return False                                     # 起因里的词不能当取值
        ok = False
        for m in re.finditer(re.escape(x), t):
            pre, post = t[max(0, m.start() - 1):m.start()], t[m.end():m.end() + 1]
            if not re.match(r"[A-Za-z0-9_.]", pre or " ") and not re.match(r"[A-Za-z0-9_:=.%]", post or " "):
                ok = True
                break
        if not ok:
            return False
    e = a.get("entity") or ""
    if e and all(t[m.end():m.end() + 1] == "·" for m in re.finditer(re.escape(e), t)):
        return False
    return True


def pre_normalize(sent: str) -> str:
    """消息体前置规范化（供严格/宽松/锚定三条路径共用）：去句首 @提及、FYI/update、时间寒暄前缀；「S 这边 A」→「S 的 A」。
    只在句子带速记信号或消息前缀时改写，其余原样返回（中文散文不受影响）。"""
    t = (sent or "").strip()
    if not t or not (_PRE.search(t) and (_STRONG.search(t) or _MSG_PREFIX.match(t))):
        return t
    for _ in range(3):
        t2 = _MSG_PREFIX.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    t = re.sub(r"(?<=[" + _CJK + r"A-Za-z0-9_)\]」』])\s*(?:这边|那边|这里|那里|方面|这头|那头)\s*(?:的\s*)?", " 的 ", t)
    return t


def norm_event_value(v, attr):
    """非严格事件的取值归一：只做数值格式（千分位/单位按属性换算/键值对齐/等值括注），不认的写法原样返回。"""
    if not v:
        return v
    x = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", v.translate(_QUOTES)).strip()
    x = re.sub(r"\s*\(\s*(?:=|≈|~|i\.e\.?|aka|即|约|也就是)\s*[^()]{1,16}\)", "", x).strip()
    x = re.sub(r"(?<=[\dsmhd])\s*\(\s*\d+(?:\.\d+)?\s*(?:ms|s|sec|secs|seconds?|min|mins|minutes?|h|hr|hrs|hours?|d|days?|秒|分钟|小时|天)?\s*\)$", "", x).strip()
    y = norm_value(x, attr)
    return y if y != x else (v if x == v.strip() else x if _NUM_UNIT.match(x) or _KV.match(x) else v)
