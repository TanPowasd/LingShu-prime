# -*- coding: utf-8 -*-
"""账本作答（机械读者，零 LLM）与召回编排。

``answer(ledger, question)``：题面 → 结构化答案
  {value, state, at_seq, chain:[{seq,from,to}], basis:[{file,line,quote}], confidence, route}
  · 现值/时点/历史/状态：时点 T 前最后一个事件（有效区间覆盖 T 的版本）；
  · 变更：编年事件链（from＝上一版本值）；
  · 缘由：T 处事件随账的缘由原文；
  · 实体或属性未登记 ⇒ absent。
``read_material(question, material)``：只用给定材料（[{cid,text}]）临时建账再作答——同一个读者可接在任何
检索臂后面，用来比较「材料里有没有正确版本」。cid 形如 ``doc#seq`` 时以 seq 为时间轴。
``plan(ledger, question)``：召回编排——当前（时点）版本段优先，其次别名声明段，再按时间顺序补变更链段。"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .ledger import INF, Ledger, Rec
from .route import route

__all__ = ["answer", "read_material", "plan"]


def _resolve(ledger: Ledger, question: str, with_attr: bool = False, ns_force: Optional[str] = None):
    r = route(question)
    cands = ledger.locate_all(question, r.T if r.intent != "change" else None)
    if ns_force is not None:
        cands = [c for c in cands if c[0] == ns_force] or cands
    loc = cands[0] if cands else None
    if loc is None:
        return (r, None, None, [], "") if with_attr else (r, None, None, [])
    ns, name, attr = loc
    evs = ledger.events(ns, name, attr) if attr else []
    if with_attr:
        if not attr:
            attr = ledger.mention_attr(ns, name, ledger.locate_tail(question, name))
        return r, ns, name, evs, attr
    return r, ns, name, evs


def _ambiguous_ns(ledger: Ledger, question: str) -> List[str]:
    r = route(question)
    return [c[0] for c in ledger.ambiguous(question, r.T if r.intent != "change" else None)]


def answer(ledger: Ledger, question: str, label=None, ns_pref: Optional[List[str]] = None) -> Dict:
    """label(rec) → (file, line)：依据轴的片段标识；缺省 (rec.ref, rec.seq)。
    题面里的实体名落在多个命名空间且题面无法消歧时：confidence='ambiguous'，candidates 列出各命名空间的值；
    主答案取 ns_pref（如基础召回里先出现的命名空间）里靠前者。"""
    label = label or (lambda rec: (rec.ref, rec.seq))
    amb = _ambiguous_ns(ledger, question)
    if amb and ns_pref is not None:
        amb = sorted(amb, key=lambda x: (ns_pref.index(x) if x in ns_pref else len(ns_pref), x))
    out = _answer_one(ledger, question, label, amb[0] if amb else None)
    if amb:
        out["confidence"] = "ambiguous"
        out["candidates"] = []
        for ns in amb:
            o = _answer_one(ledger, question, label, ns)
            out["candidates"].append({"namespace": ns, "value": o["value"], "state": o["state"], "at_seq": o["at_seq"]})
    return out


def _answer_one(ledger: Ledger, question: str, label, ns_force: Optional[str]) -> Dict:
    r, ns, name, evs = _resolve(ledger, question, ns_force=ns_force)
    out = {"value": None, "state": "absent", "at_seq": None, "chain": [], "basis": [], "confidence": "unknown",
           "route": r.intent}
    if not evs:
        return out
    T = r.T if r.T is not None else max(ledger.max_seq(ns), max(e.seq for e in evs))
    st = Ledger.status_at(evs, T)
    basis_recs: List[Rec] = []
    if r.intent == "change":
        tl = Ledger.timeline(evs, INF)
        out["chain"] = [{"seq": x["seq"], "from": x["from"], "to": x["to"]} for x in tl]
        st = Ledger.status_at(evs, INF)
        basis_recs = [e for e in evs][-3:]
    if r.intent == "reason":
        at = [e for e in evs if e.seq == T]
        rec = at[-1] if at else st.rec
        out.update(value=rec.reason if rec is not None else None, state=st.state, at_seq=T if at else st.at_seq,
                   confidence="certain" if (at and rec.reason) else "unknown")
        if rec is not None:
            basis_recs = [rec]
    else:
        out.update(value=st.value, state=st.state, at_seq=st.at_seq,
                   confidence="certain" if st.rec is not None else "unknown")
        if st.rec is not None:
            if st.rec.alt:
                out["alt"] = st.rec.alt
            basis_recs = [st.rec] + [b for b in basis_recs if b is not st.rec]
    seen = set()
    for b in basis_recs[:3]:
        f, line = label(b)
        if (f, b.quote) in seen:
            continue
        seen.add((f, b.quote))
        out["basis"].append({"file": f, "line": line, "quote": b.quote})
    return out


def read_material(question: str, material: Sequence[Dict]) -> Dict:
    led = Ledger()
    for m in material:
        cid = str(m.get("cid", ""))
        seq = None
        if "#" in cid and cid.rsplit("#", 1)[1].isdigit():
            seq = int(cid.rsplit("#", 1)[1])
        led.add_text(m.get("text") or "", ref=cid, seq=seq)
    return answer(led, question)


def plan(ledger: Ledger, question: str, order: str = "chrono", co=None, ns_pref: Optional[List[str]] = None) -> List[str]:
    """召回编排：返回来源引用（去重、按优先级）。题面落不到账本键时返回 []（交还基础召回）。

    order='chrono'：版本段 → 别名段 → 变更链段按时间正序；'near'：变更链段按与时点的远近。
    时点类问（历史/时点/状态/缘由）只补时点及以前的事件段（不把「未来」版本交给读者）。
    co(ns, names, attr, lo, hi) → [(ref, seq)]：可选的「共现守卫」——在同命名空间 seq∈(lo, hi] 的段里找同句共现
    实体名与属性名却没解析成事件的段（账本可能漏掉的更新版本），这些段排在账本当前版本之前。"""
    amb = _ambiguous_ns(ledger, question)
    if amb:
        if ns_pref is not None:
            amb = sorted(amb, key=lambda x: (ns_pref.index(x) if x in ns_pref else len(ns_pref), x))
        lists = [_plan_one(ledger, question, order, co, ns) for ns in amb]
        out: List[str] = []
        for k in range(max(len(x) for x in lists)):     # 各命名空间的编排段交错（先 ns_pref 靠前者）
            for x in lists:
                if k < len(x) and x[k] not in out:
                    out.append(x[k])
        return out
    return _plan_one(ledger, question, order, co, None)


def _plan_one(ledger: Ledger, question: str, order: str, co, ns_force: Optional[str]) -> List[str]:
    r, ns, name, evs, attr = _resolve(ledger, question, with_attr=True, ns_force=ns_force)
    if not evs:
        # 账本里没有已解析事件：退而用「<实体> 的<属性>」未解析提及当时间标记（最新的时点前提及段优先）
        ms = ledger.mentions(ns, name, attr) if (ns is not None and attr) else []
        if not ms:
            return []
        T = r.T if (r.T is not None and r.intent != "change") else INF
        past = [m for m in ms if m.seq <= T]
        if r.intent == "change":
            seq_ = [past[-1]] + past[:-1] if past else []
        else:
            seq_ = sorted(past, key=lambda m: -m.seq)
        out: List[str] = []
        for m in seq_:
            if m.ref not in out:
                out.append(m.ref)
        return out
    T = r.T if (r.T is not None and r.intent != "change") else INF
    st = Ledger.status_at(evs, T)
    refs: List[str] = []

    def push(x: Optional[str]):
        if x and x not in refs:
            refs.append(x)
    # 账本可能漏版本：时点前、晚于账本当前版本的「未解析提及」段先交出（最新在前）——它们可能才是真正的当前版本
    g = st.rec.seq if st.rec is not None else -1
    for m in sorted((m for m in ledger.mentions(ns, name, attr) if g < m.seq <= T), key=lambda m: -m.seq)[:2]:
        push(m.ref)
    if co is not None and r.intent != "change" and attr:
        for ref, _ in sorted(co(ns, ledger.group(ns, name), attr, g, T), key=lambda x: -x[1])[:2]:
            push(ref)
    if r.intent == "reason" and r.T is not None:
        for e in evs:
            if e.seq == r.T:
                push(e.ref)
    if st.rec is not None:
        push(st.rec.ref)
    for rr in ledger.rename_recs(ns, name):
        push(rr.ref)
    # 变更链段：已解析事件、未解析提及（与变更问的共现段）合并编年（抽取漏掉的版本句仍按时间补进来）
    past = [(e.seq, e.line, e.ref) for e in evs if e.seq <= T] + \
        [(m.seq, m.line, m.ref) for m in ledger.mentions(ns, name, attr) if m.seq <= T]
    if co is not None and r.intent == "change" and attr:
        past += [(sq, -1, ref) for ref, sq in co(ns, ledger.group(ns, name), attr, -1, T, window=400)]
    past.sort(key=lambda x: (x[0], x[1]))
    if order == "near":
        past = sorted(past, key=lambda e: (abs(T - e[0]) if T < INF else -e[0], e[0]))
    for _, _, ref in past:
        push(ref)
    return refs
