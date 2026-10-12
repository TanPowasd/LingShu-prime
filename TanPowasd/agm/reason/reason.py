# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""推理 Reason：零模型版本链推理（抽取 → 编年链 → 题面路由 → 带时间过滤的作答）。

记忆系统最常见的推理失败不是「找不到」，而是「找错了版本」：值改过很多次，旧值还躺在记忆里。
本模块全程零模型、零网络、纯 stdlib：
  1. 抽取（通用中文状态变更句法 + 可替换动词表）：「主体 的 属性 <变更动词> 值[，起因是 X]」
     建立/变更/撤销/两说并存/裁定 五类；另有隐含属性动词（「甲 移到了 乙」⇒ 位置）；回顾句（「早先一度为」「曾经是」）不当事件；
     改名句（「A 自第 N 次…起改名为 B」「A 更名为 B」）登记为主体别名，不合并同名异体与下属单元。
  2. 编年：事件进 TanPowasd/chronicle 的不可变版本链（硬时间过滤、四态）。
  3. 路由：从题面认出主体（最长匹配，别名归一）、属性、序号与问型（现值/时点/历史/变更/缘由/状态）。
  4. 作答：值、状态、生效序号；变更题给完整链；缘由题按事件时点定位。
动词表与问型线索都是参数，可换语料；不读答案键，不读生成器日志。
"""
from __future__ import annotations

import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "chronicle"))
from chronicle import ChronicleMemory, Query  # noqa: E402

VERBS = {
    "set": ("首次确立为", "此后确立为", "确立为", "调整为", "改为", "改成", "转为", "变为", "变成", "更新为", "换成", "恢复为", "设为", "定为"),
    "retire": ("被撤销", "被废弃", "被取消", "不再保留取值"),
    "unresolved": ("出现两种并存的取值：", "出现两种说法：", "两说并存："),
    "resolve": ("的争议就此裁定为", "的争议最终裁定为", "最终裁定为"),
}
#: 隐含属性的动词：「主体 <动词> 值」，属性由动词决定（移动 → 位置）
IMPLICIT = {"位置": ("移到了", "搬到了", "搬去了", "来到了", "转移到", "迁到了")}
RETRO = ("早先一度", "曾经是", "曾一度", "以前是", "原先是", "回顾起来")
RENAME = re.compile(r"(?P<old>[^\s，。；：、]+)\s*(?:自第\s*\d+\s*\S{0,4}?起)?\s*(?:改名为|更名为|改称)\s*(?P<new>[^\s，。；：、]+)")
REASON = re.compile(r"[，,]\s*(?:起因是|原因是|因为)\s*(?P<r>[^，。；]+)\s*$")
SUBJ = r"(?:^|[，；：])\s*(?P<s>[^\s，。；：、]+)\s*的\s*(?P<a>[^\s，。；：、的]{1,12}?)\s*"
SPLIT = re.compile(r"[。！？\n]")
#: 句框（自主学习从数据里归纳的整句骨架）：⟨S⟩＝主体、⟨A⟩＝属性，骨架末尾接取值；字面字符原样匹配，空白宽松
FS, FA = "⟨S⟩", "⟨A⟩"


def frame_regex(tpl: str):
    out = []
    for tok in re.split(r"(⟨S⟩|⟨A⟩|\s+)", tpl):
        if tok == FS:
            out.append(r"(?P<s>[^\s，。；：、]+?)")
        elif tok == FA:
            out.append(r"(?P<a>[^\s，。；：、的]{1,12}?)")
        elif tok and tok.isspace():
            out.append(r"\s*")
        elif tok:
            out.append(re.escape(tok))
    return re.compile(r"(?:^|[，；：])\s*" + "".join(out) + r"\s*(?P<rest>.*)$")
QCUES = [  # (问型线索正则, 模式)
    (re.compile(r"经历过哪些变更|变更链|每一次变更|改过几次"), "chain"),
    (re.compile(r"为什么|缘由|什么原因|起因"), "reason"),
    (re.compile(r"处于什么状态|哪一态|现行 active"), "state"),
]
SEQ = re.compile(r"第\s*(\d+)\s*(?:次|章|轮|回)")


def _value(rest: str) -> str:
    """值到「，起因是」或句末为止；括号内的逗号不切。"""
    m = REASON.search(rest)
    v = rest[:m.start()] if m else rest
    v = re.sub(r"^\s*了(?=\s)", "", v)       # 动态助词：「改成了 V」不把「了」算进值
    return v.strip().strip("，,")


class Reason:
    def __init__(self, verbs=VERBS, retro=RETRO, implicit=IMPLICIT, use_alias=True, time_filter=True, frames=()):
        self.verbs, self.retro = verbs, retro
        self.use_alias, self.time_filter = use_alias, time_filter
        self.mem = ChronicleMemory()
        self.entities, self.facets = set(), set()
        self._n = 0
        pats = []
        for op, vs in verbs.items():
            for v in sorted(vs, key=len, reverse=True):
                pats.append((op, v, re.compile(SUBJ + re.escape(v.strip()) + r"\s*(?P<rest>.*)$")))
        self._pats = sorted(pats, key=lambda x: -len(x[1]))
        self._pats += [(op, tpl, frame_regex(tpl)) for tpl, op in frames]      # 学到的句框排在原表之后
        self._imp = [(fac, re.compile(r"(?:^|[，；：])\s*(?P<s>[^\s，。；：、]+)\s*" + re.escape(v) + r"\s*(?P<rest>.+)$"))
                     for fac, vs in implicit.items() for v in vs]

    # ---------- 写入 ----------
    def ingest(self, segments):
        """segments: [(seq, source_id, text)]，按任意顺序；先登记别名，再按 seq 写事件。"""
        segs = sorted(segments, key=lambda x: (x[0], x[1]))
        if self.use_alias:
            for _seq, _sid, text in segs:
                for m in RENAME.finditer(text):
                    old, new = m.group("old"), m.group("new")
                    if old != new:
                        try:
                            self.mem.add_alias("entity", old, new)
                        except ValueError:
                            pass
        for seq, sid, text in segs:
            for sent in SPLIT.split(text):
                self._sentence(seq, sid, sent.strip())

    def _sentence(self, seq, sid, sent):
        if not sent or any(r in sent for r in self.retro):
            return
        hits = [(op, verb, m) for op, verb, pat in self._pats for m in [pat.search(sent)] if m]
        if hits:                                         # 多个说法都能匹配时取属性最短的切法（「最早定|成了」不让短动词吞掉）
            hits = [min(hits, key=lambda h: (len(h[2].group("a")), -len(h[1])))]
        for op, verb, m in hits:
            s, a, rest = m.group("s"), m.group("a"), m.group("rest")
            r = REASON.search(sent)
            reason = r.group("r").strip() if r else None
            self._n += 1
            eid = f"{sid}:{self._n}"
            kw = dict(effective_at=seq, recorded_at=seq, reason=reason, quote=sent)
            if op == "set" or op == "resolve":
                v = _value(rest)
                if not v:
                    return
                getattr(self.mem, op)(eid, sid, s, a, v, **kw)
            elif op == "retire":
                self.mem.retire(eid, sid, s, a, **kw)
            elif op == "unresolved":
                parts = re.split(r"\s*(?:与|和|或)\s*", _value(rest), maxsplit=1)
                if len(parts) != 2:
                    return
                self.mem.unresolved(eid, sid, s, a, parts[0].strip(), parts[1].split("，")[0].strip(), **kw)
            self.entities.add(s); self.facets.add(a)
            return
        for fac, pat in self._imp:
            m = pat.search(sent)
            if m:
                v = _value(m.group("rest"))
                if v:
                    r = REASON.search(sent)
                    self._n += 1
                    self.mem.set(f"{sid}:{self._n}", sid, m.group("s"), fac, v, effective_at=seq, recorded_at=seq,
                                 reason=r.group("r").strip() if r else None, quote=sent)
                    self.entities.add(m.group("s")); self.facets.add(fac)
                return

    # ---------- 作答 ----------
    def parse(self, question: str):
        """题面 → (主体, 属性, 模式, 序号)。主体须紧接「的」，取最长匹配，避免把「甲·下属」认成「甲」。"""
        ents = sorted(self.entities | set(self.mem._aliases["entity"]), key=len, reverse=True)
        ent = fac = None
        for e in ents:
            m = re.search(r"(?:^|[，\s])" + re.escape(e) + r"\s*的\s*", question)
            if m:
                ent = e
                tail = question[m.end():]
                for f in sorted(self.facets, key=len, reverse=True):
                    if tail.startswith(f):
                        fac = f; break
                break
        mode = "at"
        for rx, md in QCUES:
            if rx.search(question):
                mode = md; break
        sm = SEQ.search(question)
        at = float(sm.group(1)) if sm else math.inf
        return ent, fac, mode, at

    def answer(self, question: str) -> dict:
        ent, fac, mode, at = self.parse(question)
        if not ent or not fac:
            return {"state": "absent", "value": None, "at": None, "chain": [], "parsed": False}
        if mode == "chain":
            q = Query(ent, fac, mode="chain", at=math.inf)
        elif mode == "reason":
            q = Query(ent, fac, mode="reason", at=at, event_at=at)
        else:
            q = Query(ent, fac, mode="state" if mode == "state" else "at",
                      at=at if self.time_filter else math.inf)
        out = self.mem.query(q)
        out["parsed"] = True
        return out
