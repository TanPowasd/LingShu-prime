# -*- coding: utf-8 -*-
"""retrieval · 内容检索与组合召回

旧实现的缺陷类别：LIKE 预筛 + 硬截断 ``LIMIT 300``（无 ORDER BY，老记忆不可达 #35）、
``%`` / ``_`` 当通配符（#183 ``search_content('%')`` 返回全库）、同义词按子串触发
（#132 "EMAIL"→灵枢）、相关度分母只看查询（#82 恒饱和 1.0）、零分节点照样返回、
SELF 快照参与竞争(#201)、召回不看置信度(#29)。

不变量：
  Q1 候选来自派生倒排表（store.textindex，写时由触发器维护，无通配符语义、无插入序截断）：
     查询词元（正文二元组 + 「标签 ⊂ 查询」的标签项）按 df 升序（= idf 降序）展开；
     每个已见节点按（已知命中数, 是否命中标签）分桶，桶的可证上界 < 第 limit 名的桶不精排
     （MaxScore 式剪枝，见 :mod:`lingshu_ng.expansion`）。当未见节点与全部未精排桶的上界都低于
     第 limit 名时停止——此时结果与暴力全库精排 (:func:`brute_force`) **逐名次相同**。
     仅当累计倒排行数将超 :data:`BUDGET` 才停止展开新节点（``last_plan['approx']``），剩余词元
     只对已见节点做成员判定；被舍弃的只可能是一个已展开（最稀有）词元都不含的节点——与年龄无关。
  Q2 相关度 = 覆盖率 × (0.5 + 0.5·精确率)：同样覆盖查询时，更短、更专注的节点得分更高；
     得分为 0 的节点永不返回。
  Q3 同义词：中日韩词按子串触发，拉丁字母词必须整词匹配。评分只用原查询二元组（同义词
     命中但与原查询零交集的节点得分恒为 0），故同义词不参与候选展开——它们只会挤占预算。
  Q4 召回分 = 0.5·相关度 + 0.2·importance + 0.15·confidence + 0.15·近因（全部 ∈[0,1]）。
  Q5 退役：带 ``archived`` 标签且 importance ≤ :data:`ARCHIVED_IMP_MAX` 的节点不进召回（旧 forget_advisor
     「归档 = 降权、可逆」：恢复 importance 即重新可见；作者基准指出的「退役后检索泄漏旧值」由此关闭）。
     内容检索 :meth:`Retriever.search` 仍返回它们（审计/恢复路径）。
  Q6 矛盾两侧：入选节点若有 OPPOSITE（register_conflict 落账）边，对侧节点（未退役、可检索层）
     紧随其后一并交付，挤出末位——矛盾已落账时不只交付一侧（「聚焦检索丢失矛盾另一侧」）。
     写入期自动登记的矛盾（:mod:`lingshu_ng.conflict`，source_evidence = auto_*）置信度低，不插队：
     前 :data:`AUTO_TOP` 名的自动对侧至多 :data:`AUTO_SLOTS` 条补在末位（挤出末位，所随节点保留）。
  Q9 取代降权：被写入期检测判为「已被取代」的旧记载（auto_supersede 边的 target，且取代它的新记载未退役）
     相关度乘 :data:`SUPERSEDED_FACTOR`——旧值仍可检索、仍作为矛盾另一侧随新值交付，只是不再与新值同列。
"""
from __future__ import annotations

import json
import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .dedup import bigrams
from .layers import LayerPolicy
from .store import Store
from .store.schema import chunks, placeholders
from .expansion import TAG_BONUS, Expansion, tags_of
from .conflict import AUTO_SUPERSEDE, is_auto
from .semindex import interleave
from .rerank import Reranker
from .store.textindex import TAG_PREFIX
from .types import MemoryLayer, Node, now

__all__ = ["SYNONYM_GROUPS", "expand_terms", "score", "brute_force", "Retriever", "BUDGET"]

