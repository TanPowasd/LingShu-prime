# -*- coding: utf-8 -*-
"""prediction · 预测引擎（旧 ``lingshu.world.prediction`` 的 ng 实现，同名 API）。

「图结构的过去 + 结构 → 候选未来集合」：因果路线图（D-001/D-004）、语义邻近过滤门（D-002）、
3D 轨迹外推有效性（D-003）、注意力偏好适配器（D-005）、命中率校准（D-006）。
``engine`` 是旧核心对象（duck-typed：``engine.store.get_node/query_nodes/get_outgoing_edges/
get_incoming_edges/verify_edge``、``engine.register_rejected_path/add_perception/...``）。

判据口径（与旧版的差异即缺陷修正）：

- **D-006 如实**：旧原式 ``max(BASE, mean−2σ)`` 与同一个 mean 比较，动态项对判定零影响，
  返回的 threshold 还可能高于真实判据。这里 threshold 恒为固定基线 ``BASE_HIT_RATE``，
  ``reflect ⇔ samples ≥ MIN_SAMPLES 且 mean < threshold``，``dynamic: False`` 明示没有动态项；
  「近期窗口 vs 长期基线」的退化检测口径待 owner 决定（issue world-08），不擅自发明。
- **命中标签只收真布尔**：旧版 ``bool("false") is True``、``nan`` 也算命中；这里只接受
  bool / numpy bool / 整数 0、1，其余抛 ``ValueError``（不进入命中率历史）。
- **置信度 isfinite**：非有限的边置信度不参与候选与强化（旧版 ``min(1.0, nan+0.05)``
  会把 NaN 边静默改写成 1.0）；路线评分各维度若非有限按 0 计并标 ``non_finite``。
"""
from __future__ import annotations

import json
import math
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

__all__ = ["PredictionEngine", "dynamic_hit_threshold", "as_hit"]

CAUSAL = ("causal", "sequential")


def as_hit(hit: object) -> bool:
    """命中标签归一：bool / numpy bool / 整数 0、1；其余（字符串、浮点、None）拒收。"""
    if isinstance(hit, bool):
        return hit
    if isinstance(hit, np.bool_):
        return bool(hit)
    if isinstance(hit, int) and hit in (0, 1):
        return bool(hit)
    raise ValueError(f"hit must be a boolean, got {hit!r}")


def dynamic_hit_threshold(history: List[bool], base: float, min_samples: int) -> Dict:
    """D-006：reflect ⇔ 样本 ≥ min_samples 且 命中率 < base；返回的 threshold 就是判据边界。"""
    n = len(history)
    if n < min_samples:
        return {"threshold": base, "samples": n, "reflect": False,
                "note": "样本不足（<%d），不触发反思" % min_samples}
    mean = sum(1 for h in history if h) / n
    return {"threshold": round(base, 4), "samples": n, "reflect": mean < base,
            "mean": round(mean, 4), "dynamic": False}


def _finite(x: object) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _cs_dict(cs: object) -> Dict:
    if cs is None:
        return {}
    try:
        return json.loads(cs.to_json())
    except Exception:
        return {}


