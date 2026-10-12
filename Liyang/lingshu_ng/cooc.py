# -*- coding: utf-8 -*-
"""cooc · Q10 词级通路的第二路（gen-v3 r3；零 LLM、只读；默认全关，见 bench_gen/PREREG_GEN_v3.md 修订 2）

C1 词元共现扩散（``co_w > 0``）
  主排序（词级 BM25+SDM + 上下文聚合）前 S 名为种子，种子权重 p(s) ∝ 1/名次。每个种子取正文里 idf 最高的 T 个词元
  （2 ≤ df ≤ co_dfmax·N；可排除查询词元——它们已由主排序覆盖），沿倒排「词元 → 含该词元的节点」扩散一步：
      a(n) = Σ_s p(s) · Σ_{t ∈ T(s), t ∈ n} idf(t) / Σ_{t ∈ T(s)} idf(t)        （n ≠ s）
  即「与高分轮共享罕见词元的轮」——同一人物/事物在别的会话里再次出现。所得名次与主排序做倒数名次融合：
      f = 1/(k + r_主) + w/(k + r_共现)
  门控（``co_gate = G > 0``）：只有共现名次 ≤ G 且主名次 > 10（或无主分）的节点加第二路项，前 10 名的相对次序不受扰动。
C2 种子层 + 邻轮补位（``nb_s0 > 0``）
  最终序 = 主排序前 S0 名 → 前 m 名各自的写入序后继轮（可选再加前驱轮；过层/退役过滤；已排入者跳过）→ 主排序余下。
  分数按新次序单调重排（原分与上一名之间取较小值），后续 Q4 组合分的量纲不变。

r4 修 LME 轮级回退（PREREG_GEN_v3 修订 4；默认全关 ⇒ 与 v3 逐位相同）
  E1 头部保护（``co_head = P > 0``）：主排序前 P 名原样保持在最前，融合只重排其后的节点。
  E2a 种子分门限（``co_conf = θ > 0``）：主排序第 1 名分 / 第 6 名分 ≥ θ（不足 6 名视为 ∞）⇒ 本问不启用 C1。
  E2b 问句类型门限（``co_qtype``）：1 = 问句含计数/时间/顺序线索（:data:`QTYPE`）、2 = 只看计数/汇总线索（:data:`QAGG`，
  r4 第 2 次迭代：宽版在 loc_dev 上把「when / how long」类的增益一并关掉）⇒ 本问不启用 C1。

两路都只改排序：关闭（默认）时 :func:`apply` 原样返回输入，与 gen-v2 逐位相同。
"""
from __future__ import annotations

import math
import re
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from . import lexical as lx
from .store.schema import chunks, placeholders

__all__ = ["apply", "cooc_rank", "cooc_fuse", "neighbor_slots", "activation", "gated", "QTYPE", "QAGG"]

Admit = Callable[[List[str]], Set[str]]

#: E2b 计数/时间/顺序类问句线索（英文；中文查询不经过本通路）
QTYPE = re.compile(r"\b(how (many|much|long|often)|when|what (time|date|day|year|month)|which\b.*\b(first|last)|"
                   r"before|after|ago|since|order)\b", re.I)

#: E2b 窄版（co_qtype = 2）：只看计数/汇总线索
QAGG = re.compile(r"\b(how (many|much)|in total|total|between)\b", re.I)


def gated(main: List[str], raw: Dict[str, float], cfg: "lx.LexicalConfig", q: str) -> bool:
    """E2：本问是否跳过 C1（种子分门限或问句类型门限命中）。"""
    if cfg.co_qtype and q and (QAGG if int(cfg.co_qtype) == 2 else QTYPE).search(q):
        return True
    if cfg.co_conf > 0:
        if len(main) < 6:
            return True
        s6 = raw.get(main[5], 0.0)
        return s6 <= 0 or raw.get(main[0], 0.0) / s6 >= cfg.co_conf
    return False


def _order(scores: Dict[str, float]) -> List[str]:
    return [n for n, v in sorted(scores.items(), key=lambda x: (-x[1], x[0])) if v > 0]


