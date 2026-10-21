# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""VSA 记忆（THEORY §2）：写入 = 规则抽角色 + 痕迹 Σ R⊗F + 词袋；查询 = 相似度检索 search / 解绑查询 query(role=?, given={...})。
规则全部写死在下方 RULES_*，每个抽取结果带 (角色, 填充, 规则号, 原文片段)，可回溯；抽不到的角色不写，只留词袋。"""
import datetime, math, re

import numpy as np
import scipy.sparse as sp

import hdc as H
import ri as RI
from cleanup import Cleanup, DOUBT

ROLES = ("SPEAKER", "TIME", "SESSION", "AGENT", "WITH", "ACTION", "PLACE", "ENTITY", "BAG")   # SESSION：阶段 2，会话日期单独成角色（PREREG_v2 §A）

# ---------------------------------------------------------------- 分词（BM25 与 VSA 共用）
STOP_EN = set("""a an the and or but if of to in on at for with by from as is are was were be been being am do does did done have has had
i me my we our you your he him his she her it its they them their this that these those there here what which who whom whose when where why how
so not no yes just very really too also than then can could would should will shall may might must about into over after before up down out
s t ll ve re d m don didn doesn isn wasn aren weren haven hasn hadn won wouldn couldn shouldn oh yeah hey hi wow ok okay""".split())
_TOK = re.compile(r"[a-z0-9]+(?:'[a-z]+)?|[\u3400-\u9fff]+")


def tokens(text, stop=True):
    out = []
    for m in _TOK.finditer(text.lower()):
        t = m.group(0)
        if "\u3400" <= t[0] <= "\u9fff":
            out += [t] if len(t) == 1 else [t[i:i + 2] for i in range(len(t) - 1)]   # 汉字二元组
        else:
            t = t.split("'")[0]
            if not (stop and t in STOP_EN) and t:
                out.append(t)
    return out


def is_zh(text):
    return sum("\u3400" <= c <= "\u9fff" for c in text) > 0.2 * max(1, len(text.strip()))


# ---------------------------------------------------------------- 时间规范化
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                          "october", "november", "december"])}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
WEEKDAYS_EN = {d: i + 1 for i, d in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}
WD_ZH = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}


def t_date(d):
    return f"DATE:{d.isoformat()}"


def parse_en_date(s):
    """'8 May, 2023' / 'May 8, 2023' / '1:56 pm on 8 May, 2023' → date | None。"""
    s = s.lower()
    m = re.search(r"(\d{1,2})\s+([a-z]+),?\s+(\d{4})", s)
    if m and m.group(2) in MONTHS:
        return datetime.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"([a-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m.group(1) in MONTHS:
        return datetime.date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    return None


# ---------------------------------------------------------------- 规则表（白箱，写死）
# 动作闭集：(表面形式, 规范填充)。中文按最长匹配；英文整词。
ACTIONS_ZH = ["爬山", "看电影", "打篮球", "打羽毛球", "吃火锅", "买书", "跑步", "游泳", "散步", "下棋", "唱歌", "画画", "钓鱼", "野餐",
              "喝咖啡", "购物", "看展", "露营", "跳舞", "打乒乓球", "开会", "学习", "参加", "旅行", "做饭"]
ACTIONS_EN = {"hiking": "hike", "hike": "hike", "hiked": "hike", "shopping": "shop", "bowling": "bowl", "swimming": "swim", "swam": "swim",
              "sketching": "sketch", "fishing": "fish", "dancing": "dance", "jogging": "jog", "chess": "chess", "karaoke": "karaoke",
              "picnic": "picnic", "camping": "camp", "camped": "camp", "painting": "paint", "painted": "paint", "running": "run", "ran": "run",
              "skating": "skate", "cycling": "cycle", "climbing": "climb", "baking": "bake", "baked": "bake", "cooking": "cook",
              "volunteering": "volunteer", "volunteered": "volunteer", "visited": "visit", "visit": "visit", "attended": "attend",
              "concert": "concert", "race": "race", "adopted": "adopt", "bought": "buy", "read": "read", "reading": "read",
              "studying": "study", "yoga": "yoga", "pottery": "pottery", "surfing": "surf", "travelled": "travel", "traveled": "travel",
              "trip": "trip", "parade": "parade", "festival": "festival", "workshop": "workshop", "museum": None}
PLACE_SUFFIX_ZH = "馆|园|院|场|店|湖|山|厅|站|校|楼|街|城|寺|塔|岛|村|室|中心|广场|市场|超市|酒吧|海边|河边"
RE = {
    "zh-PL-1": re.compile(r"(?:在|去了?|到)([\u4e00-\u9fff]{0,5}?(?:" + PLACE_SUFFIX_ZH + "))"),
    "en-PL-1": re.compile(r"\b(?:at|to|in|into|near) the ([a-z]+(?: [a-z]+)?)\b"),
    "zh-TM-wd": re.compile(r"(?:周|星期|礼拜)([一二三四五六日天])"),
    "zh-TM-md": re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})[日号]"),
    "en-TM-wd": re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"),
    "en-TM-rel": re.compile(r"\b(yesterday|tomorrow|last (?:week|weekend|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
                            r"|next (?:week|weekend|month|year))\b"),
    "zh-TM-rel": re.compile(r"(昨天|前天|明天|上周末?|上个?月|去年|下个?月|明年)"),
    "en-ENT-1": re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,}(?: [A-Z][a-z]{2,})*)\b"),
    "zh-ENT-1": re.compile(r"《([^》]{1,20})》"),
}
PLACE_STOP_EN = {"morning", "evening", "afternoon", "end", "past", "moment", "future", "beginning", "world", "way", "same", "first", "last",
                 "middle", "meantime", "area", "time", "day", "weekend", "week", "night", "other", "best", "most", "long", "least"}
ENT_STOP_EN = set(w.capitalize() for w in STOP_EN) | {m.capitalize() for m in MONTHS} | {d.capitalize() for d in WEEKDAYS_EN} | {
    "Thanks", "Thank", "Wow", "Hey", "Yeah", "Sure", "Sounds", "Great", "Glad", "Awesome", "Congrats", "Haha", "Image", "Lol", "Nice",
    "Cool", "Good", "Love", "Well", "That", "This", "What", "It", "I"}


def _rel_time(expr, base):
    """相对时间 + 写入时基准日期 → 规范时间填充（LoCoMo 金标习惯：'The week before 9 June 2023'、'7 May 2023'、'2022'、'June 2023'）。"""
    e = expr.lower()
    if base is None:
        return None
    if e in ("yesterday", "昨天"):
        return t_date(base - datetime.timedelta(days=1))
    if e == "前天":
        return t_date(base - datetime.timedelta(days=2))
    if e in ("tomorrow", "明天"):
        return t_date(base + datetime.timedelta(days=1))
    if e in ("last week", "上周"):
        return f"BEFORE:week:{base.isoformat()}"
    if e in ("last weekend", "上周末"):
        return f"BEFORE:weekend:{base.isoformat()}"
    if e.startswith("last ") and e[5:] in WEEKDAYS_EN:
        return f"BEFORE:{e[5:]}:{base.isoformat()}"
    if e in ("last month", "上个月", "上月"):
        y, m = (base.year, base.month - 1) if base.month > 1 else (base.year - 1, 12)
        return f"MONTH:{y:04d}-{m:02d}"
    if e in ("next month", "下个月", "下月"):
        y, m = (base.year, base.month + 1) if base.month < 12 else (base.year + 1, 1)
        return f"MONTH:{y:04d}-{m:02d}"
    if e in ("last year", "去年"):
        return f"YEAR:{base.year - 1}"
    if e in ("next year", "明年"):
        return f"YEAR:{base.year + 1}"
    if e in ("next week",):
        return f"AFTER:week:{base.isoformat()}"
    if e in ("next weekend",):
        return f"AFTER:weekend:{base.isoformat()}"
    return None


# ---------------------------------------------------------------- 阶段 2 时间规则（PREREG_v2 §A / §B，THEORY §7）
_NUMW = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "a couple of": 2, "couple of": 2}
_N = r"(\d{1,2}|a couple of|couple of|an?|one|two|three|four|five|six|seven|eight|nine|ten)"
_WD = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
_MONRE = "|".join(sorted(MONTHS, key=len, reverse=True))
FUTURE_EN = re.compile(r"(\bwill\b|'ll\b|\bgoing to\b|\bgonna\b|\bplan(?:s|ning|ned)?\b|\bnext\b|\btomorrow\b)")
RE2_EN = [   # (规则号, 正则)；同一轮取文中最先出现者（同位置取最长）
    ("en-TM2-yday", re.compile(r"\b(yesterday|last night)\b")),
    ("en-TM2-today", re.compile(r"\b(today|tonight|this (?:morning|afternoon|evening))\b")),
    ("en-TM2-tmr", re.compile(r"\btomorrow\b")),
    ("en-TM2-ndays", re.compile(r"\b" + _N + r" days? ago\b")),
    ("en-TM2-fewdays", re.compile(r"\b(?:a )?few days ago\b")),
    ("en-TM2-week", re.compile(r"\b(?:a week ago|last week|this past week)\b")),
    ("en-TM2-nweeks", re.compile(r"\b" + _N + r" weeks ago\b")),
    ("en-TM2-wkend", re.compile(r"\b(?:last weekend|this past weekend|over the weekend)\b")),
    ("en-TM2-thiswkend", re.compile(r"\bthis weekend\b")),
    ("en-TM2-lastwd", re.compile(r"\b(?:last|this past) (" + _WD + r")\b")),
    ("en-TM2-nextwd", re.compile(r"\bnext (" + _WD + r")\b")),
    ("en-TM2-onwd", re.compile(r"\bon (" + _WD + r")\b")),
    ("en-TM2-nextwk", re.compile(r"\bnext (week|weekend)\b")),
    ("en-TM2-month", re.compile(r"\b(last|this|next) month\b")),
    ("en-TM2-nmonths", re.compile(r"\b" + _N + r" months? ago\b")),
    ("en-TM2-year", re.compile(r"\b(last|this|next) year\b")),
    ("en-TM2-nyears", re.compile(r"\b" + _N + r" years? ago\b")),
    ("en-TM2-onth", re.compile(r"\bon the (\d{1,2})(?:st|nd|rd|th)\b")),
    ("en-TM2-full", re.compile(r"\b(?:(\d{1,2})(?:st|nd|rd|th)? (" + _MONRE + r"),? (\d{4})|(" + _MONRE + r") (\d{1,2})(?:st|nd|rd|th)?,? (\d{4}))\b")),
    ("en-TM2-inyear", re.compile(r"\b(?:in|since) ((?:19|20)\d{2})\b")),
]
RE2_ZH = [
    ("X-TM2-iso", re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")),
    ("zh-TM2-ymd", re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})[日号]")),
    ("zh-TM2-ym", re.compile(r"(\d{4})年(\d{1,2})月(?!\d)")),
    ("zh-TM2-y", re.compile(r"(\d{4})年(?!\d)")),
    ("zh-TM2-md", re.compile(r"(?<![\d年])(\d{1,2})月(\d{1,2})[日号]")),
    ("zh-TM2-rel", re.compile(r"(昨天|前天|明天|上周末?|上个?月|去年|下个?月|明年)")),
    ("zh-TM2-wd", re.compile(r"(?:周|星期|礼拜)([一二三四五六日天])")),
]


def _num(s):
    s = s.strip()
    return int(s) if s.isdigit() else _NUMW.get(s)


def _mon_shift(y, m, k):
    t = y * 12 + (m - 1) + k
    return f"MONTH:{t // 12:04d}-{t % 12 + 1:02d}"


def wd_before(b, wd):
    """b 之前最近的星期 wd（1=周一…7=周日），严格早于 b。"""
    d = (b.isoweekday() - wd) % 7 or 7
    return b - datetime.timedelta(days=d)


def wd_after(b, wd):
    d = (wd - b.isoweekday()) % 7 or 7
    return b + datetime.timedelta(days=d)


def _fill_en(rule, m, b, low):
    td = datetime.timedelta
    g = m.groups()
    if rule == "en-TM2-yday":
        return t_date(b - td(days=1))
    if rule == "en-TM2-today":
        return t_date(b)
    if rule == "en-TM2-tmr":
        return t_date(b + td(days=1))
    if rule == "en-TM2-ndays":
        n = _num(g[0]); return t_date(b - td(days=n)) if n else None
    if rule == "en-TM2-fewdays":
        return f"FEWDAYS:{b.isoformat()}"
    if rule == "en-TM2-week":
        return f"BEFORE:week:{b.isoformat()}"
    if rule == "en-TM2-nweeks":
        n = _num(g[0])
        return None if not n else (f"BEFORE:week:{b.isoformat()}" if n == 1 else f"BEFORE:{n}weeks:{b.isoformat()}")
    if rule == "en-TM2-wkend":
        return f"BEFORE:weekend:{b.isoformat()}"
    if rule == "en-TM2-thiswkend":
        return f"WEEKEND_OF:{b.isoformat()}"
    if rule == "en-TM2-lastwd":
        return t_date(wd_before(b, WEEKDAYS_EN[g[0]]))
    if rule == "en-TM2-nextwd":
        return t_date(wd_after(b, WEEKDAYS_EN[g[0]]))
    if rule == "en-TM2-onwd":
        return t_date((wd_after if FUTURE_EN.search(low) else wd_before)(b, WEEKDAYS_EN[g[0]]))
    if rule == "en-TM2-nextwk":
        return f"AFTER:{g[0]}:{b.isoformat()}"
    if rule == "en-TM2-month":
        return _mon_shift(b.year, b.month, {"last": -1, "this": 0, "next": 1}[g[0]])
    if rule == "en-TM2-nmonths":
        n = _num(g[0]); return _mon_shift(b.year, b.month, -n) if n else None
    if rule == "en-TM2-year":
        return f"YEAR:{b.year + {'last': -1, 'this': 0, 'next': 1}[g[0]]}"
    if rule == "en-TM2-nyears":
        n = _num(g[0]); return f"YEAR:{b.year - n}" if n else None
    if rule == "en-TM2-onth":
        n = int(g[0])
        if not 1 <= n <= 31:
            return None
        fut = FUTURE_EN.search(low)
        y, mo = b.year, b.month
        if fut and n < b.day:
            y, mo = (y, mo + 1) if mo < 12 else (y + 1, 1)
        elif not fut and n > b.day:
            y, mo = (y, mo - 1) if mo > 1 else (y - 1, 12)
        try:
            return t_date(datetime.date(y, mo, n))
        except ValueError:
            return None
    if rule == "en-TM2-full":
        d, mo, y = (g[0], g[1], g[2]) if g[0] else (g[4], g[3], g[5])
        try:
            return t_date(datetime.date(int(y), MONTHS[mo], int(d)))
        except (ValueError, KeyError):
            return None
    if rule == "en-TM2-inyear":
        return f"YEAR:{g[0]}"
    return None


def _fill_zh(rule, m, b):
    g = m.groups()
    try:
        if rule in ("X-TM2-iso", "zh-TM2-ymd"):
            return t_date(datetime.date(int(g[0]), int(g[1]), int(g[2])))
        if rule == "zh-TM2-ym":
            return f"MONTH:{int(g[0]):04d}-{int(g[1]):02d}" if 1 <= int(g[1]) <= 12 else None
        if rule == "zh-TM2-y":
            return f"YEAR:{g[0]}"
        if rule == "zh-TM2-md":
            return t_date(datetime.date(b.year, int(g[0]), int(g[1]))) if b else None
    except ValueError:
        return None
    if rule == "zh-TM2-rel":
        return _rel_time(g[0], b)
    if rule == "zh-TM2-wd":
        return f"WD:{WD_ZH[g[0]]}"
    return None


def extract_time_v2(text, base_date=None, lang=None):
    """→ [] 或 [(TIME, 填充, 规则号, 原文片段)]：文中最先出现（同位置取最长）的可解析时间表达，至多一个（PREREG_v2 §A）。
    英文相对表达需要 base_date；中文绝对日期不需要。lang="zh"/"en" 强制规则表（默认按 is_zh）。"""
    zh = is_zh(text) if lang is None else lang == "zh"
    low = text.lower()
    best = None
    for rule, rx in (RE2_ZH if zh else RE2_EN):
        if not zh and base_date is None and rule not in ("en-TM2-full", "en-TM2-inyear"):
            continue
        for m in rx.finditer(text if zh else low):
            f = _fill_zh(rule, m, base_date) if zh else _fill_en(rule, m, base_date, low)
            if f is None:
                continue
            key = (m.start(), -(m.end() - m.start()))
            if best is None or key < best[0]:
                best = (key, ("TIME", f, rule, (text if zh else low)[m.start():m.end()]))
            break                                  # 每条规则只看它的第一次出现
    return [best[1]] if best else []


def extract_roles(text, persons=(), speaker=None, base_date=None, base_time=None, weekday=True, time_rules="v1", session=None,
                  prev=None):
    """→ [(角色, 填充, 规则号, 原文片段)]。persons = 人名表（说话人 + 调用方给的名字），speaker = 说话人，
    base_date = 写入时的日期（datetime.date，用于解析相对时间），base_time = 调用方直接给的时间填充（如会话日期、事件时间）。
    weekday=False：不把文中星期/月日写成 TIME（PREREG_v1 §c 的 LoCoMo 口径：只认相对时间，否则会话日期）。"""
    out = []
    zh = is_zh(text)
    low = text.lower()
    if speaker:
        out.append(("SPEAKER", speaker, "X-SPK", speaker))
    if session:
        out.append(("SESSION", session, "X-SESSION", session))       # v2：会话日期单独成角色，不混入 TIME
    # TIME：文中相对时间（需基准）> 文中星期/日期 > 调用方给的基准时间
    tm = []
    if time_rules == "v2":
        tm = extract_time_v2(text, base_date)
        weekday = False                                                # v2 规则已含星期/日期，下方 v1 分支跳过
    elif time_rules != "v1":
        raise ValueError(f"未知 time_rules={time_rules!r}")
    for m in (() if time_rules == "v2" else RE["en-TM-rel"].finditer(low) if not zh else RE["zh-TM-rel"].finditer(text)):
        f = _rel_time(m.group(1), base_date)
        if f:
            tm.append(("TIME", f, "en-TM-rel" if not zh else "zh-TM-rel", m.group(0)))
    if not weekday:
        pass
    elif zh:
        for m in RE["zh-TM-md"].finditer(text):
            y = int(m.group(1)) if m.group(1) else (base_date.year if base_date else None)
            if y:
                try:
                    tm.append(("TIME", t_date(datetime.date(y, int(m.group(2)), int(m.group(3)))), "zh-TM-md", m.group(0)))
                except ValueError:
                    pass
        for m in RE["zh-TM-wd"].finditer(text):
            tm.append(("TIME", f"WD:{WD_ZH[m.group(1)]}", "zh-TM-wd", m.group(0)))
    else:
        for m in RE["en-TM-wd"].finditer(low):
            if not re.search(r"last\s+$", low[:m.start()]):
                tm.append(("TIME", f"WD:{WEEKDAYS_EN[m.group(1)]}", "en-TM-wd", m.group(0)))
    if tm:
        out += tm
    elif base_time:
        out.append(("TIME", base_time, "X-TIME", base_time))
    # AGENT / WITH：人名表内的名字；紧跟在 和/跟/与/同/约了/with/and 之后的为 WITH，其余第一个为 AGENT
    body = text.split(": ", 1)[1] if (speaker and ": " in text[:40]) else text    # 说话人前缀不参与人名匹配
    hits = []
    for p in persons:
        for m in re.finditer(re.escape(p) if zh else r"\b" + re.escape(p) + r"\b", body):
            hits.append((m.start(), p))
    hits.sort()
    agent = None
    for pos, p in hits:
        pre = body[max(0, pos - 4):pos]
        if (zh and re.search(r"(和|跟|与|同|约了)$", pre)) or (not zh and re.search(r"\b(with|and|met)\s+$", body[max(0, pos - 6):pos], re.I)):
            out.append(("WITH", p, "zh-WITH-1" if zh else "en-WITH-1", pre + p))
        elif agent is None:
            agent = p
            out.append(("AGENT", p, "zh-AG-1" if zh else "en-AG-1", p))
    if agent is None and speaker:
        if (zh and body.lstrip().startswith(("我", "我们"))) or (not zh and re.match(r"\s*(i|i'm|i've|i'd|we|we're|we've)\b", body, re.I)):
            out.append(("AGENT", speaker, "zh-AG-2" if zh else "en-AG-2", body.lstrip()[:3]))
            agent = speaker
    # v2 指代/省略（PREREG_v2 §C）：无 AGENT 且句首为代词/省略主语 ⇒ AGENT := 紧邻上一句的 AGENT；句中无 TIME ⇒ 继承上一句 TIME
    if agent is None and prev and prev.get("AGENT"):
        st = body.lstrip()
        mz = re.match(r"(他|她|和|跟|同|与)", st) if zh else re.match(r"(he|she|went|headed|met)\b", st, re.I)
        if mz:
            agent = prev["AGENT"]
            out.append(("AGENT", agent, "zh-AG-3" if zh else "en-AG-3", mz.group(0)))
            if not any(r[0] == "TIME" for r in out) and prev.get("TIME"):
                out.append(("TIME", prev["TIME"], "X-TM-inh", prev["TIME"]))
    # ACTION：闭集
    if zh:
        for a in sorted(ACTIONS_ZH, key=len, reverse=True):
            i = text.find(a)
            if i >= 0:
                out.append(("ACTION", a, "zh-ACT-1", a)); break
    else:
        for m in re.finditer(r"[a-z]+", low):
            f = ACTIONS_EN.get(m.group(0))
            if f:
                out.append(("ACTION", f, "en-ACT-1", m.group(0))); break
    # PLACE
    if zh:
        m = RE["zh-PL-1"].search(text)
        if m:
            out.append(("PLACE", m.group(1), "zh-PL-1", m.group(0)))
    else:
        for m in RE["en-PL-1"].finditer(low):
            w = m.group(1).split()
            w = [x for x in w if x not in STOP_EN]
            if w and w[0] not in PLACE_STOP_EN:
                out.append(("PLACE", w[0] if len(w) == 1 or w[1] in PLACE_STOP_EN else " ".join(w), "en-PL-1", m.group(0))); break
    # ENTITY
    if zh:
        for m in RE["zh-ENT-1"].finditer(text):
            out.append(("ENTITY", m.group(1), "zh-ENT-1", m.group(0)))
    else:
        seen = set(persons)
        for m in RE["en-ENT-1"].finditer(body):
            e = m.group(1)
            if e.split()[0] in ENT_STOP_EN or e in seen:
                continue
            seen.add(e)
            out.append(("ENTITY", e, "en-ENT-1", e))
    for r in out:
        assert r[0] in ROLES and (r[2].startswith("X-") or r[3] and (r[3] in text or r[3].lower() in low or r[3] in str(text))), r   # I6 片段 ⊂ 原文
    return out


# ---------------------------------------------------------------- 记忆
CFG_BD = {"long_only": True, "index_sep": True, "one_time": True, "fallback": True, "use_q": True}   # 正文日期 BD 守卫变异改这里


class Memory:
    def __init__(self, space=None, beta=RI.BETA, window=RI.WINDOW, chunk_long=True, body_date=False):
        """chunk_long=True（默认，2026-10-21 起 = L1，RESULTS_long_hold.md）：叠加项 > K_MAX 的单元按 seg.segment_long 切块写入；
        chunk_long=False = 旧路径 S0（逐单元一条痕迹，超 K_MAX 在 trace 时抛 CapacityError），只用于复现历史读数。"""
        self.space = space or H.Space()
        self.ri = RI.RandomIndex(self.space, window=window, beta=beta)
        self.texts, self.toks, self.roles = [], [], []          # 按痕迹（短单元 = 1 条，长单元 = 每块 1 条）
        self.chunk_long = chunk_long
        self.unit_of, self.chunks, self.unit_texts = [], [], []  # 审计：痕迹 → 单元号；单元 → 其痕迹号表（块数 = len）；单元原文
        self._V = None
        self._T = {}
        self.codebooks = {}
        self.body_date = body_date                                # 正文日期 BD（PREREG_body_date §1），默认关
        self.bd, self.bd_rows = {}, []                            # 单元号 → 子痕迹号表；子痕迹 = {unit, sent, toks, fill, rule, span, kind}
        self._BT, self._bdq = {}, {}

    # 写入
    def write(self, text, roles=None, chunk_long=None, sent_roles=None, body_date=None, time_fn=None, **kw):
        """roles 为 None 时按规则抽取（kw 透传 extract_roles）；写入时增量更新 RI 共现计数。→ 单元号。
        chunk_long（None = 用构造参数）：True ⇒ L1，与 seg.segment_long 同一实现：≤K_MAX 的单元逐位同旧路径（一条痕迹），
        >K_MAX 的单元按 seg.make_elems 元素写入序贪心装成 ≤K_MAX 的块，每块一条痕迹、共享单元号（不再拒写）。
        sent_roles：可选「句 → 角色」函数；给出时长单元先切句、每句角色 = sent_roles(句)（PerLTQA 口径，seg_real.run_perltqa）；
        不给时长单元元素 = make_elems(单元, 原文, roles)（LoCoMo / hive / crossproj 口径）。chunk_long=False ⇒ 旧路径 S0。
        body_date（None = 用构造参数）：True ⇒ 另写正文日期子痕迹（PREREG_body_date §1，只对长单元、只供 decode_unit_q）；检索索引不变。
        time_fn：句 → [] 或 [TIME 项]；不给时 = sent_roles 的 TIME 项（给了 sent_roles）或 extract_time_v2(句, kw["base_date"], 单元语言)。"""
        tk = tokens(text)
        rs = extract_roles(text, **kw) if roles is None else list(roles)
        u = len(self.unit_texts)
        cl = self.chunk_long if chunk_long is None else chunk_long
        if cl:
            import seg as SG                                   # 延迟导入：seg 依赖本模块
            es, _ = (SG.make_elems(0, text, None, None, 0, sentence_split=True, role_fn=sent_roles) if sent_roles
                     else SG.make_elems(0, text, rs, None, 0))
            _, _, _, rows, _ = SG.segment_long([(tk, rs)], es)
        else:
            rows = [(tk, rs)]
        self.unit_texts.append(text); self.chunks.append([])
        for ctk, crs in rows:
            self.texts.append(text); self.toks.append(list(ctk) if cl else ctk)
            self.roles.append(list(crs) if cl else crs)
            self.unit_of.append(u); self.chunks[u].append(len(self.texts) - 1)
            for r, f, *_ in self.roles[-1]:
                self.codebooks.setdefault(r, Cleanup(self.space)).add(f"F:{f}")     # 填充原子与角色无关（F:名字），角色只靠绑定区分
            self.ri.add(self.toks[-1])
        self._V = None
        if self.body_date if body_date is None else body_date:
            self._write_bd(u, text, tk, rs, sent_roles, time_fn, kw.get("base_date"))
        return u

    def _write_bd(self, u, text, tk, rs, sent_roles, time_fn, base_date):
        """§1.1–§1.6：只对长单元（整单元载荷 > K_MAX，同 seg.is_long）写每句一条子痕迹，每条恰一个 TIME、≤ K_MAX；不碰检索索引。"""
        import seg as SG
        if CFG_BD["long_only"] and SG.n_items((tk, rs)) <= H.K_MAX:
            return
        zh = is_zh(text)
        if time_fn is None:
            time_fn = ((lambda s: [r for r in sent_roles(s) if r[0] == "TIME"][:1]) if sent_roles
                       else (lambda s: extract_time_v2(s, base_date, lang="zh" if zh else "en")))
        rows = SG.time_anchor_blocks(text, time_fn, zh)
        for k, (sent, tm, kind) in enumerate(rows):
            stk = tokens(sent)
            pieces, cur = [], []
            for w in stk:                                     # 单句项数 > K_MAX ⇒ 按词序切片，每片带同一个 TIME（1 + 不同词 ≤ K_MAX）
                if w not in cur and len(set(cur)) + 2 > H.K_MAX:
                    pieces.append(cur); cur = []
                cur.append(w)
            pieces.append(cur)
            for pt in pieces:
                self.bd.setdefault(u, []).append(len(self.bd_rows))
                self.bd_rows.append({"unit": u, "sent": k, "toks": pt, "fill": tm[1], "rule": tm[2], "span": tm[3], "kind": kind})
                if not CFG_BD["index_sep"]:                   # 变异：子痕迹写进检索库
                    self.texts.append(text); self.toks.append(list(pt)); self.roles.append([tm]); self.unit_of.append(u)
                    self.chunks[u].append(len(self.texts) - 1); self.ri.add(pt)
        self._bdq = {}

    def bd_items(self, j):
        """子痕迹 j 的叠加项：一个 ROLE:TIME⊗F:填充 + 本句词袋（同 Memory.trace 编码）。"""
        r = self.bd_rows[j]
        fills = [r["fill"]] if CFG_BD["one_time"] else sorted({x["fill"] for x in self.bd_rows if x["unit"] == r["unit"]})
        return [("ROLE:TIME", f"F:{f}") for f in fills] + [("ROLE:BAG", w) for w in sorted(set(r["toks"]))]

    def bd_trace(self, j):
        t = self._BT.get(j)
        if t is None:
            items = self.bd_items(j)
            if len(items) > H.K_MAX:
                raise H.CapacityError(f"子痕迹 {j} 叠加 {len(items)} 项 > K_MAX={H.K_MAX}")
            t = H.bundle(H.bind(self.space.vec(r), self.space.vec(f)) for r, f in items)
            self._BT[j] = t
        return t

    def bd_codebook(self):
        """子痕迹清理码本 = L1 的 TIME 码本名（同序）∪ 子痕迹填充；L1 码本本身不变。"""
        names = list(self.codebooks["TIME"].names) if "TIME" in self.codebooks else []
        key = (len(names), len(self.bd_rows))
        if getattr(self, "_bdcb_key", None) != key:
            self._bdcb = Cleanup(self.space, names + [f"F:{r['fill']}" for r in self.bd_rows])
            self._bdcb_key = key
        return self._bdcb

    def bd_decode(self, j):
        name, c, m, raw = self.bd_codebook().query(H.unbind(self.bd_trace(j), self.space.vec("ROLE:TIME")))
        return (name if name == DOUBT else name[2:]), c, m, raw[2:]

    def bd_cos(self, u, question, beta=None):
        """§1.7：问句内容向量 · 单元 u 各子痕迹内容向量的余弦（同 vectors 的 idf + RI 投影）。"""
        key = (question, beta, len(self.texts), len(self.bd_rows))
        if key not in self._bdq:
            idf = self.idf()
            Vs, Q = self.ri.project([self._wmat([r["toks"] for r in self.bd_rows], idf), self._wmat([tokens(question)], idf)], beta=beta)
            q = Q[0]; qn = float(np.linalg.norm(q))
            vn = np.linalg.norm(Vs, axis=1); vn[vn == 0] = 1
            self._bdq = {key: np.zeros(len(Vs)) if qn == 0 else (Vs @ q) / (vn * qn)}
        c = self._bdq[key]
        return [float(c[j]) for j in self.bd[u]]

    def decode_unit_q(self, u, role, question, beta=None):
        """带问句的单元解绑 → (填充 | 存疑, 余弦, 边距, 原始最近填充, 来源)。来源：l1（无子痕迹或非 TIME，≡ decode_unit）/
        bd（子痕迹按问句余弦降序，取第一个非存疑；全存疑 ⇒ 存疑）/ fallback（最大余弦 ≤ 0，显式回退 decode_unit）。"""
        js = self.bd.get(u)
        if role != "TIME" or not js:
            return (*self.decode_unit(u, role), "l1")
        cs = self.bd_cos(u, question, beta)
        if CFG_BD["fallback"] and max(cs) <= 0:
            return (*self.decode_unit(u, role), "fallback")
        order = sorted(range(len(js)), key=lambda k: -cs[k]) if CFG_BD["use_q"] else list(range(len(js)))
        first = None
        for k in order:
            a = self.bd_decode(js[k])
            if a[0] != DOUBT:
                return (*a, "bd")
            first = first or a
        return (*first, "bd")

    @property
    def n_chunks(self):
        """审计：每单元块数（1 = 未切）。"""
        return [len(c) for c in self.chunks]

    def __len__(self):
        return len(self.texts)

    # 内容向量（相似度检索）
    def idf(self):
        N = len(self.texts)
        df = np.zeros(len(self.ri.words), dtype=np.float64)
        for tk in self.toks:
            for w in set(tk):
                df[self.ri.vocab[w]] += 1
        return np.log1p(N / np.maximum(df, 1))

    def _wmat(self, toks_list, idf):
        rows, cols, vals = [], [], []
        for r, tk in enumerate(toks_list):
            c = {}
            for w in tk:
                i = self.ri.vocab.get(w)
                if i is not None:                     # 库外词跳过（THEORY §3）
                    c[i] = c.get(i, 0) + 1
            for i, n in c.items():
                rows.append(r); cols.append(i); vals.append((1 + math.log(n)) * idf[i])
        return sp.csr_matrix((np.asarray(vals, dtype=np.float32), (rows, cols)), shape=(len(toks_list), len(self.ri.words)))

    def vectors(self, queries=(), beta=None):
        """→ (V 文本内容向量 N×D, Q 问句向量 M×D)，单次按块投影。"""
        idf = self.idf()
        W = self._wmat(self.toks, idf)
        Wq = self._wmat([tokens(q) for q in queries], idf)
        V, Q = self.ri.project([W, Wq], beta=beta)
        return V, Q

    def search_many(self, queries, beta=None):
        """→ [每题对全部记忆的余弦分数数组]。"""
        V, Q = self.vectors(queries, beta=beta)
        vn = np.linalg.norm(V, axis=1); vn[vn == 0] = 1
        out = []
        for q in Q:
            qn = np.linalg.norm(q)
            out.append(np.zeros(len(V)) if qn == 0 else (V @ q) / (vn * qn))
        return out

    # 痕迹（解绑查询）
    def trace(self, i):
        """T_i = Σ R_r⊗F_f + Σ_{w∈词集} R_BAG⊗I_w（整数叠加）；项数 > K_MAX ⇒ CapacityError（I3）。"""
        t = self._T.get(i)
        if t is None:
            items = [(f"ROLE:{r}", f"F:{f}") for r, f, *_ in self.roles[i]]
            items += [("ROLE:BAG", w) for w in sorted(set(self.toks[i]))]          # 词袋用 RI 的索引向量 I_w
            if len(items) > H.K_MAX:
                raise H.CapacityError(f"痕迹 {i} 叠加 {len(items)} 项 > K_MAX={H.K_MAX}：需分块")
            t = H.bundle(H.bind(self.space.vec(r), self.space.vec(f)) for r, f in items)
            self._T[i] = t
        return t

    def rank_units(self, queries, beta=None):
        """→ 每题的单元完整排序（L1 展开口径 ≡ seg.expand(段=块, expand_chunks)）：痕迹按余弦降序（稳定），按单元号去重保序。
        无切块时（全短单元或 chunk_long=False）≡ S0 的 argsort(-分数, stable)。"""
        out = []
        for s in self.search_many(queries, beta=beta):
            seen, o = set(), []
            for t in np.argsort(-np.asarray(s), kind="stable"):
                v = self.unit_of[t]
                if v not in seen:
                    seen.add(v); o.append(v)
            out.append(o)
        return out

    def decode_unit(self, u, role):
        """单元级解绑（≡ seg.SegView.decode）：按写入序逐块解绑，取第一个非存疑；全存疑返回首块结果。旧路径下超 K_MAX 照旧抛 CapacityError。"""
        first = None
        for t in self.chunks[u]:
            a = self.decode(t, role)
            if a[0] != DOUBT:
                return a
            first = first or a
        return first or (DOUBT, 0.0, 0.0, None)

    def units(self):
        """单元级视图（texts / len / decode 按单元号），供 real_v2.answer_time 等按单元下标作答的口径使用。"""
        return UnitView(self)

    def probe(self, given):
        return H.bundle(H.bind(self.space.vec(f"ROLE:{r}"), self.space.vec(f"F:{f}")) for r, f in given.items())

    def decode(self, i, role):
        """从第 i 条痕迹解绑 role 并清理 → (填充 | 存疑, 余弦, 边距, 原始最近填充)。"""
        cb = self.codebooks.get(role)
        if cb is None:
            return DOUBT, 0.0, 0.0, None
        y = H.unbind(self.trace(i), self.space.vec(f"ROLE:{role}"))
        name, c, m, raw = cb.query(y)
        return (name if name == DOUBT else name[2:]), c, m, raw[2:]

    def query(self, role, given, order=None, max_try=None):
        """解绑查询：按探针点积（= 命中 given 项数·D + 噪声，与痕迹长度无关）排序候选痕迹；
        依次解绑目标角色，第一个清理边距 ≥ MARGIN_MIN 的即答案；全部存疑则返回存疑（不静默猜）。
        order：可选外部给定的候选顺序（如检索分数），此时不用探针排序。"""
        roles = (role,) if isinstance(role, str) else tuple(role)
        match = None
        if order is None:
            P = self.probe(given).astype(np.float64)
            dots = np.array([float(self.trace(i).astype(np.float64) @ P) for i in range(len(self))]) / self.space.dim
            order = list(np.argsort(-dots, kind="stable"))
            top = dots[order[0]] if order else 0.0
            order = [i for i in order if dots[i] >= top - 0.5]        # 只在「命中 given 项数相同」的并列组内回退（期望差 1，噪声 σ≈√(gk/D)）
            match = float(top)
        for n, i in enumerate(order[:max_try] if max_try else order):
            ans = [self.decode(i, r) for r in roles]
            if all(a[0] != DOUBT for a in ans):
                return {"trace": int(i), "rank": n, "match": match, "answer": {r: a[0] for r, a in zip(roles, ans)},
                        "cos": {r: a[1] for r, a in zip(roles, ans)}, "margin": {r: a[2] for r, a in zip(roles, ans)}}
        return {"trace": None, "match": match, "answer": {r: DOUBT for r in roles}}


class UnitView:
    """Memory 的单元级视图：下标 = 单元号（长单元的多块共享）。"""

    def __init__(self, m):
        self.m, self.texts = m, m.unit_texts

    def __len__(self):
        return len(self.texts)

    def decode(self, i, role):
        return self.m.decode_unit(i, role)

    def decode_q(self, i, role, question):
        return self.m.decode_unit_q(i, role, question)
