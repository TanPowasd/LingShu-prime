# -*- coding: utf-8 -*-
"""受限 LLM 抽取（chain-r12 B 臂，可开关模式；**缺省关**）。

开关：环境变量 ``LINGSHU_NG_CHAIN_LLM=1``。关时本模块不被调用，账本与零 LLM 路径逐条相同。

只在两类句子上调用（其余句子不调用）：
  1. 有事件信号（速记强信号 / 消息前缀 / 变更·移动·撤销·未决·裁定词）但规则路径（严格→宽松→速记→锚定）没有登记任何事件
     （结果为 none、仅 mention，或锚定结果被速记自检拒收）；
  2. 有事件信号、规则登记了事件但结果可疑：取值不是规范写法（数值/键值归一后会变）、取值是动词补语残片、
     主体带句首标签、属性夹带状语/人称。
输出受限：JSON ``{op, entity, attr, value, alt, reason}``，op ∈ {set, move, retire, unresolve, resolve, none}；
entity/attr/value/alt/reason 必须是原句的逐字子串（取值随后过与零 LLM 路径共用的数值/键值归一 ``norm_event_value``）。
任一字段校验失败 ⇒ 丢弃，保留规则结果。缓存未命中且调用失败（无网络/无密钥/超时）⇒ 保留规则结果（离线确定性）。

模型：Cline cline-pass/deepseek-v4.1-flash，thinking 关，T=0。结果缓存：``LINGSHU_LLM_CACHE``（键＝请求体 sha1，含提示词版本）。
费用：每次真实调用把网关返回的 cost 追加到 ``LINGSHU_NG_CHAIN_LLM_COSTLOG``（若设）；``STATS`` 记触发/调用/命中/采纳/拒收。"""
from __future__ import annotations

import logging
import hashlib
import json
import os
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from . import shorthand as _sh

_log = logging.getLogger(__name__)

ON = os.environ.get("LINGSHU_NG_CHAIN_LLM", "0").strip().lower() in ("1", "true", "yes", "on")
MODEL = os.environ.get("LINGSHU_NG_CHAIN_LLM_MODEL", "cline-pass/deepseek-v4.1-flash")
URL = os.environ.get("LINGSHU_NG_CHAIN_LLM_URL", "https://api.cline.bot/api/v1/chat/completions")
CACHE = os.environ.get("LINGSHU_LLM_CACHE") or os.path.expanduser("~/.cache/lingshu_ng/llm_cache")
COSTLOG = os.environ.get("LINGSHU_NG_CHAIN_LLM_COSTLOG")
OFFLINE = os.environ.get("LINGSHU_NG_CHAIN_LLM_OFFLINE", "0") == "1"      # 只读缓存，不发请求
WORKERS = int(os.environ.get("LINGSHU_NG_CHAIN_LLM_WORKERS", "4"))
GATE = os.environ.get("LINGSHU_NG_CHAIN_LLM_GATE", "ea")   # ea：实体名+该实体已登记属性同句（缺省）；ea2/names/index 为 dev 比较用
PROMPT_VER = "r12.1"   # 第 2 轮未改提示词（缓存可复用）
OPS = ("set", "move", "retire", "unresolve", "resolve", "none")
STATS = {"trig_none": 0, "trig_susp": 0, "calls": 0, "cache_hit": 0, "fail": 0, "accept": 0, "reject": 0, "say_none": 0, "cost": 0.0}
_lock = threading.Lock()

