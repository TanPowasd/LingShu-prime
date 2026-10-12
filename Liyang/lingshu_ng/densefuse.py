# -*- coding: utf-8 -*-
"""densefuse · gen-v3 r7 稠密–稀疏融合（PREREG_GEN_v3 修订 8 F1/F2；默认关）

只在两件事同时成立时接管语义第二路的融合：查询走英文词级通路（Q10），且 ``LexicalConfig.sf`` ≠ 0；否则原样交给
``Retriever._fuse_semantic``（semindex.PATTERN 交错，上次推送版行为，逐位不变）。

- F1 加权 RRF：f(n) = 1/(sf_k + r_词面(n)) + sf_w/(sf_k + r_稠密(n))，候选 = 词面最终名次 ∪ 稠密前 sf_n 名。
  思想来源：BGE-M3 的稠密 + 稀疏混合打分（Chen et al., 2024, "BGE M3-Embedding"）与倒数名次融合 RRF
  （Cormack, Clarke & Büttcher, SIGIR 2009）。本实现为自研，不含其代码。
- F2 稠密邻轮传播（sf_adj > 0）：稠密前 sf_n 名的每个节点把 sf_adj × 自身稠密项传给写入序 ±1 的邻轮（取最大，不叠加）。
  思想来源：HippoRAG（Gutiérrez et al., NeurIPS 2024）在关联图上做个性化 PageRank 扩散；这里取图 = 写入序邻接、一跳、无迭代的特例。
- 分数：按 f 排序后，把词面最终分数的多重集合按新次序重新分配（保持非增）；超出词面候选数的位置沿用最后一个分数；
  无词面命中时取 0.5·余弦（同 _fuse_semantic）。语义候选过 exclude / 退役 / 可检索层过滤（同 _fuse_semantic）。
纯 Python（核心零外部依赖）；向量与余弦全部在注入的提供者里。
"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple

from .store.schema import chunks, placeholders

__all__ = ["fuse"]


def _allowed(r, ids: List[str]) -> Dict[str, int]:
    """可检索（层内、未退役）的 id → rowid。"""
    from .retrieval import _layer_values, _retired
    use = _layer_values(None)
    out: Dict[str, int] = {}
    for part in chunks(ids):
        for nid, imp, tj, layer, rid in r.store.db.all(
                f"SELECT id, importance, tags, layer, rowid FROM nodes WHERE id IN ({placeholders(len(part))})", part):
            if layer in use and not _retired(imp, tj):
                out[nid] = rid
    return out


def _neighbours(r, rowids: List[int]) -> Dict[int, str]:
    """写入序 rowid → id（只取给定 rowid）。"""
    out: Dict[int, str] = {}
    for part in chunks(rowids):
        for rid, nid in r.store.db.all(f"SELECT rowid, id FROM nodes WHERE rowid IN ({placeholders(len(part))})", part):
            out[rid] = nid
    return out


def fuse(r, q: str, scored: List[Tuple[str, float]], limit: int, exclude: Set[str],
         lex: bool) -> List[Tuple[str, float]]:
    """语义第二路融合入口（retrieval.recall 调用）。"""
    cfg = r.lexical
    if not (lex and getattr(cfg, "sf", 0)):
        return r._fuse_semantic(q, scored, limit, exclude)
    hits = [(nid, c) for nid, c in r.semantic.search(q, int(cfg.sf_n) + len(exclude)) if nid not in exclude]
    ok = _allowed(r, [nid for nid, _ in hits])
    dense = [(nid, c) for nid, c in hits if nid in ok][:int(cfg.sf_n)]
    if not dense:
        return scored
    k, w = float(cfg.sf_k), float(cfg.sf_w)
    f: Dict[str, float] = {}
    for i, (nid, _) in enumerate(scored):
        f[nid] = 1.0 / (k + i + 1)
    dterm = {nid: w / (k + i + 1) for i, (nid, _) in enumerate(dense)}
    if cfg.sf_adj > 0:
        nb = _neighbours(r, sorted({ok[nid] + d for nid, _ in dense for d in (-1, 1)}))
        prop: Dict[str, float] = {}
        for nid, _ in dense:
            for d in (-1, 1):
                m = nb.get(ok[nid] + d)
                if m is not None and m not in exclude:
                    prop[m] = max(prop.get(m, 0.0), cfg.sf_adj * dterm[nid])
        okn = _allowed(r, [m for m in prop if m not in ok])
        for m, v in prop.items():
            if m in ok or m in okn:
                f[m] = f.get(m, 0.0) + v
    for nid, v in dterm.items():
        f[nid] = f.get(nid, 0.0) + v
    lrank = {nid: i for i, (nid, _) in enumerate(scored)}
    order = sorted(f, key=lambda n: (-f[n], lrank.get(n, len(lrank)), n))[:limit]
    vals = sorted((s for _, s in scored), reverse=True)
    cos = dict(dense)
    if not vals:
        return [(nid, round(0.5 * max(0.0, cos.get(nid, 0.0)), 6)) for nid in order]
    return [(nid, vals[min(i, len(vals) - 1)]) for i, nid in enumerate(order)]
