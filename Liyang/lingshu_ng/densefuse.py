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
- F3（gen r8，修订 9；默认关）：F3a sf_mx > 0 ⇒ 前 sf_mxn 名按提供者的逐词向量 MaxSim 名次再加 RRF 项精排（ColBERT 式晚交互，
  Khattab & Zaharia, SIGIR 2020；提供者无 ``maxsim`` 时不生效）；F3b sf_qp = 1 ⇒ 稠密路查询加 BGE v1.5 模型卡推荐的检索指令前缀。
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


#: F3b：BGE v1.5 英文模型卡推荐的短查询检索指令（文档端不加）
QP = "Represent this sentence for searching relevant passages: "
_QW = ("what", "when", "where", "who", "whom", "whose", "which", "why", "how", "is", "are", "was", "were", "do",
       "does", "did", "can", "could", "should", "would", "will", "have", "has", "had", "am")


def is_question(q: str) -> bool:
    """问句形式：以 ? 结尾，或以疑问词/助动词开头且含 ?（F3b' 查询类型路由；陈述式触发语返回 False）。"""
    s = q.strip()
    if s.endswith("?"):
        return True
    first = s.split(None, 1)[0].lower().strip("\"'") if s else ""
    return first in _QW and "?" in s


def _maxsim(r, q: str, order: List[str], f: Dict[str, float], drank: Dict[str, int], lrank: Dict[str, int],
            cfg) -> List[str]:
    """F3a：前 sf_mxn 名按 MaxSim 名次加 sf_mx/(sf_k + r_mx)，只重排这一段（之后不动）。
    提供者无 maxsim 能力（假提供者、旧接口）时原样返回。思想来源：ColBERT（Khattab & Zaharia, SIGIR 2020）。"""
    prov = getattr(r.semantic, "provider", None)
    if prov is None or not hasattr(prov, "maxsim"):
        return order
    n = min(int(cfg.sf_mxn), len(order))
    head = order[:n]
    if n < 2:
        return order
    txt: Dict[str, str] = {}
    for part in chunks(head):
        for nid, c in r.store.db.all(f"SELECT id, content FROM nodes WHERE id IN ({placeholders(len(part))})", part):
            txt[nid] = c or ""
    try:
        with r.semantic._plock:
            ms = prov.maxsim(q, [txt.get(nid, "") for nid in head])
    except Exception:  # 外部推理件异常类型不可枚举：退回 F1 次序
        return order
    mrank = {nid: i for i, nid in enumerate(sorted(range(n), key=lambda i: (-ms[i], i)))}
    mr = {head[i]: rk for i, rk in mrank.items()}
    k, w = float(cfg.sf_k), float(cfg.sf_mx)
    g = {nid: f[nid] + w / (k + mr[nid] + 1) for nid in head}
    pos = {nid: i for i, nid in enumerate(head)}
    return sorted(head, key=lambda nid: (-g[nid], pos[nid])) + order[n:]


def fuse(r, q: str, scored: List[Tuple[str, float]], limit: int, exclude: Set[str],
         lex: bool) -> List[Tuple[str, float]]:
    """语义第二路融合入口（retrieval.recall 调用）。"""
    cfg = r.lexical
    if not (lex and getattr(cfg, "sf", 0)):
        return r._fuse_semantic(q, scored, limit, exclude)
    qp = int(getattr(cfg, "sf_qp", 0) or 0)
    if qp == 2:                       # F3b'：只对问句形式的查询加指令前缀（陈述式触发语不加）
        qs = [QP + q] if is_question(q) else [q]
    elif qp == 3:                     # F3b''：原句与加前缀各检索一次，两份稠密名次各占一半权重
        qs = [q, QP + q]
    else:
        qs = [QP + q] if qp else [q]
    k, w = float(cfg.sf_k), float(cfg.sf_w)
    lists = []
    for qd in qs:
        hits = [(nid, c) for nid, c in r.semantic.search(qd, int(cfg.sf_n) + len(exclude)) if nid not in exclude]
        lists.append(hits)
    ok = _allowed(r, [nid for hits in lists for nid, _ in hits])
    lists = [[(nid, c) for nid, c in hits if nid in ok][:int(cfg.sf_n)] for hits in lists]
    if not any(lists):
        return scored
    dterm: Dict[str, float] = {}
    best: Dict[str, float] = {}
    for hits in lists:
        for i, (nid, c) in enumerate(hits):
            dterm[nid] = dterm.get(nid, 0.0) + (w / len(lists)) / (k + i + 1)
            best[nid] = max(best.get(nid, -1.0), c)
    dense = sorted(best.items(), key=lambda x: (-dterm[x[0]], -x[1], x[0])) if len(lists) > 1 else lists[0]
    f: Dict[str, float] = {}
    for i, (nid, _) in enumerate(scored):
        f[nid] = 1.0 / (k + i + 1)
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
    drank = {nid: i for i, (nid, _) in enumerate(dense)}
    # 同分按词面名次、再按稠密名次断开（gen r8 核对）：每个候选至少有一种名次，id 永不起作用，次序只由两路名次决定。
    # 注意 sf_w = 2、sf_k = 10 时 1/(k+1+i) 与 2/(k+1+j)（j = 2i + k + 1）在浮点上恰好相等，这类同分是系统性的；
    # 改成稠密名次优先会改变名次（r8 dev 实测 40/40 题名次变化），属于排序行为改动而非确定性修复，故保持 r7 的词面优先。
    order = sorted(f, key=lambda n: (-f[n], lrank.get(n, len(lrank)), drank.get(n, len(drank)), n))[:limit]
    if getattr(cfg, "sf_mx", 0) > 0:
        order = _maxsim(r, q, order, f, drank, lrank, cfg)
    vals = sorted((s for _, s in scored), reverse=True)
    cos = dict(dense)
    if not vals:
        return [(nid, round(0.5 * max(0.0, cos.get(nid, 0.0)), 6)) for nid in order]
    return [(nid, vals[min(i, len(vals) - 1)]) for i, nid in enumerate(order)]