class PredictionEngine:
    """预测引擎：候选未来集合（非确定性输出）+ 验证闭环。"""

    MIN_SAMPLES = 50
    BASE_HIT_RATE = 0.40
    HISTORY_CAP = 200

    def __init__(self, engine, attention_policy=None):
        self.engine = engine
        self.attention_policy = attention_policy
        self.prediction_log: List[Dict] = []
        self._hit_history: List[bool] = []

    @property
    def _store(self):
        return self.engine.store

    # ==================== 语义邻近 + 过滤门（D-002） ====================

    def semantic_neighbors(self, node_id: str, k: int = 5) -> List:
        center = self._store.get_node(node_id)
        if not center:
            return []
        scored = []
        for n in self._store.query_nodes(limit=300):
            sim = self._similarity(center, n) if n.id != node_id else 0.0
            if sim > 0.05:
                scored.append((n, sim))
        scored.sort(key=lambda x: -x[1])
        return [n for n, _ in scored[:k]]

    def _similarity(self, a, b) -> float:
        """语义坐标相似度（优先）或二元组 Jaccard（回退）；外部模块缺失 → 0；非有限 → 0。"""
        try:
            from spacetime_memory_core import LayeredStore
        except Exception:
            return 0.0
        sc_a = getattr(a, "semantic_coordinates", {}) or {}
        sc_b = getattr(b, "semantic_coordinates", {}) or {}
        v = None
        if sc_a and sc_b:
            try:
                from semantic_space import SemanticSpaceProvider
                v = SemanticSpaceProvider.similarity_coordinates(sc_a, sc_b)
            except Exception:
                v = None
        if v is None:
            v = LayeredStore.char_bigram_jaccard(a.content, b.content)
        return _finite(v) or 0.0

    def has_causal_link(self, a_id: str, b_id: str) -> bool:
        return any(e.target_id == b_id and e.relation_type.value in CAUSAL
                   for e in self._store.get_outgoing_edges(a_id))

    def has_structural_pattern(self, a_id: str, b_id: str) -> bool:
        pa = {e.source_id for e in self._store.get_incoming_edges(a_id)}
        pb = {e.source_id for e in self._store.get_incoming_edges(b_id)}
        return bool(pa & pb)

    def _preference_weight(self, content: str) -> float:
        """D-005：注意力偏好权重；无策略/异常/非有限 → 0（回退边置信度排序）。"""
        if self.attention_policy is None:
            return 0.0
        try:
            w = self.attention_policy.get_weights()
            score = 0.0
            if "存在" in content or "威胁" in content:
                score += w.get("existence", 1.0)
            if "信任" in content:
                score += w.get("trust", 0.8)
            if "信息差" in content or "盲区" in content:
                score += w.get("gap", 0.6)
        except Exception:
            return 0.0
        return _finite(score) or 0.0

    def _branch_candidates(self, start_id: str) -> List[Tuple[str, float, str]]:
        """causal（边置信度）> structural（0.6）> semantic_induced（0.3）；非有限置信度的边跳过。"""
        cands, seen = [], set()
        for e in self._store.get_outgoing_edges(start_id):
            c = _finite(e.confidence)
            if e.relation_type.value in CAUSAL and c is not None:
                cands.append((e.target_id, c, "causal"))
                seen.add(e.target_id)
        for n in self.semantic_neighbors(start_id, k=5):
            if n.id in seen:
                continue
            if self.has_causal_link(start_id, n.id):
                cands.append((n.id, 0.6, "structural_causal"))
            elif self.has_structural_pattern(start_id, n.id):
                cands.append((n.id, 0.6, "structural_pattern"))
            elif self._preference_weight(n.content) > 0.8:
                cands.append((n.id, 0.3, "semantic_induced"))
        return cands

    # ==================== 生成式预测：因果路线图 ====================

    def predict_routes(self, start_id: str = None, blindspot_id: str = None,
                       horizon: int = 3, max_branches: int = 5) -> Dict:
        """候选未来路径集合；盲区驱动时 unknowable 盲区不生成路线（D-003）。"""
        if blindspot_id is None:
            if start_id is None:
                return {"status": "no_start", "routes": []}
            return self._generate_routes(start_id, horizon, max_branches)
        bs = self._find_blindspot(blindspot_id)
        if bs is None:
            return {"status": "blindspot_not_found", "routes": []}
        if bs.get("predictability") == "unknowable":
            return {"status": "unpredictable", "reason": "structural_unknowability", "routes": []}
        anchor = self._anchor_from_description(bs.get("description", ""))
        if anchor is None:
            return {"status": "no_anchor", "routes": []}
        result = self._generate_routes(anchor, horizon, max_branches)
        result["meta"]["blindspot_id"] = blindspot_id
        return result

    def _cs_label(self, node_id: str, edge_cs=None) -> str:
        """该步条件：边条件空间 → 节点条件空间 → 待定（取存在约束，截 40 字）。"""
        ec = str(_cs_dict(edge_cs).get("existence_constraint", "")).strip()
        if not ec:
            try:
                n = self._store.get_node(node_id)
                ec = str(_cs_dict(getattr(n, "condition_space", None))
                         .get("existence_constraint", "")).strip()
            except Exception:
                ec = ""
        return ec[:40] if ec else "待定（条件空间未声明）"

    def _edge_cs(self, src: str, dst: str):
        try:
            for e in self._store.get_outgoing_edges(src):
                if e.target_id == dst and e.relation_type.value in CAUSAL:
                    return e.condition_space
        except Exception:
            pass
        return None

    def _walk(self, routes: List[Dict], cur: str, path: List[str], conds: List[str],
              depth: int, conf: float, horizon: int, max_branches: int) -> None:
        if depth >= horizon:
            return
        for nid, ec, src in self._branch_candidates(cur)[:max_branches]:
            new_path, c = path + [nid], conf * ec
            new_conds = conds + [self._cs_label(nid, self._edge_cs(cur, nid))]
            routes.append({"path": new_path, "conf": round(c, 4), "source": src,
                           "conditions": new_conds})
            self._walk(routes, nid, new_path, new_conds, depth + 1, c, horizon, max_branches)

    def _generate_routes(self, start_id: str, horizon: int, max_branches: int) -> Dict:
        routes: List[Dict] = []
        self._walk(routes, start_id, [start_id], ["起点（观测条件）"], 0, 1.0, horizon, max_branches)
        scored = [{**r, "score": self._score_route(r), "uncertainty_bound": self._uncertainty(r["conf"])}
                  for r in routes]
        scored.sort(key=lambda r: -r["score"]["composite"])
        self.prediction_log.append({"type": "predict_routes", "start": start_id,
                                    "routes": len(scored), "ts": time.time()})
        return {"routes": scored,
                "meta": {"horizon": horizon, "start": start_id,
                         "note": "候选未来集合，非必然未来（0.0.3 局部不可知）；"
                                 "每条路线含条件空间序列（预演规划 H2）"}}

    def _find_blindspot(self, blindspot_id: str) -> Optional[Dict]:
        try:
            return next((b for b in self.engine.list_blindspots() if b["id"] == blindspot_id), None)
        except Exception:
            return None

    def _anchor_from_description(self, description: str) -> Optional[str]:
        """盲区描述的锚点：内容检索优先，语义坐标相似度回退（优先有出边的节点）。"""
        try:
            hits = self.engine.search_content(description, limit=3)
            if hits:
                return hits[0][0].id
        except Exception:
            pass
        try:
            return self._anchor_by_semantics(description)
        except Exception:
            return None

    def _anchor_by_semantics(self, description: str) -> Optional[str]:
        from semantic_space import SemanticSpaceProvider
        q = SemanticSpaceProvider().to_semantic_coordinates(description)
        best, best_routed = (None, 0.0), (None, 0.0)
        for n in self._store.query_nodes(limit=300):
            sc = getattr(n, "semantic_coordinates", {}) or {}
            sim = _finite(SemanticSpaceProvider.similarity_coordinates(q, sc)) if sc else None
            if sim is None:
                continue
            if sim > best[1]:
                best = (n.id, sim)
            if sim > best_routed[1] and self._store.get_outgoing_edges(n.id):
                best_routed = (n.id, sim)
        for nid, sim in (best_routed, best):
            if nid and sim > 0.05:
                return nid
        return None

    # ==================== 评分（D-004）====================

    def _score_route(self, route: Dict) -> Dict:
        """T_pred 四维度：trend·boundary·verification·balance（权重 .40/.20/.25/.15）。"""
        dims = {"trend": route["conf"], "boundary": self._boundary_consistency(route["path"]),
                "verification": self._hit_rate(), "balance": self._branch_diversity(route["path"])}
        bad = [k for k, v in dims.items() if _finite(v) is None]
        dims = {k: round(_finite(v) or 0.0, 4) for k, v in dims.items()}
        dims["composite"] = round(0.40 * dims["trend"] + 0.20 * dims["boundary"]
                                  + 0.25 * dims["verification"] + 0.15 * dims["balance"], 4)
        if bad:
            dims["non_finite"] = bad
        return dims

    def _boundary_consistency(self, path: List[str]) -> float:
        if not path:
            return 0.0
        ok = 0
        for nid in path:
            n = self._store.get_node(nid)
            ok += bool(n and ("boundary" in n.tags or "不确定" in n.content or "边界" in n.content))
        return round(ok / len(path), 4)

    def _hit_rate(self) -> float:
        h = self._hit_history
        return round(sum(1 for x in h if x) / len(h), 4) if h else 0.0

    def _branch_diversity(self, path: List[str]) -> float:
        dims = set()
        for nid in path:
            n = self._store.get_node(nid)
            if n:
                dims.update((n.semantic_coordinates or {}).get("protocol", {}))
        return round(min(1.0, len(dims) / 4.0), 4)

    def _uncertainty(self, conf: float) -> Dict:
        base = 1.0 - conf
        return {"lower": round(max(0.0, conf - base * 0.5), 4),
                "upper": round(min(1.0, conf + base * 0.5), 4)}

    # ==================== 验证闭环（D-006）====================

    def update_prediction_feedback(self, predicted_node_id: str, actual_node_id: str,
                                   hit: bool, note: str = "") -> Dict:
        """命中 → 入边强化 +0.05（仅有限置信度）；未命中 → 被拒路径 + 自动条件化。"""
        hit = as_hit(hit)
        self._hit_history = (self._hit_history + [hit])[-self.HISTORY_CAP:]
        if hit and predicted_node_id == actual_node_id:
            for e in self._store.get_incoming_edges(predicted_node_id):
                c = _finite(e.confidence)
                if e.relation_type.value in CAUSAL and c is not None:
                    self._store.verify_edge(e.id, min(1.0, c + 0.05))
        elif not hit:
            self._register_miss(predicted_node_id, actual_node_id, note)
        return self._dynamic_hit_threshold()

    def _content_of(self, node_id: str) -> str:
        try:
            n = self._store.get_node(node_id)
        except Exception:
            n = None
        return (getattr(n, "content", "") or "")[:80] if n is not None else ""

    def _register_miss(self, predicted_id: str, actual_id: str, note: str) -> None:
        # #216 ⑤：负记忆同时存两端内容摘要（只存 id 时 find_rejected_paths 的文本匹配恒 0 命中）
        pc, ac = self._content_of(predicted_id), self._content_of(actual_id)
        try:
            self.engine.register_rejected_path(
                path_type="prediction",
                description=f"预测未命中：{pc}［{predicted_id}］" + (f"（{note}）" if note else ""),
                reason=f"实际：{ac}［{actual_id}］")
        except Exception:
            pass
        try:
            self._auto_conditionize(predicted_id, actual_id)
        except Exception:
            pass

    @staticmethod
    def _missing_conditions(p_cs: Dict, a_cs: Dict) -> List[str]:
        missing = []
        p_ec = str(p_cs.get("existence_constraint", "")).strip()
        a_ec = str(a_cs.get("existence_constraint", "")).strip()
        if a_ec and a_ec != p_ec:
            missing.append(f"缺失条件：{a_ec}")
        a_pos = str(a_cs.get("observation_position", "")).strip()
        p_pos = str(p_cs.get("observation_position", "")).strip()
        if a_pos and a_pos != p_pos and "外部" not in a_pos:
            missing.append(f"缺失条件：观测位置[{a_pos}]")
        return missing

    def _auto_conditionize(self, predicted_id: str, actual_id: str) -> List[str]:
        """未命中：实际节点有、预测节点没有的条件 → 条件候选节点。"""
        try:
            pn, an = self._store.get_node(predicted_id), self._store.get_node(actual_id)
        except Exception:
            return []
        if not pn or not an:
            return []
        missing = self._missing_conditions(_cs_dict(pn.condition_space), _cs_dict(an.condition_space))
        created = []
        for cond in missing:
            try:
                node = self.engine.add_perception(
                    content=f"[条件候选] {cond}（预测误差自动条件化：{predicted_id}→{actual_id}）",
                    importance=0.7,
                    tags=["condition_candidate", "auto_conditionized", "prediction_error"])
                created.append(node.id)
            except Exception:
                pass
        if created:
            self.prediction_log.append({"type": "auto_conditionize", "predicted": predicted_id,
                                        "actual": actual_id, "conditions": missing,
                                        "created": created, "ts": time.time()})
        return created

    def _dynamic_hit_threshold(self) -> Dict:
        return dynamic_hit_threshold(self._hit_history, self.BASE_HIT_RATE, self.MIN_SAMPLES)

    # ==================== 2D 语义地图 / 3D 时空立方体 ====================

    @staticmethod
    def _axis_xy(node, axes: List[str]) -> Tuple[float, float]:
        concept = (node.semantic_coordinates or {}).get("protocol", {}).get("concept", {})
        x = _finite(concept.get(axes[0], 0.0)) if axes else 0.0
        y = _finite(concept.get(axes[1], 0.0)) if len(axes) > 1 else 0.0
        return x or 0.0, y or 0.0

    def render_semantic_map_2d(self, limit: int = 50) -> Dict:
        nodes = self._store.query_nodes(limit=limit)
        axes = self._top_axes(nodes, 2)
        pos = {}
        for n in nodes:
            x, y = self._axis_xy(n, axes)
            pos[n.id] = {"x": round(x, 4), "y": round(y, 4), "content": n.content[:12]}
        return {"axes": axes, "positions": pos, "count": len(pos),
                "note": "ND 语义空间 2D 有损投影（盲区25）"}

    @staticmethod
    def _validity(delta: float) -> str:
        if delta < 0.05:
            return "smooth"
        return "jump" if delta >= 0.3 else "unknown"

    def render_semantic_cube_3d(self, entity_id: str = None, limit: int = 50) -> Dict:
        nodes = self._store.query_nodes(limit=limit)
        if entity_id:
            nodes = [n for n in nodes if n.entity_id == entity_id
                     or (n.tags and f"ent:{entity_id}" in n.tags)]
        if not nodes:
            return {"entity_id": entity_id, "trajectory": [], "note": "无轨迹数据"}
        axes = self._top_axes(nodes, 2)
        traj: List[Dict] = []
        for n in sorted(nodes, key=lambda n: n.temporal_coordinate):
            x, y = self._axis_xy(n, axes)
            pt = {"id": n.id, "t": round(n.temporal_coordinate, 4), "x": round(x, 4), "y": round(y, 4)}
            if traj:
                pt["extrapolation_validity"] = self._validity(
                    abs(pt["x"] - traj[-1]["x"]) + abs(pt["y"] - traj[-1]["y"]))
            traj.append(pt)
        return {"entity_id": entity_id, "axes": axes, "trajectory": traj,
                "note": "外推仅在 smooth 区间有效（D-003）"}

    @staticmethod
    def _top_axes(nodes: List, n: int) -> List[str]:
        freq: Dict[str, int] = {}
        for node in nodes:
            for k in (node.semantic_coordinates or {}).get("protocol", {}).get("concept", {}):
                freq[k] = freq.get(k, 0) + 1
        return sorted(freq, key=freq.get, reverse=True)[:n]