def activation(seeds: Sequence[Tuple[str, float]], seed_terms: Dict[str, List[Tuple[str, float]]],
               members: Dict[str, Set[str]]) -> Dict[str, float]:
    """C1 纯函数：seeds = [(种子 id, 权重)]，seed_terms[种子] = [(词元, idf)]，members[词元] = 含它的节点集合。
    返回非种子节点的共现激活 a(n)（定义见模块文档）。"""
    seed_ids = {s for s, _ in seeds}
    act: Dict[str, float] = {}
    for s, p in seeds:
        terms = seed_terms.get(s) or []
        tot = sum(i for _, i in terms)
        if tot <= 0 or p <= 0:
            continue
        for t, idf in terms:
            for n in members.get(t, ()):
                if n != s and n not in seed_ids:
                    act[n] = act.get(n, 0.0) + p * idf / tot
    return act


def _seed_terms(store, seeds: List[str], cfg: "lx.LexicalConfig", qtf: Dict[str, int],
                n_docs: float) -> Dict[str, List[Tuple[str, float]]]:
    """每个种子 idf 最高的 co_terms 个索引词元（只取拉丁词干词元；2 ≤ df ≤ co_dfmax·N）。"""
    body: Dict[str, str] = {}
    for part in chunks(seeds):
        for nid, content in store.db.all(f"SELECT id, content FROM nodes WHERE id IN ({placeholders(len(part))})", part):
            body[nid] = content or ""
    toks = {s: {t for t in lx.tokens(body.get(s, ""), cfg) if t.isascii()} for s in seeds}
    if cfg.co_qexcl:
        toks = {s: ts - set(qtf) for s, ts in toks.items()}
    df = store.text.df({lx.index_term(t) for ts in toks.values() for t in ts})
    cap = max(2.0, cfg.co_dfmax * n_docs)
    n = max(1.0, n_docs)
    out: Dict[str, List[Tuple[str, float]]] = {}
    for s, ts in toks.items():
        cand = []
        for t in ts:
            d = df.get(lx.index_term(t), 0)
            if 2 <= d <= cap:
                cand.append((-math.log(1.0 + (n - d + 0.5) / (d + 0.5)), t))
        out[s] = [(lx.index_term(t), -ni) for ni, t in sorted(cand)[:cfg.co_terms]]
    return out


def cooc_rank(store, main: List[str], cfg: "lx.LexicalConfig", qtf: Dict[str, int], n_docs: float,
              admit: Admit) -> List[str]:
    """C1 第二路名次（共现激活降序；admit 过滤不可检索节点并登记其 rowid）。"""
    seeds = main[:cfg.co_seeds]
    if not seeds:
        return []
    z = sum(1.0 / (i + 1) for i in range(len(seeds)))
    weighted = [(s, (1.0 / (i + 1)) / z) for i, s in enumerate(seeds)]
    terms = _seed_terms(store, seeds, cfg, qtf, n_docs)
    want = sorted({t for ts in terms.values() for t, _ in ts})
    if not want:
        return []
    rows = store.text.postings_rows(want)
    ids = store.text.node_ids({k for _, k, _ in rows})
    ok = admit(sorted(set(ids.values())))
    members: Dict[str, Set[str]] = {}
    for t, k, _ in rows:
        nid = ids.get(k)
        if nid in ok:
            members.setdefault(t, set()).add(nid)
    act = activation(weighted, terms, members)
    return [n for n, _ in sorted(act.items(), key=lambda x: (-x[1], x[0]))]


def cooc_fuse(main: List[str], second: List[str], w: float, k: float, gate: int = 0, head: int = 0) -> Dict[str, float]:
    """C1 融合：f = 1/(k + r_主) + w/(k + r_共现)；gate > 0 时第二路项只给共现名次 ≤ gate 且主名次 > 10（或无主分）的节点；
    head > 0（E1）时主序前 head 名原样居前，其余按 f 排在其后（分数单调截到前一名之下）。"""
    rm = {n: i + 1 for i, n in enumerate(main)}
    f = {n: 1.0 / (k + r) for n, r in rm.items()}
    for i, n in enumerate(second):
        r = i + 1
        if gate > 0 and (r > gate or rm.get(n, 10 ** 9) <= 10):
            continue
        f[n] = f.get(n, 0.0) + w / (k + r)
    if head <= 0:
        return f
    top = main[:head]
    fixed = set(top)
    order = top + [n for n, _ in sorted(((n, v) for n, v in f.items() if n not in fixed), key=lambda x: (-x[1], x[0]))]
    out: Dict[str, float] = {}
    prev = None
    for n in order:
        v = f[n] if prev is None else min(f[n], prev * (1.0 - 1e-6))
        out[n] = v
        prev = v
    return out