SYS = ("你是一个信息抽取器。输入是一句工作记录/消息/备注（常常中英夹杂、速记写法）。判断这句话是否陈述了「某个东西（主体）的某个属性」的一次状态变化，"
       "如果是，输出这一次变化；不是就输出 op=none。\n"
       "op 取值：set＝首次定下或改成新值；move＝主体搬到/迁到新的地方（位置变化）；retire＝该属性作废、撤销、此后不再有值；"
       "unresolve＝出现两个并存的取值、尚未定下；resolve＝争议/分歧最终定为某值；none＝不是状态变化（描述、提问、计划、闲聊等）。\n"
       "字段：entity＝主体全名（含「·」连接的层级名，不含句首【标签】/[标签]/@某人/渠道前缀）；attr＝属性名（move 时为 null）；"
       "value＝新值（retire 为 null；unresolve 时为第一个值）；alt＝unresolve 的第二个值，否则 null；reason＝起因，没有则 null。\n"
       "硬性要求：除 null 外，每个字段必须是原句里**逐字出现**的连续片段（不改字、不翻译、不补全、不换算单位、不去空格）；"
       "数值连同原句里紧跟的单位一起照抄（如「6h」「21,600 秒」「retry = 16」）。\n"
       "只输出一个 JSON 对象，形如 {\"op\":...,\"entity\":...,\"attr\":...,\"value\":...,\"alt\":...,\"reason\":...}，不要任何其他文字。\n"
       "示例：\n"
       "句子：[看板] 北辰服务·网关 的 超时秒数 bump 到 90s，压测结论。\n"
       "{\"op\":\"set\",\"entity\":\"北辰服务·网关\",\"attr\":\"超时秒数\",\"value\":\"90s\",\"alt\":null,\"reason\":\"压测结论\"}\n"
       "句子：@全员 老周 已经 relocate 去 二号楼 了。\n"
       "{\"op\":\"move\",\"entity\":\"老周\",\"attr\":null,\"value\":\"二号楼\",\"alt\":null,\"reason\":null}\n"
       "句子：北辰服务 的压缩算法 zstd vs lz4 还在 debate，没拍板。\n"
       "{\"op\":\"unresolve\",\"entity\":\"北辰服务\",\"attr\":\"压缩算法\",\"value\":\"zstd\",\"alt\":\"lz4\",\"reason\":null}\n"
       "句子：明天下午三点开会讨论 北辰服务 的部署方案。\n"
       "{\"op\":\"none\",\"entity\":null,\"attr\":null,\"value\":null,\"alt\":null,\"reason\":null}")

_EV_WORDS = re.compile(
    r"确立|定为|定成|定下|定在|改为|改成|改用|换成|换为|换上|变为|变成|调整|调成|调到|调为|设为|设成|设置|更新为|更新成|转为|转成|选定|确定为|敲定|拍板|裁定|"
    r"搬到|搬去|搬进|迁到|迁往|迁至|移到|移至|挪到|挪去|住进|回到|来到|落脚|撤销|撤掉|撤了|取消|作废|废止|废除|废掉|不再|删除|删掉|移除|拿掉|划掉|"
    r"并存|两个值|两种|未定|没定|待定|悬而未决|争议|分歧|争执|"
    r"(?<![A-Za-z_])(?:set|sets|setting|changed?|changes|switch(?:ed|es)?|bump(?:ed|s)?|mov(?:e|ed|es)|relocat(?:e|ed|es)|updated?|"
    r"deprecated?|drop(?:ped)?|removed?|rm|retired?|unset|tbd|pending|coexist\w*|resolved?|settled?|decided|final(?:ized)?|"
    r"→|->|=>)(?![A-Za-z_])", re.I)
_TAG_LEAD = re.compile(r"^\s*(?:[\[【][^\]】]{0,12}[\]】]|@\S+)")
_BAD_VAL = re.compile(r"^(?:下来|下|好|了|上|过|完|掉|成)$")
_BAD_ATTR = re.compile(r"\s|因|按|根据|我们|现在|已经|now|again", re.I)


_MOVE_W = re.compile(r"搬|迁|挪|移|住进|回到|来到|落脚|去了|转去|(?<![A-Za-z_])(?:mov(?:e|ed|es|ing)|relocat\w*|mv|transfer\w*)(?![A-Za-z_])|→|->|=>", re.I)


def move_signal(sent: str) -> bool:
    return bool(_MOVE_W.search(sent))


def has_signal(sent: str) -> bool:
    s = (sent or "").strip()
    if not s or len(s) > 200:
        return False
    return bool(_sh.strong_cue(s) or _sh.pre_normalize(s) != s or _EV_WORDS.search(s))


_PAREN_CJK = re.compile(r"[（(][^）)]*[\u4e00-\u9fff][^）)]*[）)]")
_TAIL_FRAG = re.compile(r"\s+(?:了|走|来|吧|啦|呢)$|^[A-Za-z]$|[:：=]$")
_UNRES_CUE = re.compile(r"两个|两种|俩|并存|还没定|没定|未定|待定|悬而未决|(?<![A-Za-z_])(?:tbd|pending|coexist\w*|vs\.?)(?![A-Za-z_])", re.I)


def suspicious(ev) -> bool:
    """规则结果可疑（只看结果本身与原句，不看任何语料词表）。r12 第 2 轮：括注夹带、尾部虚词残片、千分位截断、
    单字母取值、键值残缺、句中有并存未决信号而结果不是 unresolve。"""
    v, e, a = ev.value, ev.entity or "", ev.attr or ""
    q = ev.quote or ""
    if v and (_PAREN_CJK.search(v) or _TAIL_FRAG.search(v)):
        return True
    if v and re.fullmatch(r"\d{1,3}", v.strip()) and re.search(r"(?<![\d,])" + re.escape(v.strip()) + r",\d{3}", q):
        return True
    if ev.op != "unresolve" and ev.op != "retire" and _UNRES_CUE.search(q):
        return True
    if v and _sh.norm_event_value(v, ev.attr) != v:
        return True
    if ev.alt and _sh.norm_event_value(ev.alt, ev.attr) != ev.alt:
        return True
    if v and _BAD_VAL.match(v.strip()):
        return True
    if _TAG_LEAD.match(e):
        return True
    return bool(a) and a != "位置" and bool(_BAD_ATTR.search(a))