SYNONYM_GROUPS: Tuple[frozenset, ...] = tuple(frozenset(g) for g in (
    {"视觉", "图像", "画面", "图片", "影像", "视像"},
    {"语义", "含义", "意思", "意义", "概念"},
    {"识别", "检测", "感知", "探测", "发现"},
    {"转换", "转化", "映射", "变换"},
    {"实验", "试验", "实现", "验证", "测试"},
    {"评测", "评估", "跑分", "基准", "benchmark", "评审", "考核"},
    {"记忆", "记录"},
    {"智能", "智能体", "灵枢", "AI"},
    {"语音", "声音", "音频", "说话"},
    {"对话", "聊天", "交流"},
))
#: 展开倒排的累计行数上限（超过即停止展开，见 Q1）
BUDGET = 60000
#: 展开下一个词元前「先精排再判完成」的最低代价额度（倒排成员点查次数；实际额度取
#: max(REFINE_CAP, 下一词元 df/2)——点查一次约等于读两行倒排，超出额度就先展开下一个词元）
REFINE_CAP = 400
#: 归档节点的 importance 上限（forget_advisor 默认 archived_imp=0.1；恢复到此之上即解除退役）
ARCHIVED_IMP_MAX = 0.1 + 1e-9
#: Q6 自动登记矛盾：只看前 AUTO_TOP 名入选节点的对侧，至多补 AUTO_SLOTS 条
AUTO_TOP = 3
AUTO_SLOTS = 2
#: Q9 被取代旧记载的相关度系数
SUPERSEDED_FACTOR = 0.5
#: 查询不长于此时枚举其全部子串作标签候选；更长的查询扫描标签词表（两者都精确）
_TAG_ENUM_MAX = 64


def _hit(word: str, query: str) -> bool:
    if word.isascii():
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", query, re.I) is not None
    return word in query


def expand_terms(query: str) -> List[str]:
    """Q3：原查询 + 命中组的全部同义词（去重保序）。"""
    terms = [query]
    for group in SYNONYM_GROUPS:
        if any(_hit(w, query) for w in group):
            terms.extend(sorted(group))
    return list(dict.fromkeys(terms))


def score(query_grams: frozenset, text: str) -> float:
    """Q2：覆盖率 × (0.5 + 0.5·精确率)。"""
    if not query_grams:
        return 0.0
    ng = bigrams(text)
    if not ng:
        return 0.0
    inter = len(query_grams & ng)
    if not inter:
        return 0.0
    return (inter / len(query_grams)) * (0.5 + 0.5 * inter / len(ng))


def tag_hit(query: str, tags: Iterable[str]) -> bool:
    """标签加分条件：某标签等于查询，或（长度 >1 且）是查询的子串。"""
    return any(t == query or (len(t) > 1 and t in query) for t in tags)


def relevance(query: str, qg: frozenset, content: str, tags: Iterable[str]) -> float:
    """单节点相关度（Q2 + 标签加分），检索与暴力基线共用。"""
    s = score(qg, content or "")
    if tag_hit(query, tags):
        s = min(1.0, s + TAG_BONUS)
    return round(s, 6)


def brute_force(store: Store, query: str, layers: Optional[Sequence[MemoryLayer]] = None,
                limit: int = 20) -> List[Tuple[str, float]]:
    """暴力全库精排（召回率基线；不走索引）：[(id, 相关度)]。"""
    q = (query or "").strip()
    qg = bigrams(q)
    use = _layer_values(layers)
    out = []
    for nid, content, tags_json, imp, layer in store.db.all(
            "SELECT id, content, tags, importance, layer FROM nodes"):
        if layer in use:
            s = relevance(q, qg, content, json.loads(tags_json) if tags_json else [])
            if s > 0:
                out.append((nid, s, imp or 0.0))
    out.sort(key=lambda x: (-x[1], -x[2], x[0]))
    return [(nid, s) for nid, s, _ in out[:limit]]


def _layer_values(layers: Optional[Sequence[MemoryLayer]]) -> Set[str]:
    allowed = set(LayerPolicy.layers(searchable=True))
    use = [x for x in (MemoryLayer.coerce(y) for y in layers) if x in allowed] if layers else list(allowed)
    return {m.value for m in use}