def neighbor_slots(main: List[str], scores: Dict[str, float], nbrs: Dict[str, List[str]], s0: int,
                   m: int) -> Dict[str, float]:
    """C2 纯函数：主序前 s0 名 → 前 m 名的邻轮（nbrs[id] = 按优先级的邻轮 id）→ 主序余下；分数单调重排。"""
    order: List[str] = list(main[:s0])
    placed = set(order)
    for n in main[:m]:
        for x in nbrs.get(n, ()):
            if x not in placed:
                order.append(x); placed.add(x)
    order.extend(n for n in main[s0:] if n not in placed)
    out: Dict[str, float] = {}
    prev = None
    for n in order:
        v = scores.get(n, 0.0)
        if prev is not None:
            v = min(v, prev * (1.0 - 1e-6)) if v > 0 else prev * (1.0 - 1e-6)
        out[n] = v
        prev = v
    return out


def _neighbors(store, main: List[str], seqno: Dict[str, Optional[int]], cfg: "lx.LexicalConfig",
               admit: Admit) -> Dict[str, List[str]]:
    """前 nb_m 名各自最近的可检索后继轮（rowid 之后 3 行内取最近者），nb_prev 时再取最近的前驱轮。"""
    by_row = {r: n for n, r in seqno.items() if r is not None}
    want: Set[int] = set()
    for n in main[:cfg.nb_m]:
        k = seqno.get(n)
        if k is not None:
            want.update(range(k + 1, k + 4))
            if cfg.nb_prev:
                want.update(range(k - 3, k))
    miss = sorted(r for r in want - set(by_row) if r > 0)
    if miss:
        got: Dict[int, str] = {}
        for part in chunks(miss):
            got.update((r, nid) for r, nid in store.db.all(
                f"SELECT rowid, id FROM nodes WHERE rowid IN ({placeholders(len(part))})", part))
        ok = admit(sorted(got.values()))
        by_row.update((r, nid) for r, nid in got.items() if nid in ok)
    out: Dict[str, List[str]] = {}
    for n in main[:cfg.nb_m]:
        k = seqno.get(n)
        if k is None:
            continue
        nx = [by_row[r] for r in range(k + 1, k + 4) if r in by_row][:1]
        pv = [by_row[r] for r in range(k - 1, k - 4, -1) if r in by_row][:1] if cfg.nb_prev else []
        out[n] = nx + pv
    return out


def _admitter(store, use: Set[str], seqno: Dict[str, Optional[int]]) -> Callable[[List[str]], Set[str]]:
    """可检索过滤（层在 use 内、未退役，同 Q10 主通路）；通过者登记 rowid 进 seqno。"""
    from .retrieval import _retired   # 延迟导入：retrieval 导入本模块

    def admit(ids: List[str]) -> Set[str]:
        """ids 中可检索者的集合。"""
        ok: Set[str] = set()
        for part in chunks(ids):
            for nid, rowid, layer, tj, imp in store.db.all(
                    f"SELECT id, rowid, layer, tags, importance FROM nodes WHERE id IN ({placeholders(len(part))})", part):
                if layer in use and not _retired(imp, tj):
                    ok.add(nid)
                    seqno.setdefault(nid, rowid)
        return ok
    return admit


def apply(store, raw: Dict[str, float], seqno: Dict[str, Optional[int]], cfg: "lx.LexicalConfig",
          qtf: Dict[str, int], n_docs: float, use: Set[str], q: str = "") -> Dict[str, float]:
    """Q10 第二路入口（lex_rank 在上下文聚合 / D1 / D2 之后调用）：先 C1 再 C2；两路都关时原样返回 raw。"""
    if cfg.co_w <= 0 and cfg.nb_s0 <= 0:
        return raw
    main = _order(raw)
    if not main:
        return raw
    admit = _admitter(store, use, seqno)
    if cfg.co_w > 0 and not gated(main, raw, cfg, q):
        raw = cooc_fuse(main, cooc_rank(store, main, cfg, qtf, n_docs, admit), cfg.co_w, cfg.co_k, cfg.co_gate,
                        cfg.co_head)
        main = _order(raw)
    if cfg.nb_s0 > 0:
        raw = neighbor_slots(main, raw, _neighbors(store, main, seqno, cfg, admit), cfg.nb_s0, cfg.nb_m)
    return raw
