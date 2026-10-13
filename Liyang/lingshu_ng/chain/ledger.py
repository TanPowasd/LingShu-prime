# -*- coding: utf-8 -*-
"""版本链账本（编年）：按「命名空间 · 实体 · 属性」登记版本事件，派生有效区间与四态。

* 一条事件＝(ns, entity, attr, op, value, alt, reason, seq, line, ref, quote)：seq＝段序号（时间轴），
  ref＝来源段的引用（引擎里是节点 id，读者里是材料 cid），line＝段内句序号，quote＝来源原文。
* 有效区间：事件 i 的值在 [seq_i, seq_{i+1}) 内有效（最后一个事件开区间到「现在」）。
* 四态（某时点 T）：T 前最后一个事件决定——set/resolve⇒active，retire⇒retired（值为空），
  unresolve⇒unresolved（两值并存），T 前无事件⇒absent。
* 同体异名：rename 事件把旧名并入新名（并查集，命名空间内）；查询任一名字都落到同一实体组。

账本本身不依赖引擎：引擎（:mod:`lingshu_ng.chain.index`）用它做持久化索引，机械读者
（:mod:`lingshu_ng.chain.reader`）用它在「只看检索材料」的条件下临时建账作答。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import anchored as _anc
from . import shorthand as _sh
from . import llm_extract as _llm
from . import sav as _sav
from . import v15 as _v15
from . import v16 as _v16
from . import v17 as _v17
from . import v18 as _v18
from . import v19 as _v19
from . import v21 as _v21
from . import v22 as _v22
from . import v23 as _v23
from . import v24 as _v24
from . import v25 as _v25
from . import v26 as _v26
from .extract import MOVE_ATTR, Event, extract, parse_header, split_sentences

__all__ = ["Rec", "Ledger", "Status", "INF"]

INF = 10 ** 9


@dataclass
class Rec:
    ns: str
    entity: str
    attr: Optional[str]
    op: str
    value: Optional[str]
    alt: Optional[str]
    reason: Optional[str]
    seq: int
    line: int
    ref: str
    quote: str
    rename_from_seq: Optional[int] = None

    @property
    def state(self) -> str:
        return {"retire": "retired", "unresolve": "unresolved"}.get(self.op, "active")


@dataclass
class Status:
    value: Optional[str]
    state: str
    at_seq: Optional[int]
    rec: Optional[Rec]


class Ledger:
    def __init__(self) -> None:
        self.recs: List[Rec] = []
        self._by_key: Dict[Tuple[str, str, str], List[Rec]] = {}
        self._parent: Dict[Tuple[str, str], Tuple[str, str]] = {}
        self._renames: List[Rec] = []
        self._ns_counter: Dict[str, int] = {}
        self._ns_max: Dict[str, int] = {}
        self._names: Dict[str, set] = {}          # ns → 出现过的实体名
        self._attrs: Dict[Tuple[str, str], set] = {}
        self._mentions: Dict[Tuple[str, str], List[Rec]] = {}   # (ns, 实体名) → 未解析提及（value 存句尾 rest）
        self._name_index: Dict[str, set] = {}    # 实体名（含别名、提及主语）→ {ns}
        self._ml = 0
        self.lex = _anc.Lexicon()                 # v9：词表锚定二次抽取的运行时锚点
        self.sinfo = _sav.AttrInfo()              # v13：属性取值形态（「S A V」抽取与取值修复用）
        self._v13_bl: Dict[str, list] = {}        # v13：ns → 未登记句待查队列（冷启动）
        self._v13_sig: Dict[str, tuple] = {}

    # ------------------------------------------------------------ 写
    def add_text(self, text: str, ref: str, seq: Optional[int] = None, ns: Optional[str] = None) -> List[Rec]:
        """登记一段原文的全部事件。seq/ns 缺省取段首「第 N … （命名空间）」；仍缺则按命名空间写入序。"""
        h = parse_header(text)
        ns = ns if ns is not None else (h.ns or "")
        if seq is None:
            seq = h.seq
        if seq is None:
            seq = self._ns_counter.get(ns, 0) + 1
        self._ns_counter[ns] = max(self._ns_counter.get(ns, 0), seq)
        out = []
        evs = extract(text)
        if _llm.ON:                                          # chain-r12 B 臂（缺省关）：可疑规则结果交受限 LLM 复核
            self._llm_refine(evs)
        if _sav.V13:                                         # v13：非严格事件的主体前缀/属性残片/取值形态修复
            v13_names, v13_attrs = self._v13_anchors(ns)
            self.sinfo.cur = v13_attrs
            keep = []
            for ev in evs:
                if ev.op not in ("mention", "rename"):
                    if not _v18.brk_ok(ev, v13_names):        # v18：方括号日志频道名不当主体（须是已知名）
                        continue
                    _sav.fix_entity(ev, None)
                    if (ev.extra.get("loose") or ev.extra.get("short")) and not _sav.repair_event(ev, ns, v13_names, v13_attrs, self.sinfo, extract):
                        continue
                    if _v15.V15:
                        _v15.fix_entity(ev)
                        _v15.fix_value(ev)
                        _v15.snap_attr(ev, v13_attrs); _v15.snap_loc(ev, v13_attrs)
                        if ev.extra.get("loose") or ev.extra.get("short"):
                            _v15.post(ev); _v15.two_vals(ev, ns, self.sinfo)
                keep.append(ev)
            evs = keep
        for ev in evs:
            if ev.op == "set" and ev.extra.get("short"):          # v10：未决之后的新值＝裁定（mem0 式更新判定；只作用于速记体事件）
                prev = self._by_key.get((ns, ev.entity, ev.attr))
                if prev and prev[-1].op == "unresolve" and _sh.decides(ev.quote):
                    ev.op = "resolve"
            out.append(self.add_event(ns, ev, seq, ref))
        done = {ev.line for ev in evs if ev.op != "mention"}
        if _anc.ANCHOR:                                    # v9：句式认不出的句子，用已登记的实体/属性/取值做锚点再试
            for i, sent in enumerate(split_sentences(text)):
                if i in done:
                    continue
                a = _anc.extract_anchored(_sh.pre_normalize(sent) if _sh.SHORT else sent, ns, self.lex, self.group)
                if a is None:
                    continue
                if _sh.SHORT and _sh.strong_cue(sent) and not _sh.anchored_ok(sent, a):
                    continue                                   # v10：速记信号句上的锚定结果先自检（残缺记号、标签词、起因当值、点分名前缀）
                if _sh.SHORT and _sh.strong_cue(sent):
                    a["value"] = _sh.norm_event_value(a["value"], a["attr"]); a["alt"] = _sh.norm_event_value(a["alt"], a["attr"])
                ev = Event(op=a["op"], entity=a["entity"], attr=a["attr"], value=a["value"], alt=a["alt"],
                           reason=a["reason"], line=i, quote=sent.strip(), extra={"anchored": True})
                if _sav.V13:
                    _sav.repair_event(ev, ns, v13_names, v13_attrs, self.sinfo, None)
                    if _v15.V15:
                        _v15.fix_value(ev); _v15.snap_attr(ev, v13_attrs); _v15.snap_loc(ev, v13_attrs)
                        _v15.post(ev); _v15.two_vals(ev, ns, self.sinfo)
                if _llm.ON:                                  # r12 B 臂第 2 轮：锚定结果同样过可疑复核
                    self._llm_refine([ev])
                out.append(self.add_event(ns, ev, seq, ref))
                done.add(i)
        ss_v13 = None
        if _sav.V13:                                       # v13：账本上下文里的「主体 属性 值」（渠道前缀/无动词/按…走）
            ss_v13 = split_sentences(text)
            self._v13_pass(ns, [(sent, i, seq, ref) for i, sent in enumerate(ss_v13) if i not in done], out, done)
        if _sav.V13 and _v15.V15:                          # v15：仍未登记且带消息体外壳的句子，去外壳后重抽一次（quote 存原句）
            self._v15_pass(ns, ss_v13, seq, ref, out, done)
        if _sav.V13 and _v16.V16 and _v16.WIN:             # v16：仍未登记的句子做账本窗口抽取（已知主体…已确认属性…合形态取值）
            self._v16_pass(ns, ss_v13, seq, ref, out, done)
        if _sav.V13 and _v18.V18 and _v18.FAM:              # v18：已知锚点下的写法覆盖（规则族见 v18.py）
            self._v18_pass(ns, ss_v13, seq, ref, out, done)
        if _sav.V13 and _v19.V19 and "K" in _v19.FAM:          # v19：ASCII 取值冷启动（规则族见 v19.py）
            self._v19_pass(ns, ss_v13, seq, ref, out, done)
        if _sav.V13 and _v21.V21 and _v21.FAM & {"G", "L", "C", "P"}:     # v21：段内仍未登记句的追加抽取（G/L，见 v21.py）
            self._v21_pass(ns, ss_v13, seq, ref, out, done)
        if _v25.FAM:                                       # v25 B：前序各路径都未登记的句子，处置句主体剥离后重抽（见 v25.py）
            b_ctx = None
            for i, sent in enumerate(ss_v13 if ss_v13 is not None else split_sentences(text)):
                if i in done or not (_v25.pre(sent) or _v25.epre(sent) or ("M" in _v26.FAM and _v26._MV.search(sent))):
                    continue
                if b_ctx is None:
                    b_names, b_attrs = self._v13_anchors(ns)
                    b_ctx = (set(b_names), set(b_attrs) | self._v16_gattrs())
                e = _v25.ba(sent, *b_ctx) if _v25.pre(sent) else None
                if e is None and _v25.epre(sent):                   # v25 E：主体与属性不相连的叙事句（见 v25.py）
                    a = _v25.ewin(self, sent, ns, sorted(b_ctx[0], key=len, reverse=True), b_ctx[1])
                    if a is not None:
                        r = Rec(ns, a["entity"], a["attr"], a["op"], a["value"], a["alt"], a["reason"], int(seq), i, ref, sent.strip(), None)
                        r._anchored = True; r._cold = bool(a.get("_cold")); r._strict = False   # 不走 v16/v19 后处理（取值已由 E 定好）；v26 C 冷启动主体只进影子锚点
                        self.add_rec(r); out.append(r); done.add(i)
                        continue
                if e is None and _v26.FAM & {"M"}:                   # v26 M：叙事迁移句（首次出现主体/地名；见 v26.py）
                    _ss = ss_v13 if ss_v13 is not None else split_sentences(text)
                    a = _v26.mwin(self, sent, ns, b_ctx[0], b_ctx[1], _ss[max(0, i - 3):i])
                    if a is not None:
                        r = Rec(ns, a["entity"], a["attr"], a["op"], a["value"], a["alt"], a["reason"], int(seq), i, ref, sent.strip(), None)
                        r._anchored = True; r._cold = bool(a.get("_cold")); r._strict = False
                        self.add_rec(r); out.append(r); done.add(i)
                        continue
                if e is None:
                    continue
                if "B1" in _v25.FAM and self._by_key.get((ns, e.entity, e.attr)):
                    continue                                   # B1（试验）：该键已有登记时不走 B
                e.line = i; e.quote = sent.strip(); e.extra = dict(e.extra or {}, v25="B")
                out.append(self.add_event(ns, e, seq, ref)); done.add(i)
        if _llm.ON:                                          # chain-r12 B 臂：有事件信号但规则/锚定都没登记的句子
            ss = split_sentences(text)
            idx = [i for i, sent in enumerate(ss) if i not in done and _llm.has_signal(sent) and self._known_in(sent, ns)]
            _llm.STATS["trig_none"] += len(idx)
            for i, r in zip(idx, _llm.run([ss[i].strip() for i in idx])):
                if isinstance(r, dict):
                    ev = Event(op=r["op"], entity=r["entity"], attr=r["attr"] or MOVE_ATTR, value=r["value"], alt=r["alt"],
                               reason=r["reason"], line=i, quote=ss[i].strip(), first=False, extra={"loose": True, "llm": True})
                    out.append(self.add_event(ns, ev, seq, ref))
                    done.add(i)
        if _sav.V13 and _sav.BACKLOG:                      # 冷启动：本段仍未登记的句子进待查队列，锚点（确认实体/属性）增长后重试
            bl = self._v13_bl.setdefault(ns, [])
            bl.extend((sent, i, seq, ref) for i, sent in enumerate(ss_v13) if i not in done and len(sent) <= 200)
            del bl[:-_sav.BACKLOG]
        return out

    def _v15_pass(self, ns: str, ss, seq, ref, out, done) -> None:
        cand = []
        pre = None
        if _v16.V16 and _v15.GATE_E:                       # v16 预检：重抽 pass 的主体门要求已知名，句中没有任何已知名就不必规范化/重抽
            pre = self._v13_anchors(ns)[0]
            if not pre:
                return
        for i, sent in enumerate(ss):
            if i in done or len(sent) > 200:
                continue
            s0 = sent.strip()
            if pre is not None and not any(x in s0 for x in pre):
                continue
            n = _v15.norm(_sh.pre_normalize(s0) if _sh.SHORT else s0)
            if n and n != s0 and n != s0.translate(_v15._TR).strip():
                cand.append((i, s0, n))
        if not cand:
            return
        names, cattrs = self._v13_anchors(ns)
        self.sinfo.cur = cattrs
        for i, s0, n in cand:
            evs = [e for e in extract(n) if e.op not in ("mention", "rename")]
            if not evs:
                if not names or not cattrs or not any(x in n for x in names):
                    continue
                self.sinfo.pairs = {(e, a) for (ns_, e), at in self.lex.attrs.items() if ns_ == ns for a in at}
                a = _sav.extract_sav(n, ns, names, self.sinfo, None)
                if a is None:
                    continue
                prev = self._by_key.get((ns, a["entity"], a["attr"]))
                if a["op"] == "set" and prev and prev[-1].op == "unresolve" and prev[-1].seq <= seq and _v25.decides(prev[-1], a["value"], n, _sav._DECIDE):
                    a["op"] = "resolve"
                evs = [Event(op=a["op"], entity=a["entity"], attr=a["attr"], value=a["value"], alt=a["alt"], reason=a["reason"],
                             line=i, quote=s0, extra={"anchored": True, "sav": True})]
            ev = evs[0]
            ev.line, ev.quote = i, s0
            ev.extra = dict(ev.extra or {}, loose=True, v15=True)
            if not _sav.repair_event(ev, ns, names, cattrs, self.sinfo, None):
                continue
            _v15.fix_entity(ev, names); _v15.fix_value(ev)
            _v15.snap_attr(ev, cattrs); _v15.snap_loc(ev, cattrs); _v15.post(ev); _v15.two_vals(ev, ns, self.sinfo)
            if not ev.entity or (ev.attr is not None and not ev.attr) or ev.entity == ev.attr:
                continue
            ga = _v15.GATE_A
            aok = ga == "off" or ev.attr in cattrs or (ga == "reg" and ev.attr in self.sinfo.attrs.get(ns, ()))
            if (_v15.GATE_E and not _v15.known_entity(ev, names)) or not aok \
                    or any(v and re.fullmatch(r"[\u4e00-\u9fff]", v) for v in (ev.value, ev.alt)) \
                    or not _v15.shape_ok(ev, self.sinfo.want(ns, ev.attr) if ev.attr else set()):
                continue                                   # 主体须已知、属性须已确认、取值不为单字：宁漏不错
            if _llm.ON:
                self._llm_refine([ev])
            out.append(self.add_event(ns, ev, seq, ref))
            done.add(i)

    def _v16_pass(self, ns: str, ss, seq, ref, out, done) -> None:
        names = cattrs = None
        for i, sent in enumerate(ss):
            if i in done or len(sent) > 200:
                continue
            if names is None:
                names, cattrs = self._v13_anchors(ns)
                if not names or not cattrs:
                    return
                self.sinfo.cur = cattrs
                self.sinfo.pairs = {(e, a) for (ns_, e), at in self.lex.attrs.items() if ns_ == ns for a in at}
                if _v16.GLOB:                              # v16：属性/取值锚点放宽到全账本（其他命名空间确认过的属性），取值门不变
                    cattrs = set(cattrs) | self._v16_gattrs()
                attrs2 = [a for a in cattrs if a != "位置" and len(a) >= 2]
                loc_ok = "位置" in cattrs
            if not any(a in sent for a in attrs2) and not loc_ok and not _v17.loc_cue(sent, names):
                continue
            if not any(n in sent for n in names):
                continue
            a = _v16.extract_win(self, sent, ns, names, cattrs)
            if a is not None and not _v17.win_ok(sent, a):     # v17：收紧窗口抽取（表格行 / 取值含属性名 / 作废词远离属性）
                a = None
            if a is None:
                continue
            ev = Event(op=a["op"], entity=a["entity"], attr=a["attr"], value=a["value"], alt=a["alt"], reason=a["reason"],
                       line=i, quote=sent.strip(), extra={"anchored": True, "sav": True, "v16": True})
            if _llm.ON:
                self._llm_refine([ev])
            out.append(self.add_event(ns, ev, seq, ref))
            done.add(i)

    def _v18_pass(self, ns: str, ss, seq, ref, out, done) -> None:
        names = cattrs = None
        for i, sent in enumerate(ss):
            if i in done or len(sent) > 200:
                continue
            if names is None:
                names, cattrs = self._v13_anchors(ns)
                if not names:
                    return
                cattrs = set(cattrs) | self._v16_gattrs()
                if not cattrs:
                    return
            nm = names
            if not any(n in sent for n in names):
                if "E" not in _v18.FAM:
                    continue
                x = _v18.cold_entity(sent, names, cattrs, _v18.allvals(self))
                if not x:
                    continue
                nm = [x] + list(names)
            a = _v18.recall(self, sent, ns, nm, cattrs, lambda e, at: (self._by_key.get((ns, e, at)) or [None])[-1])
            if a is None and nm is not names:
                a = _v16.extract_win(self, sent, ns, nm, cattrs)
                if a is not None and (not _v17.win_ok(sent, a) or a.get("entity") != nm[0]):
                    a = None
                if a is not None:
                    a["fam"] = "E"
            if a is None:
                continue
            ev = Event(op=a["op"], entity=a["entity"], attr=a["attr"], value=a["value"], alt=a["alt"], reason=a["reason"],
                       line=i, quote=sent.strip(), extra={"anchored": True, "sav": True, "v18": a["fam"]})
            if _llm.ON:
                self._llm_refine([ev])
            out.append(self.add_event(ns, ev, seq, ref))
            done.add(i)

    def _v19_pass(self, ns: str, ss, seq, ref, out, done) -> None:
        names = cattrs = None
        for i, sent in enumerate(ss):
            if i in done or len(sent) > 200:
                continue
            if names is None:
                names, cattrs = self._v13_anchors(ns)
                if not names:
                    return
                cattrs = set(cattrs) | self._v16_gattrs()
            if not any(n in sent for n in names):
                continue
            a = _v19.cold_ascii(self, ns, sent, names, cattrs, lambda e, at: (self._by_key.get((ns, e, at)) or [None])[-1])
            if a is None:
                continue
            ev = Event(op=a["op"], entity=a["entity"], attr=a["attr"], value=a["value"], alt=a["alt"], reason=a["reason"],
                       line=i, quote=sent.strip(), extra={"anchored": True, "sav": True, "v19": a["fam"]})
            out.append(self.add_event(ns, ev, seq, ref))
            done.add(i)

    def _v16_gattrs(self) -> set:
        g = set()
        for (_ns, _e), at in self.lex.attrs.items():
            g |= at
        for _ns, at in self.sinfo.attrs.items():
            g |= {a for a in at if self.sinfo.acnt.get((_ns, a), 0) >= _sav.ATTR_MIN}
        return {a for a in g if a and len(a) >= 2}

    def _v13_anchors(self, ns: str):
        if _v16.V16:                                       # v16：锚点只随新记录变化，按（ns, 记录数）缓存
            k = (ns, len(self.recs))
            c = self.__dict__.get("_anc_cache")
            if c and c[0] == k:
                return c[1]
            r = self._v13_anchors0(ns)
            self._anc_cache = (k, r)
            return r
        return self._v13_anchors0(ns)

    def _v13_anchors0(self, ns: str):
        names = sorted({n for n in self._names.get(ns, ()) if n and len(n) >= 2} | {n for n in self.lex.names.get(ns, set()) if len(n) >= 2},
                       key=len, reverse=True)
        cattrs = set()
        for (ns_, _e), at in self.lex.attrs.items():
            if ns_ == ns:
                cattrs |= at
        cattrs |= {a for a in self.sinfo.attrs.get(ns, ()) if self.sinfo.acnt.get((ns, a), 0) >= _sav.ATTR_MIN}
        return names, cattrs

    def _v13_pass(self, ns: str, items, out, done) -> None:
        """v13：只用「确认过」的锚点（lex 确认实体/属性 ∪ 句式路径登记≥ATTR_MIN 的属性）；锚定/SAV 结果不回灌锚点。
        先重试本命名空间待查队列（锚点自上次以来有增长时），再处理本段。"""
        names, cattrs = self._v13_anchors(ns)
        if not names or not cattrs:
            return
        self.sinfo.cur = cattrs
        self.sinfo.pairs = {(e, a) for (ns_, e), at in self.lex.attrs.items() if ns_ == ns for a in at}
        sig = (len(names), len(cattrs), sum(sum(d.values()) for (n_, _a), d in self.sinfo.shapes.items() if n_ == ns))
        bl = self._v13_bl.get(ns)
        if bl and self._v13_sig.get(ns) != sig:
            keep = []
            ctx = None
            if _v21.V21 and _v21.FAM & {"B", "G", "L", "C", "P"}:
                bsig = (len(names), len(cattrs))               # 提速：v21 重试只在主体/属性锚点集变化后的那次扫描里做
                bs = self.__dict__.setdefault("_v21_bsig", {})
                if not _v21.SIG or bs.get(ns) != bsig:
                    bs[ns] = bsig
                    ctx = (names, set(cattrs) | self._v16_gattrs())
            for it in bl:
                if not self._v13_one(ns, it, out, names) and not (ctx is not None and self._v21_retry(ns, it, out, ctx)):
                    keep.append(it)
            bl[:] = keep
        self._v13_sig[ns] = sig
        for it in items:
            if self._v13_one(ns, it, out, names):
                done.add(it[1])

    def _v13_one(self, ns: str, it, out, names) -> bool:
        sent, i, seq, ref = it
        if not any(n in sent for n in names):
            return False
        a = _sav.extract_sav(sent, ns, names, self.sinfo, None)
        if a is None:
            return False
        prev = self._by_key.get((ns, a["entity"], a["attr"]))
        if a["op"] == "set" and prev and prev[-1].op == "unresolve" and prev[-1].seq <= seq and _v25.decides(prev[-1], a["value"], sent, _sav._DECIDE):
            a["op"] = "resolve"
        ev = Event(op=a["op"], entity=a["entity"], attr=a["attr"], value=a["value"], alt=a["alt"],
                   reason=a["reason"], line=i, quote=sent.strip(), extra={"anchored": True, "sav": True})
        if _v15.V15:
            _v15.post(ev)
        if _llm.ON:
            self._llm_refine([ev])
        out.append(self.add_event(ns, ev, seq, ref))
        return True

    def _v21_pass(self, ns: str, ss, seq, ref, out, done) -> None:
        names = cattrs = None
        for i, sent in enumerate(ss):
            if i in done or len(sent) > 200:
                continue
            if names is None:
                names, cattrs = self._v13_anchors(ns)
                if not names:
                    return
                cattrs = set(cattrs) | self._v16_gattrs()
            cold_only = not any(n in sent for n in names) and "C" not in _v21.FAM
            cgo = _v22.FAM & {"N", "U"} and _v22.cold_pre(sent)
            nar = _v24.FAM & {"N", "Q", "P"} and _v24.narr_pre(sent)
            if cold_only and not cgo and not nar:
                continue
            a = None
            if not cold_only or cgo:
                a = _v22.more_cold(self, sent, ns, names, cattrs) if cold_only else _v21.more(self, sent, ns, names, cattrs)
                if not cold_only and _v23.FAM and (a is None or not _v21.retry_ok(self, ns, a, a.get("_names") or names, sent)):
                    a = _v23.more(self, sent, ns, names, cattrs)          # v23：前序族未中或被 retry 门拒时再试（见 v23.py）
                a = _v24.filt(a)                                          # v24 K：主体形态门
                if a is not None and not _v21.retry_ok(self, ns, a, a.get("_names") or names, sent):
                    a = None
            if a is None and nar:                                         # v24 N：叙事句「主体的属性 + 承接词 + 取值」
                a = _v24.filt(_v24.more(self, sent, ns, names, cattrs))
                if a is not None and not _v24.gate_ok(self, ns, a, a.get("_names") or names, sent):
                    a = None
            if a is None:
                continue
            prior = sorted((r for r in (self._by_key.get((ns, a["entity"], a["attr"])) or []) if r.seq <= seq), key=lambda r: (r.seq, r.line))
            if not _v21.retry_keep(a, prior) and not a.get("_disp"):
                continue
            ev = Event(op=a["op"], entity=a["entity"], attr=a["attr"], value=a["value"], alt=a["alt"], reason=a["reason"],
                       line=i, quote=sent.strip(), extra={"anchored": True, "sav": True, "v21": a["fam"]})
            rec = self.add_event(ns, ev, seq, ref)
            if a.get("op_v21"):
                rec.op = a["op_v21"]
            _v21.retry_op(rec, prior, sent)
            out.append(rec)
            done.add(i)

    def _v21_retry(self, ns: str, it, out, ctx) -> bool:
        """v21 B：待查队列句锚点增长后，SAV 不中再走 v16 窗口抽取（v17 收紧门同 v16 pass），再走 G/P/L/C。"""
        sent, i, seq, ref = it
        names, cattrs = ctx
        cold_only = not any(n in sent for n in names) and "C" not in _v21.FAM
        cgo = _v22.FAM & {"N", "U"} and _v22.cold_pre(sent)
        nar = _v24.FAM & {"N", "Q", "P"} and _v24.narr_pre(sent)
        if cold_only and not cgo and not nar:
            return False
        if cold_only and not cgo:
            a = None
        elif cold_only:                                    # v22 提速：句中无已知名时只走冷启动路径（其余族都要求已知名）
            a = _v22.more_cold(self, sent, ns, names, cattrs)
        else:
            a = _v16.extract_win(self, sent, ns, names, cattrs) if "B" in _v21.FAM else None
            if a is not None and not _v17.win_ok(sent, a):
                a = None
            if a is None:
                a = _v21.more(self, sent, ns, names, cattrs)
            if _v23.FAM and (a is None or not _v21.retry_ok(self, ns, a, a.get("_names") or names, sent)):
                a = _v23.more(self, sent, ns, names, cattrs)          # v23：前序族未中或被 retry 门拒时再试
        a = _v24.filt(a)                                              # v24 K：主体形态门
        if a is not None and not _v21.retry_ok(self, ns, a, a.get("_names") or names, sent):
            a = None
        if a is None and nar:                                         # v24 N：叙事句
            a = _v24.filt(_v24.more(self, sent, ns, names, cattrs))
            if a is not None and not _v24.gate_ok(self, ns, a, a.get("_names") or names, sent):
                a = None
        if a is None:
            return False
        ev = Event(op=a["op"], entity=a["entity"], attr=a["attr"], value=a["value"], alt=a["alt"], reason=a["reason"],
                   line=i, quote=sent.strip(), extra={"anchored": True, "sav": True, "v16": True, "v21": a.get("fam", "B")})
        prior = sorted((r for r in (self._by_key.get((ns, a["entity"], a["attr"])) or []) if r.seq <= seq), key=lambda r: (r.seq, r.line))
        if not _v21.retry_keep(a, prior) and not a.get("_disp"):
            return False
        rec = self.add_event(ns, ev, seq, ref)
        if a.get("op_v21"):
            rec.op = a["op_v21"]
        _v21.retry_op(rec, prior, sent)
        out.append(rec)
        return True

    def _known_in(self, sent: str, ns: str) -> bool:
        """B 臂触发门：句中出现本命名空间里已登记过事件的实体名（≥2 字）。散文/对话语料里极少命中，控制调用量与误登记。"""
        if _llm.GATE == "ea2":                             # 实体名 + 本命名空间任一已登记属性
            if not any(len(n) >= 2 and n in sent for n in self._names.get(ns, ())):
                return False
            ats = set().union(*[a for (ns_, _), a in self._attrs.items() if ns_ == ns] or [set()])
            return any(a and len(a) >= 2 and a != MOVE_ATTR and a in sent for a in ats) or (MOVE_ATTR in ats and _llm.move_signal(sent))
        if _llm.GATE == "ea":                              # 实体名 + 该实体已登记过的属性（位置属性只需移动类信号）同句出现
            for n in self._names.get(ns, ()):
                if len(n) >= 2 and n in sent:
                    at = self._attrs.get((ns, n), set())
                    if any(a and len(a) >= 2 and a != MOVE_ATTR and a in sent for a in at) or (MOVE_ATTR in at and _llm.move_signal(sent)):
                        return True
            return False
        names = self._names.get(ns, ()) if _llm.GATE == "names" else [n for n, s_ in self._name_index.items() if ns in s_]
        return any(len(n) >= 2 and n in sent for n in names)

    def _llm_refine(self, evs) -> None:
        """B 臂：有事件信号且结果可疑的规则事件，LLM 输出过校验就替换，否则保留规则结果。"""
        c = [ev for ev in evs if ev.op not in ("mention", "rename") and _llm.suspicious(ev)]     # 规则已认出事件＝有事件信号
        _llm.STATS["trig_susp"] += len(c)
        for ev, r in zip(c, _llm.run([ev.quote for ev in c])):
            if isinstance(r, dict):
                ev.op, ev.entity, ev.attr, ev.value, ev.alt = r["op"], r["entity"], r["attr"] or MOVE_ATTR, r["value"], r["alt"]
                ev.reason = r["reason"] or ev.reason
                ev.extra = dict(ev.extra or {}, loose=True, llm=True)

    def add_event(self, ns: str, ev: Event, seq: int, ref: str) -> Rec:
        if _v16.V16 and _sav.V13 and ev.op not in ("mention", "rename") and not ev.extra.get("llm"):
            nonstrict = bool(ev.extra.get("loose") or ev.extra.get("short") or ev.extra.get("anchored"))
            if nonstrict or _v16.STRICT:
                names, cattrs = self._v13_anchors(ns)
                _v16.post(self, ev, ns, names, cattrs, strict=not nonstrict)
        if _v19.V19 and _v19.FAM and _sav.V13 and ev.op not in ("mention", "rename") and not ev.extra.get("llm"):
            if _v19.SCOPE == "all" or ev.extra.get("loose") or ev.extra.get("short") or ev.extra.get("anchored"):
                _n, _c = self._v13_anchors(ns)
                _v19.apply(self, ev, ns, _n, (set(_c) | self._v16_gattrs()) if ("A" in _v19.FAM) else None)
        _v26cold = False
        if _v26.FAM:
            _v26.tidy(self, ev, ns)                                          # v26 T：属性/取值粘连修整
        if _v26.FAM and ev.op not in ("mention", "rename") and _v26.frame(ev.entity):
            rc = _v26.recover(self, ev, ns)                                  # v26 R：框架主体 ⇒ 句中唯一名称候选
            if rc is not None:
                ev.entity = rc[0]; _v26cold = not rc[1]
        if (_v24.FAM and ev.op not in ("mention", "rename") and _v24.drop_base(ev)) or (_v26.FAM and _v26.drop(ev)):
            ev.op = "mention"; ev.extra["rest"] = None; ev.extra["v24_drop"] = True     # v24 G：主体修复后仍不合名称形态 ⇒ 不登记（句子留给锚定/窗口路径重试）
            return Rec(ns, ev.entity, ev.attr, "mention", None, None, ev.reason, int(seq), ev.line, ref, ev.quote, ev.rename_from_seq)
        r = Rec(ns, ev.entity, ev.attr, ev.op, ev.extra.get("rest") if ev.op == "mention" else ev.value, ev.alt,
                ev.reason, int(seq), ev.line, ref, ev.quote, ev.rename_from_seq)
        r._anchored = bool(ev.extra.get("anchored"))                       # 不持久化：只影响本进程的锚点学习
        r._cold = (bool(_v22.FAM & {"P", "Q"}) and ev.extra.get("v21") in ("N", "U")) or ("H" in _v23.FAM and ev.extra.get("v21") == "S")   # v23 H：S 冷启动主体同样暂不入锚点。 v22 P/Q：冷启动主体暂不入锚点名（Q：同名冷启动 ≥2 条后转正）
        if "S" in _v25.FAM and ev.extra.get("v25") == "B":
            r._cold = True                                                     # v25 S：B 的冷启动主体只进只读影子锚点（不入 _names，不供其他族用）
        if _v26cold:
            r._cold = True                                                     # v26 R：自举出的首次出现主体只进只读影子锚点
        r._strict = not ev.extra.get("loose") and not r._anchored
        if ev.extra.get("v15") and _v15.LEARN != "full":
            r._anchored = True; r._v15 = True                                 # v15 重抽事件：只把（主体, 属性）喂给锚点，不喂取值/形态
        self.add_rec(r)
        return r

    def _note_name(self, ns: str, n: Optional[str]) -> None:
        if n:
            self._name_index.setdefault(n, set()).add(ns)
            self._ml = max(self._ml, len(n))

    def _attrs_names(self, ns: str, n: str) -> set:
        return self._attrs.get((ns, n), set())

    def _maxlen(self) -> int:
        return self._ml

    def add_rec(self, r: Rec) -> None:
        if getattr(r, "_cold", False):
            k = (r.ns, r.entity)
            cc = self.__dict__.setdefault("_v22_cold", {})
            cc[k] = cc.get(k, 0) + 1
            if not ("Q" in _v22.FAM and cc[k] >= 2) and r.entity not in self._names.get(r.ns, ()):
                self.recs.append(r)
                self._ns_max[r.ns] = max(self._ns_max.get(r.ns, 0), r.seq)
                self._by_key.setdefault((r.ns, r.entity, r.attr), []).append(r)
                self._attrs.setdefault((r.ns, r.entity), set()).add(r.attr)
                return
        if r.op == "mention":
            self._mentions.setdefault((r.ns, r.entity), []).append(r)
            self._note_name(r.ns, r.entity)
            return
        self._note_name(r.ns, r.entity)
        if r.op == "rename":
            self._note_name(r.ns, r.value)
        self.recs.append(r)
        self._ns_max[r.ns] = max(self._ns_max.get(r.ns, 0), r.seq)
        self._names.setdefault(r.ns, set()).add(r.entity)
        if r.op == "rename":
            self._renames.append(r)
            if r.value:
                self._names[r.ns].add(r.value)
                self._union((r.ns, r.entity), (r.ns, r.value))
            return
        self._by_key.setdefault((r.ns, r.entity, r.attr), []).append(r)
        self._attrs.setdefault((r.ns, r.entity), set()).add(r.attr)
        if _sav.V13 and not getattr(r, "_anchored", False):
            self.sinfo.note(r.ns, r.attr, r.value, r.alt)
        if not getattr(r, "_anchored", False):
            self.lex.learn(r.ns, r.entity, r.attr, r.value, r.alt, strict=getattr(r, "_strict", False))
        elif getattr(r, "_v15", False) and _v15.LEARN == "ea":
            self.lex.learn(r.ns, r.entity, r.attr)

    # ------------------------------------------------------------ 别名
    def _find(self, x):
        while self._parent.get(x, x) != x:
            x = self._parent[x]
        return x

    def _union(self, a, b) -> None:
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            self._parent[ra] = rb          # 新名作根

    def group(self, ns: str, name: str) -> List[str]:
        root = self._find((ns, name))
        return sorted(n for n in self._names.get(ns, ()) if self._find((ns, n)) == root)

    def rename_recs(self, ns: str, name: str) -> List[Rec]:
        g = set(self.group(ns, name))
        return [r for r in self._renames if r.ns == ns and (r.entity in g or r.value in g)]

    # ------------------------------------------------------------ 读
    def namespaces(self) -> List[str]:
        return sorted(self._names)

    def max_seq(self, ns: str) -> int:
        return self._ns_max.get(ns, 0)

    def attrs_of(self, ns: str, names: Iterable[str]) -> set:
        out = set()
        for n in names:
            out |= self._attrs.get((ns, n), set())
        return out

    def events(self, ns: str, name: str, attr: str) -> List[Rec]:
        """实体组（含别名）在某属性上的全部事件，按 (seq, line) 编年。"""
        out = []
        for n in self.group(ns, name):
            out.extend(self._by_key.get((ns, n, attr), ()))
        # 同一 (seq, ref, line) 的重复登记（同段重复写入）去重
        seen, uniq = set(), []
        for r in sorted(out, key=lambda r: (r.seq, r.line, r.ref)):
            k = (r.seq, r.line, r.quote)
            if k not in seen:
                seen.add(k)
                uniq.append(r)
        return uniq

    def mention_attr(self, ns: str, name: str, text_after: str) -> str:
        """属性未登记时，用题面「<实体> 的…」与该实体各未解析提及句尾的最长公共前缀（≥2 字）猜属性。"""
        q = text_after.lstrip().lstrip("的").lstrip()
        best = ""
        for n in self.group(ns, name) or [name]:
            for r in self._mentions.get((ns, n), ()):
                rest, k = r.value or "", 0
                while k < min(len(q), len(rest)) and q[k] == rest[k]:
                    k += 1
                if k >= 2 and k > len(best):
                    best = q[:k]
        return best

    def mentions(self, ns: str, name: str, attr: str) -> List[Rec]:
        """实体组在某属性上的未解析提及（句子以「<实体> 的<属性>」开头但不在句式表内），按 (seq, line) 编年。"""
        out = []
        for n in self.group(ns, name) or [name]:
            out.extend(r for r in self._mentions.get((ns, n), ()) if attr and (r.value or "").startswith(attr))
        return sorted(out, key=lambda r: (r.seq, r.line))

    @staticmethod
    def status_at(evs: Sequence[Rec], T: int) -> Status:
        last = None
        for r in evs:
            if r.seq <= T:
                last = r
        if last is None:
            return Status(None, "absent", None, None)
        return Status(None if last.op == "retire" else last.value, last.state, last.seq, last)

    @staticmethod
    def timeline(evs: Sequence[Rec], T: int = INF) -> List[dict]:
        """变更链：[{seq, from, to, op, state, alt, reason, ref, line, quote}]（from＝上一事件的值，链式追踪）。"""
        rows, prev = [], None
        for r in evs:
            if r.seq > T:
                break
            to = None if r.op == "retire" else r.value
            rows.append({"seq": r.seq, "from": prev, "to": to, "op": r.op, "state": r.state, "alt": r.alt,
                         "reason": r.reason, "ref": r.ref, "line": r.line, "quote": r.quote})
            prev = to
        return rows

    # ------------------------------------------------------------ 定位（题面 → 账本键）
    def locate(self, text: str) -> Optional[Tuple[str, str, str]]:
        """在一句话里找「实体（最长匹配、且不是更长实体名的前缀）+ 该实体组已登记的属性（最长匹配）」。
        返回 (ns, 实体名, 属性)；找到实体但属性未登记时返回 (ns, 实体名, 题面里的属性猜测或 '')。
        同名实体落在多个命名空间时按 :meth:`locate_all` 的消歧打分取第一名。"""
        c = self.locate_all(text)
        return c[0] if c else None

    def _name_span(self, text: str):
        best = None
        maxlen = self._maxlen()
        n_q = len(text)
        for i in range(n_q):                      # 题面子串查名字表：与登记的实体数无关，O(|题面|·最长名)
            for j in range(min(n_q, i + maxlen), i, -1):
                nss = self._name_index.get(text[i:j])
                if not nss:
                    continue
                if text[j:j + 1] in ("·", "・", "."):
                    continue                       # 「甲·下属」不算「甲」
                if best is None or j - i > best[1] - best[0]:
                    best = (i, j)
                break
        return best

    def _attr_in(self, ns: str, n: str, tail: str) -> str:
        for a in sorted(self.attrs_of(ns, self.group(ns, n)), key=len, reverse=True):
            if a and a in tail:
                return a
        return ""

    def locate_all(self, text: str, T: Optional[int] = None) -> List[Tuple[str, str, str]]:
        return [c for _, c in self._cands(text, T)]

    def _cands(self, text: str, T: Optional[int] = None) -> List[Tuple[int, Tuple[str, str, str]]]:
        """题面 → 候选 [(ns, 实体名, 属性)]，按消歧打分降序；只有一个命名空间登记过该名时就一个候选。

        跨命名空间同名消歧（零 LLM，只用题面）：
          · 命名空间线索：题面里出现该命名空间名（不与实体名所在位置重叠、也不是另一候选命名空间名里的子串）＋2；
          · 该实体组在此命名空间登记过题面里的属性 ＋1；
          · 题面时点 T 超出该命名空间已知最大序号 −1。
        打分并列的候选按「该名在此命名空间登记过的属性数」再按名字序排（与 v5 的单一选择相同），
        并列本身由 :meth:`ambiguous` 报告，调用方据此决定是否同时交出多个命名空间的版本。"""
        sp = self._name_span(text)
        if sp is None:
            return []
        i, j = sp
        n = text[i:j]
        nss = sorted(self._name_index.get(n, ()))
        tail = text[j:]
        if len(nss) == 1:
            ns = nss[0]
            return [(0, (ns, n, self._attr_in(ns, n, tail)))]
        occ = {}
        for ns in nss:
            if not ns:
                continue
            k = text.find(ns)
            spans = []
            while k >= 0:
                if k + len(ns) <= i or k >= j:     # 与实体名位置不重叠
                    spans.append((k, k + len(ns)))
                k = text.find(ns, k + 1)
            occ[ns] = spans
        def covered(ns, a, b):                     # 被更长的另一候选命名空间名的出现覆盖
            return any(o != ns and len(o) > len(ns) and any(x <= a and b <= y for x, y in occ.get(o, ())) for o in occ)
        scored = []
        for ns in nss:
            sc = 0
            if any(not covered(ns, a, b) for a, b in occ.get(ns, ())):
                sc += 2
            attr = self._attr_in(ns, n, tail)
            if attr:
                sc += 1
            if T is not None and T > self.max_seq(ns):
                sc -= 1
            scored.append((-sc, -len(self._attrs_names(ns, n)), ns, attr))
        scored.sort()
        return [(-a, (ns, n, attr)) for a, _, ns, attr in scored]

    def ambiguous(self, text: str, T: Optional[int] = None) -> List[Tuple[str, str, str]]:
        """消歧打分并列第一的候选（≥2 个才算有歧义；否则返回 []）。"""
        c = self._cands(text, T)
        top = [x for sc, x in c if c and sc == c[0][0]]
        return top if len(top) > 1 else []

    def locate_tail(self, text: str, name: str) -> str:
        i = text.find(name)
        return text[i + len(name):] if i >= 0 else ""