def _key(body) -> str:
    return hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _call(sent: str) -> Optional[str]:
    body = {"model": MODEL, "max_tokens": 400, "temperature": 0.0, "reasoning": {"enabled": False},
            "messages": [{"role": "system", "content": SYS + f"\n（提示词版本 {PROMPT_VER}）"},
                         {"role": "user", "content": "句子：" + sent.strip()}]}
    k = _key(body); p = os.path.join(CACHE, k[:2], k + ".json")
    with _lock:
        STATS["calls"] += 1
    if os.path.exists(p):
        try:
            with _lock:
                STATS["cache_hit"] += 1
            return json.load(open(p, encoding="utf-8")).get("content")
        except (OSError, ValueError):
            pass
    if OFFLINE:
        with _lock:
            STATS["fail"] += 1
        return None
    key = os.environ.get("LINGSHU_NG_LLM_KEY") or os.environ.get("CLINE_API_KEY") or "x"
    for attempt in range(3):
        try:
            req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            d = json.load(urllib.request.urlopen(req, timeout=60))
            d = d.get("data", d)
            m = d["choices"][0]["message"]
            content = m.get("content") or ""
            cost = float(((m.get("provider_metadata") or {}).get("gateway") or {}).get("cost") or (d.get("usage") or {}).get("cost") or 0)
            with _lock:
                STATS["cost"] += cost
                if COSTLOG:
                    with open(COSTLOG, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"t": time.time(), "model": MODEL, "tag": "chain_llm_extract", "cost": cost}) + "\n")
            if not content.strip():
                continue
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"content": content, "cost": cost, "model": MODEL}, f, ensure_ascii=False)
            os.replace(tmp, p)
            return content
        except Exception:  # noqa: BLE001
            _log.debug("LLM 抽取请求失败（网络 / 解析，类型不可枚举）→ 退避重试", exc_info=True)
            time.sleep(2 * (attempt + 1))
    with _lock:
        STATS["fail"] += 1
    return None


def _parse(content: Optional[str]):
    if not content:
        return None
    m = re.search(r"\{.*\}", content, re.S)
    try:
        o = json.loads(m.group(0)) if m else None
    except ValueError:
        return None
    return o if isinstance(o, dict) else None


def _validate(o, sent: str):
    """返回 dict（与 loose 输出同形）、"none"（模型判非事件）或 None（校验失败）。"""
    if not o:
        return None
    op = o.get("op")
    if op not in OPS:
        return None
    if op == "none":
        return "none"
    f = {}
    for k in ("entity", "attr", "value", "alt", "reason"):
        x = o.get(k)
        if x is None or (isinstance(x, str) and not x.strip()):
            f[k] = None
            continue
        if not isinstance(x, str):
            return None
        x = x.strip()
        if x not in sent:                                  # 逐字子串校验
            return None
        f[k] = x
    if not f["entity"] or (_TAG_LEAD.match(f["entity"])):
        return None
    if op == "move":
        attr = None
    else:
        if not f["attr"]:
            return None
        attr = f["attr"]
    if op in ("set", "move", "resolve", "unresolve") and not f["value"]:
        return None
    if op == "unresolve" and not f["alt"]:
        return None
    if op == "retire":
        f["value"] = None
    if op != "unresolve":
        f["alt"] = None
    val = _sh.norm_event_value(f["value"], attr) if f["value"] else None
    alt = _sh.norm_event_value(f["alt"], attr) if f["alt"] else None
    return {"op": "set" if op == "move" else op, "entity": f["entity"], "attr": attr, "value": val, "alt": alt,
            "reason": f["reason"], "first": False}


def run(sents: List[str]) -> List[object]:
    """并发抽取，按输入顺序返回 dict / "none" / None。"""
    if not sents:
        return []

    def one(s):
        r = _validate(_parse(_call(s)), s.strip())
        with _lock:
            if r == "none":
                STATS["say_none"] += 1
            elif r is None:
                STATS["reject"] += 1
            else:
                STATS["accept"] += 1
        return r
    if len(sents) == 1 or WORKERS <= 1:
        return [one(s) for s in sents]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        return list(ex.map(one, sents))
