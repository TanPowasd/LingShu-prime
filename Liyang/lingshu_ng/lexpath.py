# -*- coding: utf-8 -*-
"""lexpath · Q10 词级通路的排序主体（gen-v1/v3；自 retrieval 拆出以满足模块 <600 行规则，行为逐字节不变）。

retrieval 中的同名符号（``lex_rank``/``lex_stats``/``_lex_ready``）为本模块的再导出。"""
from __future__ import annotations
from typing import Dict, List, Optional, Sequence, Set, Tuple
from . import cooc, headrank as hd, lexical as lx
from .store import Store
from .store.schema import chunks, placeholders
from .expansion import TAG_BONUS, tags_of
from . import retrieval as _R


def _lex_ready(store: Store) -> bool:
    """派生倒排已含 Q10 词干词元（index_state('lexv') 为当前版本）。"""
    return store.db.scalar("SELECT value FROM index_state WHERE key='lexv'") == lx.LEXV


def lex_stats(store: Store) -> Tuple[float, float]:
    """(可检索节点数 N, 平均正文字符数 avgdl)；按库缓存，代理键上界漂移超过 2% 才重读。"""
    mk = store.db.scalar("SELECT MAX(nkey) FROM node_index") or 0
    k0, n, avg = getattr(store.text, "_lex_stats", (-1, 0.0, 1.0))
    if k0 < 0 or abs(mk - k0) > 0.02 * max(1, k0):
        row = store.db.one("SELECT COUNT(*), AVG(length(n.content)) FROM node_index ni JOIN nodes n ON n.id = ni.node_id "
                           "WHERE ni.grams > 0")
        n, avg = (float(row[0] or 0), float(row[1] or 1.0)) if row else (0.0, 1.0)
        store.text._lex_stats = (mk, n, avg or 1.0)
    return n, avg or 1.0


def _ctx_fill(store: Store, raw: Dict[str, float], seqno: Dict[str, Optional[int]], tags: Dict[str, str],
              use: Set[str], cfg: "lx.LexicalConfig") -> None:
    """Q10 上下文补位：前 ctx_fill 名（按原始分）的写入序邻居（|Δrowid| ≤ ctx_span）中未打分者以 0 分加入，
    随后的 :func:`lexical.context_aggregate` 给它们 β·decay^(d−1)·来源分（问句之后的答句常与问题零词面重合）。"""
    top = sorted(raw, key=lambda n: (-raw[n], n))[:cfg.ctx_fill]
    want: Set[int] = set()
    for nid in top:
        k = seqno.get(nid)
        if k is not None:
            want.update(range(k - cfg.ctx_span, k + cfg.ctx_span + 1))
    want -= {v for v in seqno.values() if v is not None}
    for part in chunks(sorted(want)):
        for nid, rowid, layer, tj, imp in store.db.all(
                f"SELECT id, rowid, layer, tags, importance FROM nodes WHERE rowid IN ({placeholders(len(part))})", part):
            if layer in use and not _R._retired(imp, tj):
                seqno[nid] = rowid
                tags[nid] = tj or ""
                raw[nid] = 0.0


def _diffuse_fuse(store: Store, raw0: Dict[str, float], agg: Dict[str, float], seqno: Dict[str, Optional[int]],
                  tags: Dict[str, str], use: Set[str], cfg: "lx.LexicalConfig") -> Dict[str, float]:
    """gen-v3 D1（:func:`lexical.diffuse_fuse`）：扩散可达范围内未打分的节点从库里补读（过层/退役过滤，同 :func:`_ctx_fill`）。"""
    def fetch(rowids: List[int]) -> Dict[int, str]:
        """rowid → 可检索节点 id（顺带登记 seqno/tags）。"""
        got: Dict[int, str] = {}
        for part in chunks(rowids):
            for nid, rowid, layer, tj, imp in store.db.all(
                    f"SELECT id, rowid, layer, tags, importance FROM nodes WHERE rowid IN ({placeholders(len(part))})", part):
                if layer in use and not _R._retired(imp, tj):
                    got[rowid] = nid
                    seqno.setdefault(nid, rowid)
                    tags.setdefault(nid, tj or "")
        return got
    return lx.diffuse_fuse(raw0, agg, seqno, fetch, cfg)


