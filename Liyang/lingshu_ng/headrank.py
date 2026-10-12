# -*- coding: utf-8 -*-
"""headrank · Q10 词级通路的头部精排 H2（gen-v3 r6；零 LLM、只读；PREREG_GEN_v3 修订 7 / 7a / 7b）

在召回的最终前 N 名（``hd_n``）内按
    h = 分/最大 + hd_own·own + hd_cov·cov + hd_prox·prox
重排，再把前 N 名原有分数按新次序重新分配（分数多重集合不变 ⇒ 第 N+1 名以后名次与分数不变）。
  own  = 节点自身 BM25+SDM 原始分（上下文聚合 / C1 之前）/ 前 N 名内最大值；
  cov  = 命中查询词元的 qtf·idf 和 / 全部查询词元的 qtf·idf 和（协调度）；
  prox = 命中的不同查询词元数 m ≥ 2 时 m / 覆盖它们的最短词窗长，否则 0。
放置 ``hd_at``：0 = 词级通路内（Q4 组合分之前）；1 = 召回最终名次上（Q4 组合分与 R2 多样化之后，前 N 名集合严格不变）。
gen-v3.2 交付值：hd_at 1、hd_n 10、hd_cov 1（own / prox 关）；``hd_n = 0`` 即回到 v3。中文查询不经过本通路。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

__all__ = ["features", "head_rerank", "lex_stage", "recall_stage"]


def features(scorer, content: str) -> Tuple[float, float]:
    """(cov, prox)。cov = 命中查询词元 qtf·idf 和 / 全部查询词元；
    prox = 正文内命中的不同查询词元数 m ≥ 2 时 m / 覆盖它们的最短词窗长，否则 0。"""
    if not content or not scorer.idf:
        return 0.0, 0.0
    _, pos, _ = scorer._positions(content)
    tot = sum(scorer.qtf[t] * scorer.idf[t] for t in scorer.idf)
    cov = sum(scorer.qtf[t] * scorer.idf[t] for t in pos) / tot if tot > 0 else 0.0
    live = {t: [i for i in p if i >= 0] for t, p in pos.items()}
    live = {t: p for t, p in live.items() if p}
    m = len(live)
    if m < 2:
        return cov, 0.0
    ev = sorted((i, t) for t, p in live.items() for i in p)
    cnt: Dict[str, int] = {}
    best, lo, have = 0, 0, 0
    for hi in range(len(ev)):
        t = ev[hi][1]
        cnt[t] = cnt.get(t, 0) + 1
        if cnt[t] == 1:
            have += 1
        while have == m:
            span = ev[hi][0] - ev[lo][0] + 1
            best = span if not best or span < best else best
            tl = ev[lo][1]
            cnt[tl] -= 1
            if cnt[tl] == 0:
                have -= 1
            lo += 1
    return cov, (m / best if best else 0.0)


def head_rerank(ranked: List[Tuple[str, float]], raw0: Dict[str, float], body: Dict[str, str], scorer,
                cfg) -> List[Tuple[str, float]]:
    """ranked 已按 (−分, id) 排好；只重排前 hd_n 名，分数按原名次重新分配。"""
    N = int(cfg.hd_n)
    if N <= 1 or len(ranked) < 2 or not (cfg.hd_own or cfg.hd_cov or cfg.hd_prox):
        return ranked
    top = ranked[:N]
    rmax = top[0][1] or 1.0
    omax = max((raw0.get(n, 0.0) for n, _ in top), default=0.0) or 1.0
    keyed = []
    for i, (n, v) in enumerate(top):
        cov, prox = features(scorer, body.get(n, "")) if (cfg.hd_cov or cfg.hd_prox) else (0.0, 0.0)
        h = v / rmax + cfg.hd_own * raw0.get(n, 0.0) / omax + cfg.hd_cov * cov + cfg.hd_prox * prox
        keyed.append((-h, i, n))
    keyed.sort()
    return [(n, top[j][1]) for j, (_, _, n) in enumerate(keyed)] + ranked[N:]


def lex_stage(ranked: List[Tuple[str, float]], raw0: Dict[str, float], body: Dict[str, str], scorer, cfg,
              limit: int, diag: Dict) -> Tuple[List[Tuple[str, float]], Dict]:
    """lex_rank 出口：hd_at 0 在此重排；hd_at 1 把 (raw0, body, scorer) 放进 diag["head"] 交给召回。"""
    if cfg.hd_n > 0:
        if cfg.hd_at == 1:
            diag["head"] = (raw0, body, scorer)
        else:
            ranked = head_rerank(ranked, raw0, body, scorer, cfg)
    return ranked[:limit], diag


def recall_stage(retriever, lex: bool, scored: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    """Retriever.recall 在 Q4 组合分与 R2 多样化之后调用：hd_at 1 时在最终前 hd_n 名内重排。"""
    cfg = retriever.lexical
    head: Optional[tuple] = retriever.last_plan.get("head") if lex else None
    if head is None or cfg.hd_n <= 0 or cfg.hd_at != 1:
        return scored
    return head_rerank(scored, head[0], head[1], head[2], cfg)
