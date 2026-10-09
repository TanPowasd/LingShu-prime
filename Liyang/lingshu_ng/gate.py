# -*- coding: utf-8 -*-
"""gate · 长期记忆门控（快照 / 前馈新奇 / 情境层提升）

旧实现的缺陷类别：回执 layer 与实际落库层不一致(#224/core-rest-01)；「已存在」检索不限层、
命中后裸 SQL 改写共享层并照收来源标签(#217)；t_total 零值域校验直通评分(#206)；
关联边传字符串 relation_type 被吞成 links=0(#195/#44)；新奇度只认汉字(#213)、只看前 80 条(#48)；
默认参数下长期层结构性不可达(#114)；判为情境层的快照直接丢弃、提升通路全仓零调用(#214)。

不变量：
  H1 所有特征值在进入评分前经 numeric 校验并钳制到声明值域；评分 ∈ [0,1]。
  H2 已存在判定 = 规范化内容键精确命中（不靠检索分数阈值），且只在当前角色**可写**的
     层里命中；命中共享层而角色为 SUB ⇒ 不改写（action=unchanged）。
  H3 回执 ``stored_layer`` 永远读回自库；``layer`` 是门控判定（long_term 无独立落点，
     落知识层 + 不可遗忘保护）。
  H4 只升不降：已存在节点 importance 取 max，层只按允许方向提升（context→knowledge）。
  H5 无信任历史时信任特征取中性 0.5（而不是 0），使长期层在默认参数下可达。
  H6 判为情境层的快照落情境层（受 FIFO/衰减管理），由 :meth:`promote_from_context` 再评估。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

from . import dedup
from .dedup import SOURCE_TAGS
from .layers import LayerPolicy
from .novelty import features as novelty_features
from .numeric import require_finite, unit, unit_or_none
from .types import EdgeType, MemoryLayer, Node

if TYPE_CHECKING:  # pragma: no cover
    from .engine import MemoryEngine

__all__ = ["LongTermGate", "WEIGHTS", "LONG_TERM", "KNOWLEDGE"]

WEIGHTS = {"novelty": 0.30, "trust": 0.25, "d2": 0.15, "t2": 0.15, "mention": 0.15}
LONG_TERM = 0.70
KNOWLEDGE = 0.40
NOVEL_TRIGGER = 0.75
NOVEL_BOOST = 0.15
LINK_SIM = 0.25


def _decide(imp: float) -> str:
    return "long_term" if imp >= LONG_TERM else "knowledge" if imp >= KNOWLEDGE else "context"


def _second_diff(vals: List[float]) -> float:
    if len(vals) < 3:
        return 0.0
    d1 = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    return max(-0.5, min(0.5, d1[-1] - d1[0]))


class LongTermGate:
    """挂在 :class:`MemoryEngine` 上的门控（无自有状态）。"""

    def __init__(self, engine: "MemoryEngine", weights: Optional[Dict[str, float]] = None) -> None:
        self.engine = engine
        self.weights = dict(WEIGHTS)
        for k, v in (weights or {}).items():
            if k not in WEIGHTS:
                raise ValueError(f"未知权重: {k}")
            self.weights[k] = unit(v, k)

    # ------------------------------------------------------------ 特征（H1/H5）
    def _reference(self, exclude: Optional[str]) -> Iterable[str]:
        """全量参照正文（暴力基线；线上新奇度走 store.text 的增量特征计数）。"""
        layers = LayerPolicy.layers(searchable=True)
        for n in self.engine.store.nodes.scan(layers):
            if n.id != exclude:
                yield n.content or ""

    def features(self, content: str, existing_id: Optional[str] = None) -> Dict[str, float]:
        """特征向量（全部已钳制）。"""
        sm = self.engine.self_store.model
        th = [require_finite(h["t_total"], "t_total") for h in sm.trust_history[-6:]]
        trust = unit(sm.trust_state.get("t_total", 0.5), "t_total") if th else 0.5
        gaps = [require_finite(g["d_norm"], "d_norm") for g in self.engine.store.meta.gaps(5)]
        mention = 0
        if existing_id:
            n = self.engine.store.nodes.get(existing_id)
            mention = int(n.access_count or 0) if n else 0
        return {"novelty": unit(self.engine.store.text.novelty(content, existing_id)),
                "trust": trust, "d2": _second_diff(gaps), "t2": _second_diff(th), "mention": mention}

    def score(self, f: Dict[str, float]) -> float:
        """线性评分（mention 以 n/(n+2) 平滑，最多贡献其权重）。"""
        w = self.weights
        m = f["mention"] / (f["mention"] + 2.0)
        s = (w["novelty"] * f["novelty"] + w["trust"] * f["trust"] + w["d2"] * max(0.0, f["d2"]) * 2
             + w["t2"] * max(0.0, f["t2"]) * 2 + w["mention"] * m)
        return unit(s)

    def evaluate(self, content: str, existing_id: Optional[str] = None) -> Dict:
        """评估：特征 → 评分 → 层级判定。"""
        f = self.features(content, existing_id)
        imp = self.score(f)
        layer = _decide(imp)
        return {"importance": round(imp, 3), "layer": layer,
                "features": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()},
                "decision": {"long_term": f"长期记忆（imp={imp:.2f}≥{LONG_TERM}）",
                             "knowledge": f"知识层（imp={imp:.2f}）",
                             "context": f"情境层（imp={imp:.2f}，可提升）"}[layer]}

    # ------------------------------------------------------------ 已存在（H2）
    def _existing(self, content: str) -> Optional[Node]:
        """精确内容键命中的最早节点——只在快照可写的本地层（非共享层）里找（上游 #217）：
        锚点/结构层同文节点既不被快照的更新分支改写，也不被冒充为本次快照的落点；
        快照照常在本地层新建（与旧 write_snapshot 只查知识/情境层同口径）。"""
        hits = self.engine.store.nodes.by_key(dedup.content_key(content),
                                              LayerPolicy.layers(searchable=True, shared=False))
        return hits[0] if hits else None

    def _merge_tags(self, node: Node, tags: List[str]) -> List[str]:
        own = {t for t in node.tags if t.lower() in SOURCE_TAGS}
        keep = [t for t in tags if t.lower() not in SOURCE_TAGS or t in own]
        return list(dict.fromkeys(node.tags + keep))

    # ------------------------------------------------------------ 快照
    def write_snapshot(self, content: str, source: str = "snapshot", tags: Optional[List[str]] = None,
                       entities: Optional[List[str]] = None, importance_hint: Optional[float] = None) -> Dict:
        """快照写入（H2–H6）。"""
        hint = unit_or_none(importance_hint, "importance_hint")
        tags = list(tags or [])
        existing = self._existing(content)
        ev = self.evaluate(content, existing.id if existing else None)
        imp = hint if hint is not None else ev["importance"]
        layer = _decide(imp)
        eng = self.engine
        if existing is not None:
            if LayerPolicy.rule(existing.layer).shared and not eng.store.policy.is_primary:
                return self._receipt(existing.id, imp, layer, ev, action="unchanged",
                                     reason="命中共享层节点，当前角色不可改写")
            node_id = existing.id
            new_layer = existing.layer
            if layer != "context" and existing.layer == MemoryLayer.CONTEXT:
                new_layer = MemoryLayer.KNOWLEDGE
            eng.store.nodes.update(node_id, allow_transition=True, layer=new_layer,
                                   importance=max(existing.importance or 0.0, imp),
                                   tags=self._merge_tags(existing, tags + [f"ent:{e}" for e in entities or []]))
            action = "updated"
        elif layer == "context":
            node_id = eng.add_context(content, importance=imp, tags=tags + ["gate"],
                                      entities=entities).node_id
            action = "created"
        else:
            node_id = eng.perceive(content, importance=imp, tags=tags + ["gate"], entities=entities,
                                   skip_dedup=True).node_id
            action = "created"
        out = self._receipt(node_id, imp, layer, ev, action=action)
        if layer == "long_term":
            out["protected"] = eng.protect(node_id, f"LongTermGate:{source}")
            out["links"] = self._link(node_id, content)
        return out

    def _receipt(self, node_id: Optional[str], imp: float, layer: str, ev: Dict,
                 action: str, reason: str = "") -> Dict:
        stored = self.engine.store.nodes.layer_of(node_id) if node_id else None
        return {"status": "ok", "node_id": node_id, "importance": round(imp, 3), "layer": layer,
                "stored_layer": stored.value if stored else None, "features": ev["features"],
                "action": action, "reason": reason}

    def _link(self, node_id: str, content: str) -> int:
        """与最相似的既有节点建 SIMILAR 边（枚举类型，失败不吞）。"""
        n = 0
        for other, sim in self.engine.retriever.search(content, limit=4, touch=False):
            if other.id != node_id and sim >= LINK_SIM:
                self.engine.link(node_id, other.id, EdgeType.SIMILAR, evidence="inferred")
                n += 1
        return n

    # ------------------------------------------------------------ 前馈（H1 海马体）
    def prefeed(self, content: str, source: str = "input", tags: Optional[List[str]] = None,
                entities: Optional[List[str]] = None) -> Dict:
        """高新奇输入当场强化编码；否则 routine（不写库）。"""
        text = self.engine.store.text
        nov = unit(text.novelty(content, None))
        if nov < NOVEL_TRIGGER:
            # novelty_basis 区分「不新」与「看不见」（上游 #213）：none = 输入无可比较单元
            grams, idents = novelty_features(content)
            basis = "none" if not (grams or idents) else ("units" if text.has_reference() else "no_reference")
            return {"novel": False, "novelty": round(nov, 3), "novelty_basis": basis, "action": "routine"}
        imp = min(1.0, self.evaluate(content)["importance"] + NOVEL_BOOST)
        all_tags = list(dict.fromkeys(list(tags or []) + ["novel_prefeed", "gate"]))
        node_id = self.engine.perceive(content, importance=imp, tags=all_tags, entities=entities,
                                       skip_dedup=True).node_id
        links = self._link(node_id, content)
        if imp >= LONG_TERM:
            self.engine.protect(node_id, f"Prefeed:{source}")
        return {"novel": True, "novelty": round(nov, 3), "action": "prefeed_boost",
                "node_id": node_id, "importance": round(imp, 3), "links": links}

    # ------------------------------------------------------------ 情境层提升（H6）
    def promote_from_context(self, limit: Optional[int] = 30) -> List[Dict]:
        """重新评估情境节点，够格者升知识层（long_term 另加保护）。"""
        out = []
        for n in self.engine.store.nodes.query(layer=MemoryLayer.CONTEXT, limit=limit):
            ev = self.evaluate(n.content or "", n.id)
            if ev["layer"] == "context":
                continue
            self.engine.store.nodes.update(
                n.id, allow_transition=True, layer=MemoryLayer.KNOWLEDGE,
                importance=max(n.importance or 0.0, ev["importance"]),
                tags=list(dict.fromkeys(n.tags + ["promoted"])))
            if ev["layer"] == "long_term":
                self.engine.protect(n.id, "LongTermGate:promote")
            out.append({"node_id": n.id, "importance": ev["importance"], "layer": ev["layer"]})
        return out