def lex_rank(store: Store, q: str, cfg: "lx.LexicalConfig", use: Set[str], limit: int,
             keys: Optional[List[int]] = None, tag_terms: Sequence[str] = ()) -> Tuple[List[Tuple[str, float]], Dict]:
    """Q10 词级通路：对 keys（nkey；None = 全部节点，即暴力基线）精排，返回 ([(id, 相关度)], 诊断)。"""
    text = store.text
    seq, qtf = lx.query_terms(q, cfg)
    df = text.df({lx.index_term(t) for t in qtf})
    n, avg = lex_stats(store)
    sc = lx.Scorer(q, cfg, df, n, avg)
    sel = ("SELECT n.id, n.content, n.tags, n.layer, n.rowid, n.importance FROM node_index ni "
           "JOIN nodes n ON n.id = ni.node_id")
    rows: List[tuple] = []
    if keys is None:
        rows = store.db.all(sel)
    else:
        for part in chunks(keys):
            rows.extend(store.db.all(f"{sel} WHERE ni.nkey IN ({placeholders(len(part))})", part))
    raw: Dict[str, float] = {}
    seqno: Dict[str, Optional[int]] = {}
    tags: Dict[str, str] = {}
    body: Dict[str, str] = {}
    for nid, content, tj, layer, rowid, _imp in rows:
        if layer not in use:
            continue
        v = sc.score(content or "")
        tags[nid] = tj or ""
        seqno[nid] = rowid
        if v > 0:
            raw[nid] = v
            body[nid] = content or ""
    if cfg.prf_docs > 0 and raw:
        # 伪相关反馈：扩展词只对首轮非零分节点重排（不引入新候选 ⇒ 与暴力精排仍逐名次相同）
        top = sorted(raw, key=lambda n_: (-raw[n_], n_))[:cfg.prf_docs]
        extra = lx.prf_terms(sc, [body[n_] for n_ in top], text.df, cfg)
        if extra:
            df2 = dict(df)
            df2.update(text.df({lx.index_term(t) for t in extra}))
            sc = lx.Scorer(q, cfg, df2, n, avg, extra)
            raw = {nid: sc.score(body[nid]) for nid in raw}
    raw0 = dict(raw)
    if cfg.ctx_fill > 0 and cfg.ctx_beta > 0 and raw:
        _ctx_fill(store, raw, seqno, tags, use, cfg)
    raw = lx.context_aggregate(raw, seqno, cfg.ctx_beta, cfg.ctx_span, cfg.ctx_decay, cfg.ctx_prev, cfg.ctx_next)
    if cfg.dif_w > 0 and raw0:
        raw = _diffuse_fuse(store, raw0, raw, seqno, tags, use, cfg)
    raw = lx.cluster_diversify(raw, seqno, cfg.div_win, cfg.div_pen, cfg.div_top) if cfg.div_win > 0 else raw
    raw = cooc.apply(store, raw, seqno, cfg, qtf, n, use, q)     # gen-v3 r3 C1/C2 + r4 E1/E2
    mx = max(raw.values() or [0.0])
    out: Dict[str, float] = {nid: v / mx for nid, v in raw.items()} if mx > 0 else {}
    # 标签加分（与旧通路同一条件）：命中标签的节点即使正文零分也可入选
    for nid, tj in tags.items():
        if tj and tj != "[]" and _R.tag_hit(q, tags_of(tj)):
            out[nid] = min(1.0, out.get(nid, 0.0) + TAG_BONUS)
    ranked = sorted(((nid, round(v, 6)) for nid, v in out.items() if v > 0), key=lambda x: (-x[1], x[0]))
    return hd.lex_stage(ranked, raw0, body, sc, cfg, limit, {"scored": len(rows), "n": n, "avgdl": round(avg, 1)})