class Retriever:
    """内容检索器（只读）。``on_hit`` 回调用于访问计数/飞轮记账。"""

    def __init__(self, store: Store, on_hit: Optional[Callable[[List[str]], None]] = None) -> None:
        self.store = store
        self.on_hit = on_hit
        self.reranker = Reranker(store.db)
        #: 可选第二路召回（:class:`lingshu_ng.semindex.SemanticIndex`；engine 注入，默认无）
        self.semantic = None
        #: 最近一次检索的展开计划（诊断/测试用）：terms/expanded/rows/approx
        self.last_plan: Dict = {}

    # ------------------------------------------------------------ 候选展开
    def _tag_terms(self, q: str) -> List[str]:
        """满足「标签 == 查询 或 标签 ⊂ 查询」的全部标签词元（精确）。"""
        if len(q) <= _TAG_ENUM_MAX:
            subs = {q} | {q[i:j] for i in range(len(q)) for j in range(i + 2, len(q) + 1)}
            return [TAG_PREFIX + t for t in subs]
        rows = self.store.db.all("SELECT term FROM term_df WHERE term >= ? AND term < ? AND df > 0",
                                 (TAG_PREFIX, chr(ord(TAG_PREFIX) + 1)))
        return [r[0] for r in rows if tag_hit(q, [r[0][1:]])]

    def _plan(self, q: str, qg: frozenset) -> List[Tuple[int, str, bool]]:
        """展开顺序：[(df, 词元, 是否标签项)]，df 升序（idf 降序）；df=0 的词元不展开。"""
        text = self.store.text
        order = [(d, t, False) for t, d in text.df(qg).items()]
        order += [(d, t, True) for t, d in text.df(self._tag_terms(q)).items()]
        return sorted(order)

    def _ranked(self, q: str, layers: Optional[Sequence[MemoryLayer]], limit: int) -> List[Tuple[str, float]]:
        """Q1：按 idf 降序展开倒排，上界剪枝精排，直到可证完成或预算耗尽（见 expansion）。"""
        self.store.text.flush()
        use, qg = _layer_values(layers), bigrams(q)
        order = self._plan(q, qg) if use else []
        hit_tags = {t[len(TAG_PREFIX):] for _, t, tag in order if tag}

        def content_score(content: str, tj: str, known: Optional[bool]) -> float:
            """单节点正文精排。标签加分：标签项已全部展开时直接用倒排结论（known），
            否则惰性解析 JSON（无转义且不含任何命中标签子串 ⇒ 不可能加分，免解析）。"""
            if known is None:
                known = ("\\" in tj or any(t in tj for t in hit_tags)) and tag_hit(q, tags_of(tj))
            s = score(qg, content or "")
            return round(min(1.0, s + TAG_BONUS) if known else s, 6)

        text = self.store.text
        ex = Expansion(self.store.db, len(qg), text.min_grams(), use, limit, content_score,
                       sum(1 for o in order if not o[2]), sum(1 for o in order if o[2]), member=text.members)
        rows, expanded = 0, 0
        for i, (d, term, tag) in enumerate(order):
            if expanded:
                ex.drain(max(REFINE_CAP, d // 2), order[i:])
                if ex.unseen_cleared() and ex.pending() == 0:
                    break
                if rows + d > BUDGET:
                    ex.approx = not ex.unseen_cleared()
                    ex.settle(order[i:])
                    break
            ex.expand(text.postings_g(term), tag)
            rows, expanded = rows + d, expanded + 1
        ex.drain(0)
        self.last_plan = {"terms": len(order), "expanded": expanded, "rows": rows, "approx": ex.approx,
                          "scored": len(ex.done)}
        return ex.top()

    def candidates(self, query: str, layers: Optional[Sequence[MemoryLayer]] = None) -> List[Node]:
        """候选节点（含任一查询二元组或命中标签的可检索节点；整行反序列化，仅供诊断）。"""
        q = (query or "").strip()
        self.store.text.flush()
        ids = self.store.text.postings_any(sorted(bigrams(q)) + self._tag_terms(q)) if q else set()
        use = _layer_values(layers)
        return [n for n in self.store.nodes.get_many(sorted(ids)).values() if n.layer.value in use]

    def search(self, query: str, layers: Optional[Sequence[MemoryLayer]] = None,
               limit: int = 20, touch: bool = True) -> List[Tuple[Node, float]]:
        """内容检索：[(节点, 相关度)]，相关度降序、同分 importance 降序、再按 id。"""
        q = (query or "").strip()
        if not q:
            return []
        top = self._ranked(q, layers, int(limit))
        nodes = self.store.nodes.get_many([t[0] for t in top])
        out = [(nodes[nid], s) for nid, s in top if nid in nodes]
        if touch and out:
            self.store.nodes.touch([n.id for n, _ in out])
            if self.on_hit:
                self.on_hit([n.id for n, _ in out])
        return out

    def recall(self, query: str, limit: int = 10, exclude: Set[str] = frozenset()) -> List[Tuple[Node, float]]:
        """Q4 组合召回。``exclude`` 用于剔除负记忆命中的节点。

        先按相关度取前 max(50, 5·limit) 名（同 :meth:`search`），组合分只读轻量列
        （importance/confidence/last_access/created_at），最后只对入选的 limit 条整行反序列化。"""
        q = (query or "").strip()
        if not q:
            return []
        hits = self._ranked(q, None, max(50, limit * 5))
        light: Dict[str, tuple] = {}
        rows: Dict[str, tuple] = {}
        for part in chunks([nid for nid, _ in hits]):
            for r in self.store.db.all(f"SELECT n.id, n.importance, n.confidence, n.last_access, n.created_at, n.tags, "
                                       f"n.content, i.grams, n.rowid FROM nodes n LEFT JOIN node_index i ON i.node_id = n.id "
                                       f"WHERE n.id IN ({placeholders(len(part))})", part):
                light[r[0]] = tuple(r)[1:6]
                rows[r[0]] = (r[6], r[7], r[8])
        # Q7（:mod:`lingshu_ng.rerank` R1）：池内 idf 重排；df 读写入时维护的 term_df
        rel = {nid: sim for nid, sim in hits if nid in light}
        sims = self.reranker.rerank(q, rel, self.store.text.df(bigrams(q)), rows) if rel else {}
        superseded = self._superseded(list(light))
        t = now()
        scored = []
        for nid, _ in hits:
            if nid in exclude or nid not in light:
                continue
            imp, conf, la, created, tj = light[nid]
            if _retired(imp, tj):
                continue
            sim = sims.get(nid, 0.0) * (SUPERSEDED_FACTOR if nid in superseded else 1.0)
            la = la if la is not None else (created or t)
            recency = 1.0 / (1.0 + max(0.0, t - la) / 86400.0)
            scored.append((nid, round(0.5 * sim + 0.2 * (imp or 0.0) + 0.15 * (conf or 0.0) + 0.15 * recency, 6)))
        scored.sort(key=lambda x: (-x[1], x[0]))
        # Q8（rerank R2）：长文本块之间 MMR 多样化（短节点不受影响）
        scored = self.reranker.diversify(scored, limit, rows, max(sims.values() or [0.0]))
        if self.semantic is not None:
            scored = self._fuse_semantic(q, scored, limit, exclude)
        picked = self._with_opposites(scored[:limit], limit, exclude)
        nodes = self.store.nodes.get_many([nid for nid, _ in picked])
        top = [(nodes[nid], s) for nid, s in picked if nid in nodes]
        if top:
            self.store.nodes.touch([n.id for n, _ in top])
            if self.on_hit:
                self.on_hit([n.id for n, _ in top])
        return top

    def _fuse_semantic(self, q: str, scored: List[Tuple[str, float]], limit: int,
                       exclude: Set[str]) -> List[Tuple[str, float]]:
        """S3：词面名次与语义名次按 semindex.PATTERN 交错；语义候选过 exclude / 退役 / 可检索层过滤。
        语义入选者的分数取前一名的分数（保持非增；居首且无词面命中时取 0.5·余弦）。"""
        cos = {nid: c for nid, c in self.semantic.search(q, 2 * limit + len(exclude)) if nid not in exclude}
        sem = list(cos)
        ok: Set[str] = set()
        use = _layer_values(None)
        for part in chunks(sem):
            for nid, imp, tj, layer in self.store.db.all(
                    f"SELECT id, importance, tags, layer FROM nodes WHERE id IN ({placeholders(len(part))})", part):
                if layer in use and not _retired(imp, tj):
                    ok.add(nid)
        sem = [nid for nid in sem if nid in ok]
        if not sem:
            return scored
        sc = dict(scored)
        out: List[Tuple[str, float]] = []
        for nid in interleave([nid for nid, _ in scored], sem, limit):
            s_ = sc.get(nid)
            floor = out[-1][1] if out else max(sc.values() or [round(0.5 * max(0.0, cos.get(nid, 0.0)), 6)])
            out.append((nid, floor if s_ is None else min(s_, floor)))
        return out

    def _superseded(self, ids: List[str]) -> Set[str]:
        """Q9：ids 中被未退役的新记载取代（auto_supersede 边的 target）的节点。"""
        out: Set[str] = set()
        src: Dict[str, List[str]] = {}
        for part in chunks(ids):
            for s_, t_ in self.store.db.all(
                    f"SELECT source_id, target_id FROM edges WHERE target_id IN ({placeholders(len(part))}) "
                    f"AND relation_type='opposite' AND source_evidence=?", [*part, AUTO_SUPERSEDE]):
                src.setdefault(s_, []).append(t_)
        if not src:
            return out
        for part in chunks(sorted(src)):
            for nid, imp, tj in self.store.db.all(
                    f"SELECT id, importance, tags FROM nodes WHERE id IN ({placeholders(len(part))})", part):
                if not _retired(imp, tj):
                    out.update(src[nid])
        return out

    def _with_opposites(self, ranked: List[Tuple[str, float]], limit: int,
                        exclude: Set[str]) -> List[Tuple[str, float]]:
        """Q6：手工登记的 OPPOSITE 对侧紧随其后（分数取所随节点的分数，保持非增），截断到 limit；
        自动登记的对侧（前 AUTO_TOP 名的）至多 AUTO_SLOTS 条补在末位。"""
        ids = [nid for nid, _ in ranked]
        if not ids:
            return ranked
        partner: Dict[str, List[str]] = {}
        auto: Dict[str, List[str]] = {}
        for part in chunks(ids):
            ph = placeholders(len(part))
            for s_, t_, ev in self.store.db.all(
                    f"SELECT source_id, target_id, source_evidence FROM edges WHERE relation_type='opposite' AND "
                    f"(source_id IN ({ph}) OR target_id IN ({ph}))", [*part, *part]):
                d = auto if is_auto(ev) else partner
                d.setdefault(s_, []).append(t_)
                d.setdefault(t_, []).append(s_)
        if not partner and not auto:
            return ranked
        have = set(ids)
        want = sorted({p for d in (partner, auto) for nid in ids for p in d.get(nid, ())
                       if p not in have and p not in exclude})
        ok: Set[str] = set()
        use = _layer_values(None)
        for part in chunks(want):
            for nid, imp, tj, layer in self.store.db.all(
                    f"SELECT id, importance, tags, layer FROM nodes WHERE id IN ({placeholders(len(part))})", part):
                if layer in use and not _retired(imp, tj):
                    ok.add(nid)
        out: List[Tuple[str, float]] = []
        seen: Set[str] = set()
        for nid, sc in ranked:
            if nid in seen:
                continue
            out.append((nid, sc))
            seen.add(nid)
            for p in sorted(partner.get(nid, ())):
                if p in ok and p not in seen:
                    out.append((p, sc))
                    seen.add(p)
        return _auto_tail(out[:limit], auto, ok, limit)


def _auto_tail(out: List[Tuple[str, float]], auto: Dict[str, List[str]], ok: Set[str],
               limit: int) -> List[Tuple[str, float]]:
    """Q6 自动登记部分：前 AUTO_TOP 名的自动对侧至多 AUTO_SLOTS 条补在末位（挤出末位，所随节点不被挤出），
    分数取保留部分的末位分（保持非增）。"""
    if not auto:
        return out
    seen = {nid for nid, _ in out}
    adds: List[Tuple[str, int]] = []
    for i, (nid, _) in enumerate(out[:AUTO_TOP]):
        for p in sorted(auto.get(nid, ())):
            if p in ok and p not in seen and all(p != a for a, _ in adds):
                adds.append((p, i))
    head, tail = list(out), []
    for p, i in adds[:AUTO_SLOTS]:
        if len(head) + len(tail) < limit:
            tail.append(p)
        elif len(head) - 1 > i:
            head.pop()
            tail.append(p)
        else:
            break
    floor = head[-1][1] if head else 0.0
    return head + [(p, floor) for p in tail]


def _retired(imp, tags_json) -> bool:
    """Q5：归档且未恢复（importance 仍 ≤ 归档值）。"""
    if not tags_json or "archived" not in tags_json:
        return False
    return (imp or 0.0) <= ARCHIVED_IMP_MAX and "archived" in tags_of(tags_json)
