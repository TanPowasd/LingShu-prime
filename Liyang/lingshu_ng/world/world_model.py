# -*- coding: utf-8 -*-
"""world_model · 统一世界模型（旧 ``lingshu.world.world_model`` 的 ng 实现，同名 API）。

世界图（节点 + 关系边 + 观测历史）+ 三端口：perceive（观测→图）、generate（图→候选未来）、
verify（外部观察者：生成 vs 最近一次真实观测快照）。模型只读 perceive 给它的位置与类别。

与旧版相比修正的缺陷类别：

- **seed 不透传**：旧构造器持有 seed 却不传给 SceneSimulator，物理世界恒为 42；这里透传。
- **生成 eid 不查重**：6 位 hex 的生日碰撞会让新实体命中既有节点、被静默合并；这里查重，
  并且同一轮 perceive 内一个既有节点至多被一个无 eid 观测认领（旧版两个同类观测可同时
  并到同一节点）。
- **推断边只增不退**：同源推断出新关系时旧推断边退场并留痕 ``patterns()["superseded"]``；
  假设节点（wm_simloop 生长，``attrs["hypothesis"]``）的边不在此处取代。
- 观测位置拒收 NaN/inf（旧版混入后 math.dist 产出 nan，nan < bound 恒假，被静默记成异常）。
- verify 的 actual 只取最近一次 perceive 的真实观测快照，未观测的预测标 pending 不计分。
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .scene_sim import SceneSimulator, normalize_xz
from .validate import finite_vec3

__all__ = ["WMNode", "WMEdge", "UnifiedWorldModel", "motion_stats", "pair_tendency",
           "pair_tendency_n"]

Vec3 = Tuple[float, float, float]
_HEX = "0123456789abcdef"
TRACK_RADIUS = 2.0


@dataclass
class WMNode:
    """世界图节点：实体在模型内部的状态（仅由观测更新）。"""
    eid: str
    category: str
    pos: Vec3
    confidence: float = 0.5
    behavior_inferred: str = "unknown"
    first_seen: int = 0
    last_seen: int = 0
    attrs: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class WMEdge:
    """世界图关系边（evidence: observed/inferred）。"""
    source: str
    relation: str
    target: str
    confidence: float = 0.5
    evidence: str = "inferred"

    def to_dict(self) -> Dict:
        return asdict(self)


def _moves(history: List[Dict], eid: str) -> List[Tuple[float, float]]:
    """连续两次都被观测到的 xz 位移序列。"""
    out, prev = [], None
    for rec in history:
        cur = rec["entities"].get(eid)
        if cur is not None and prev is not None:
            out.append((cur[0] - prev[0], cur[2] - prev[2]))
        prev = cur
    return out


def motion_stats(history: List[Dict], eid: str) -> Tuple[float, float]:
    """(方向一致性 |mean unit| ∈[0,1]，平均步长)；无位移 → (0, 0.3)。"""
    return stats_from_moves(_moves(history, eid))


def stats_from_moves(moves: List[Tuple[float, float]]) -> Tuple[float, float]:
    """:func:`motion_stats` 的位移序列版（调用方已抽好位移）。"""
    if not moves:
        return 0.0, 0.3
    speed = sum(math.hypot(*m) for m in moves) / len(moves)
    units = [(m[0] / math.hypot(*m), m[1] / math.hypot(*m)) for m in moves if math.hypot(*m) > 1e-6]
    if not units:
        return 0.0, round(speed, 3)
    mx = sum(u[0] for u in units) / len(units)
    mz = sum(u[1] for u in units) / len(units)
    return round(math.hypot(mx, mz), 3), round(speed, 3)


def pair_tendency(history: List[Dict], a: str, b: str) -> float:
    """a 对 b 的趋向均值 cos(位移_a, a→b)：>0.5 趋向 / <−0.5 远离。"""
    return pair_tendency_n(history, a, b)[0]


def pair_tendency_n(history: List[Dict], a: str, b: str) -> Tuple[float, int]:
    """(趋向均值, 样本数)；``history`` 每项 ``{"entities": {eid: (x, y, z)}}``。"""
    scores, prev = [], None
    for rec in history:
        ea, eb = rec["entities"].get(a), rec["entities"].get(b)
        if ea is None or eb is None:
            prev = None
            continue
        if prev is not None:
            dx, dz = ea[0] - prev[0], ea[2] - prev[2]
            tx, tz = eb[0] - ea[0], eb[2] - ea[2]
            dl, tl = math.hypot(dx, dz), math.hypot(tx, tz)
            if dl > 1e-6 and tl > 1e-6:
                scores.append((dx * tx + dz * tz) / (dl * tl))
        prev = ea
    return (round(sum(scores) / len(scores), 3) if scores else 0.0), len(scores)


def window_series(history: List[Dict], eids: List[str], key: Optional[str] = None
                  ) -> Tuple[Dict[str, List], Dict[str, List], Dict[str, Tuple[float, float]]]:
    """一次抽出窗口内每实体的位置序列（缺测 None）、有效位移 (dx, dz, |d|)（|d|>1e-6）
    与 :func:`motion_stats`。``key`` 非空时观测项是 ``{key: pos}``（WorldLearner 口径）。

    与逐对 :func:`pair_tendency_n` / :func:`motion_stats` 逐位相同，配对时免去逐对重扫历史。"""
    ser: Dict[str, List] = {}
    disp: Dict[str, List] = {}
    stats: Dict[str, Tuple[float, float]] = {}
    n = len(history)
    for eid in eids:
        s_: List = [None] * n
        for i, r in enumerate(history):
            ent = r["entities"].get(eid)
            if ent is not None:
                s_[i] = ent if key is None else ent[key]
        moves, d_ = [], [None] * n
        for i in range(1, n):
            cur, prev = s_[i], s_[i - 1]
            if cur is not None and prev is not None:
                dx, dz = cur[0] - prev[0], cur[2] - prev[2]
                moves.append((dx, dz))
                dl = math.hypot(dx, dz)
                if dl > 1e-6:
                    d_[i] = (dx, dz, dl)
        ser[eid], disp[eid], stats[eid] = s_, d_, stats_from_moves(moves)
    return ser, disp, stats


def best_tendency(a: str, eids: List[str], ser: Dict, disp: Dict,
                  min_n: int = 1) -> Tuple[Optional[str], float]:
    """a 的趋向均值 |c| 最大（严格大于，先到先得）且样本 ≥ min_n 的目标 → (目标, c)。"""
    sa, da = ser[a], disp[a]
    idx = [i for i in range(1, len(sa)) if da[i] is not None]
    best_t, best_c = None, 0.0
    for b in eids:
        if b == a:
            continue
        sb, scores = ser[b], []
        for i in idx:
            eb = sb[i]
            if eb is None or sb[i - 1] is None:
                continue
            tx, tz = eb[0] - sa[i][0], eb[2] - sa[i][2]
            tl = math.hypot(tx, tz)
            if tl > 1e-6:
                dx, dz, dl = da[i]
                scores.append((dx * tx + dz * tz) / (dl * tl))
        if scores and len(scores) >= min_n:
            c = round(sum(scores) / len(scores), 3)
            if abs(c) > abs(best_c):
                best_t, best_c = b, c
    return best_t, best_c


class UnifiedWorldModel:
    """统一世界模型：世界图 + 理解/生成/验证三端口（物理世界在模型之外）。"""

    def __init__(self, size: int = 24, ground_level: int = 1, seed: int = 42,
                 world: Optional[SceneSimulator] = None):
        self.world = world or SceneSimulator(size=size, ground_level=ground_level, seed=seed)
        self.size = self.world.world.size
        self.nodes: Dict[str, WMNode] = {}
        self.edges: List[WMEdge] = []
        self.history: List[Dict] = []
        self.tick = 0
        self._conditions: Dict[str, Dict] = {}
        self._last_prediction: Dict[str, Dict] = {}
        self._compare: Dict = {}
        self._obs_snapshot: Optional[Dict[str, List[float]]] = None
        self._obs_tick: Optional[int] = None
        self._anomalies: List[Dict] = []
        self._patterns: Dict = {}
        self._rng = random.Random(seed)
        self.pad = 0.2
        self.hit_threshold = 0.5
        self.entropy_threshold = 0.7

    # ================= 理解端口 =================

    def _observe_world(self) -> List[Dict]:
        return [{"eid": eid, "category": e.category, "pos": tuple(e.pos)}
                for eid, e in self.world.entities.items()]

    def _new_eid(self) -> str:
        for n in (6,) * 8 + (12,) * 8:
            cand = "wm_" + "".join(self._rng.choice(_HEX) for _ in range(n))
            if cand not in self.nodes:
                return cand
        raise RuntimeError("eid space exhausted")

    def _track_identity(self, o: Dict, claimed: Optional[Set[str]] = None) -> str:
        """无 eid 观测：同类别、追踪半径内、本轮未被认领的最近节点；否则新 eid（查重）。"""
        claimed = claimed if claimed is not None else set()
        pos = tuple(o["pos"])
        best = min(((math.dist(n.pos, pos), eid) for eid, n in self.nodes.items()
                    if n.category == o["category"] and eid not in claimed), default=None)
        if best is not None and best[0] < TRACK_RADIUS:
            return best[1]
        return self._new_eid()

    def _assign_identities(self, obs: List[Dict]) -> Dict[int, str]:
        """#226：本帧无 eid 观测与已有节点的一一匹配——显式 eid 先认领；其余按**本帧起始位置**、
        距离升序全局贪心（同类别、追踪半径内），与观测顺序无关。未匹配者交给 _ingest 生成新 eid。"""
        explicit = {str(o.get("eid", "") or "") for o in obs} - {""}
        pairs = []
        for i, o in enumerate(obs):
            if str(o.get("eid", "") or ""):
                continue
            try:
                pos = tuple(float(v) for v in finite_vec3(o["pos"], "observation pos"))
            except Exception:                      # noqa: BLE001 —— 非法坐标留给 _ingest 报错
                continue
            for eid, n in self.nodes.items():
                if n.category == o.get("category") and eid not in explicit:
                    d = math.dist(n.pos, pos)
                    if d < TRACK_RADIUS:
                        pairs.append((d, i, eid))
        out: Dict[int, str] = {}
        used: Set[str] = set()
        for d, i, eid in sorted(pairs):
            if i not in out and eid not in used:
                out[i] = eid
                used.add(eid)
        return out

    def _expected(self, eid: str) -> Optional[Dict]:
        return self._last_prediction.get(eid)

    def _check_prior(self, eid: str, n: WMNode, pos: Vec3, stats: Dict) -> None:
        """生成先验注入理解：一致 → 置信 +0.05；不一致 → −0.1 并记 anomaly。"""
        exp = self._expected(eid)
        if exp is None:
            return
        dist = math.dist(exp["predicted"], pos)
        if dist < exp["bound"]:
            n.confidence = min(1.0, n.confidence + 0.05)
            stats["consistent"] += 1
            return
        n.confidence = max(0.1, n.confidence - 0.1)
        stats["anomalies"] += 1
        self._anomalies.append({"tick": self.tick, "entity": eid,
                                "expected": list(exp["predicted"]), "observed": list(pos),
                                "distance": round(dist, 4), "bound": exp["bound"],
                                "note": "预测-观测不一致（模型缺口/外部事件）"})

    def _ingest(self, o: Dict, tool: str, claimed: Set[str], stats: Dict) -> Tuple[str, Vec3]:
        p = finite_vec3(o["pos"], "observation pos")
        pos = (float(p[0]), float(p[1]), float(p[2]))
        eid = str(o.get("eid", "") or "") or self._track_identity({**o, "pos": pos}, claimed)
        claimed.add(eid)
        stats["observed"] += 1
        if eid in self.nodes:
            stats["matched"] += 1
            n = self.nodes[eid]
            self._check_prior(eid, n, pos, stats)
            n.pos, n.last_seen = pos, self.tick
        else:
            stats["new"] += 1
            self.nodes[eid] = WMNode(eid=eid, category=str(o["category"]), pos=pos,
                                     first_seen=self.tick, last_seen=self.tick)
        self._conditions[eid] = {"first_seen": self.nodes[eid].first_seen, "last_seen": self.tick,
                                 "observation_tool": tool,
                                 "time_window": [self.tick - 5, self.tick],
                                 "existence_constraint": "观测存在中"}
        return eid, pos

    def perceive(self, observations: Optional[List[Dict]] = None, tool: str = "observer") -> Dict:
        """观测 → 更新世界图；留存本轮真实观测快照（verify 唯一 actual 来源）。"""
        obs = observations if observations is not None else self._observe_world()
        self.tick += 1
        stats = {"observed": 0, "matched": 0, "new": 0, "consistent": 0, "anomalies": 0}
        claimed: Set[str] = set()
        snap: Dict[str, List[float]] = {}
        assigned = self._assign_identities(obs)
        for i, o in enumerate(obs):
            if i in assigned:
                o = {**o, "eid": assigned[i]}
            elif not str(o.get("eid", "") or ""):
                o = {**o, "eid": self._new_eid()}          # #226：未匹配即新节点，不再顺序抢占
            eid, pos = self._ingest(o, tool, claimed, stats)
            snap[eid] = list(pos)
        self._obs_snapshot, self._obs_tick = snap, self.tick
        self.history.append({"tick": self.tick,
                             "entities": {eid: list(n.pos) for eid, n in self.nodes.items()}})
        self._patterns = {}
        return {"status": "ok", "tick": self.tick, **stats, "anomaly_events": stats["anomalies"]}

    # ================= 模式推断 =================

    def _motion_stats(self, eid: str, window: int = 8) -> Tuple[float, float]:
        return motion_stats(self.history[-window:], eid)

    def _pair_tendency(self, a: str, b: str, window: int = 8) -> float:
        return pair_tendency(self.history[-window:], a, b)

    def _best_relation(self, a: str, eids: List[str], window: int) -> Tuple[Optional[str], float]:
        best_t, best_c = None, 0.0
        for b in eids:
            if b != a:
                c = self._pair_tendency(a, b, window)
                if abs(c) > abs(best_c):
                    best_t, best_c = b, c
        return best_t, best_c

    def _is_hypothesis(self, eid: str) -> bool:
        return eid in self.nodes and bool(self.nodes[eid].attrs.get("hypothesis"))

    def _put_inferred_edge(self, edge: WMEdge, pat: Dict) -> None:
        """推断边：同源旧推断边（非假设目标）退场并留痕，然后去重加入。"""
        stale = [e for e in self.edges if e.source == edge.source and e.evidence == "inferred"
                 and (e.relation, e.target) != (edge.relation, edge.target)
                 and not self._is_hypothesis(e.target)]
        if stale:
            pat.setdefault("superseded", []).extend(e.to_dict() for e in stale)
            ids = {id(e) for e in stale}
            self.edges = [e for e in self.edges if id(e) not in ids]
        if not any((e.source, e.relation, e.target) == (edge.source, edge.relation, edge.target)
                   for e in self.edges):
            self.edges.append(edge)
        pat["relations"].append(edge.to_dict())

    def _infer_behavior(self, eid: str, cons: float) -> str:
        if cons < self.entropy_threshold:
            return "wander"
        rel = next((e for e in self.edges if e.source == eid), None)
        return rel.relation if rel is not None and rel.relation in ("seek", "flee") else "follow"

    def infer_patterns(self, window: int = 8, force: bool = False) -> Dict:
        """观测-only 推断：方向一致性、速度、趋向/远离关系（取代旧推断边）、行为。"""
        if self._patterns and not force:
            return self._patterns
        pat: Dict = {"relations": [], "speed_estimates": {}, "entropy": {},
                     "behavior_inference": {}}
        eids = list(self.nodes)
        ser, disp, stats = window_series(self.history[-window:], eids)   # ≡ 逐对 _motion_stats/_best_relation
        for eid in eids:
            pat["entropy"][eid], pat["speed_estimates"][eid] = stats[eid]
        for a in eids:
            t, c = best_tendency(a, eids, ser, disp)
            if t is not None and abs(c) > 0.5:
                self._put_inferred_edge(WMEdge(source=a, relation="seek" if c > 0 else "flee",
                                               target=t, confidence=round(min(1.0, abs(c)), 3)),
                                        pat)
        for eid in eids:
            beh = self._infer_behavior(eid, pat["entropy"][eid])
            pat["behavior_inference"][eid] = self.nodes[eid].behavior_inferred = beh
        self._patterns = pat
        return pat

    def patterns(self) -> Dict:
        return self.infer_patterns()

    # ================= 生成端口 =================

    def _apply_move(self, pos: Vec3, speed: float, d: Vec3, max_step: Optional[float] = None) -> Vec3:
        """与物理世界同式：clamp 到 [0.5, size−0.5] + 两位小数。"""
        if tuple(d) == (0.0, 0.0, 0.0):
            return tuple(round(v, 2) for v in pos)
        if max_step is not None:      # seek 步长按剩余距离封顶，与物理世界同式（#249）
            speed = min(speed, max_step)
        nx = max(0.5, min(self.size - 0.5, pos[0] + d[0] * speed))
        nz = max(0.5, min(self.size - 0.5, pos[2] + d[2] * speed))
        return (round(nx, 2), pos[1], round(nz, 2))

    def _reach(self, speed: float) -> float:
        return max(self.hit_threshold, speed * 1.5 + self.pad)

    def _pat(self, key: str, eid: str, default: float) -> float:
        return self._patterns.get(key, {}).get(eid, default)

    def _relation_for(self, eid: str, shadow: Dict[str, Vec3]) -> Optional[WMEdge]:
        """可用关系：自身方向性明确，或 seek 一个随机目标（降级 chase_stochastic）。"""
        rel = next((e for e in self.edges if e.source == eid), None)
        if rel is None or rel.relation not in ("seek", "flee") or rel.target not in shadow:
            return None
        cons = self._pat("entropy", eid, 0.0)
        tgt_random = self._pat("entropy", rel.target, 0.0) < self.entropy_threshold
        ok = cons >= self.entropy_threshold or (rel.relation == "seek" and tgt_random)
        return rel if ok else None

    def _predict_rel(self, eid: str, rel: WMEdge, shadow: Dict[str, Vec3],
                     speed: float) -> Tuple[Vec3, float, str]:
        t, p = shadow[rel.target], shadow[eid]
        sign = -1.0 if rel.relation == "flee" else 1.0
        d = normalize_xz(sign * (t[0] - p[0]), 0.0, sign * (t[2] - p[2]))
        if rel.relation == "seek" and self._pat("entropy", rel.target, 0.0) < self.entropy_threshold:
            bound = max(self._reach(speed), self._reach(self._pat("speed_estimates", rel.target, 0.3)))
            return p, bound + self.hit_threshold, "chase_stochastic"
        cap = math.hypot(t[0] - p[0], t[2] - p[2]) if rel.relation == "seek" else None
        shadow[eid] = self._apply_move(p, speed, d, max_step=cap)
        if rel.relation == "seek":
            return shadow[eid], self.hit_threshold + 0.05, "exact"
        return shadow[eid], self.hit_threshold + speed * 0.3, "bounded_noisy"

    def _predict_one(self, eid: str, shadow: Dict[str, Vec3]) -> Tuple[Vec3, float, str]:
        speed = self._pat("speed_estimates", eid, 0.3)
        rel = self._relation_for(eid, shadow)
        if rel is not None:
            return self._predict_rel(eid, rel, shadow, speed)
        d = self._recent_move(eid) if self._pat("entropy", eid, 0.0) >= self.entropy_threshold else None
        if d is not None:
            shadow[eid] = self._apply_move(shadow[eid], speed, d)
            return shadow[eid], self.hit_threshold + speed * 0.4, "bounded_noisy"
        return shadow[eid], self._reach(speed), "bounded_stochastic"

    def generate(self, horizon: int = 1, use_patterns: bool = True) -> Dict:
        """世界图 → 候选未来：按 first_seen 序（≈ 世界插入序）顺序外推 + 不确定边界。"""
        if use_patterns:
            self.infer_patterns()
        shadow = {eid: tuple(n.pos) for eid, n in self.nodes.items()}
        pred: Dict[str, Dict] = {}
        for eid, n in sorted(self.nodes.items(), key=lambda kv: kv[1].first_seen):
            p, bound, mode = self._predict_one(eid, shadow)
            pred[eid] = {"category": n.category, "behavior": n.behavior_inferred, "mode": mode,
                         "predicted": list(p), "bound": round(bound, 3),
                         "confidence": round(n.confidence, 3)}
        self._last_prediction = pred
        return {"tick": self.tick, "horizon": horizon, "predictions": pred}

    def _recent_move(self, eid: str) -> Optional[Vec3]:
        """最近一次非零位移的单位方向。"""
        for dx, dz in reversed(_moves(self.history, eid)):
            dl = math.hypot(dx, dz)
            if dl > 1e-6:
                return (dx / dl, 0.0, dz / dl)
        return None

    # ================= 验证端口 =================

    def verify(self) -> Dict:
        """最近一次 generate vs 最近一次真实观测快照；未观测 → pending（不计分）。"""
        snap = self._obs_snapshot
        hits = total = pending = 0
        details = []
        for eid, p in self._last_prediction.items():
            actual = snap.get(eid) if snap is not None else None
            row = {"entity": eid, "mode": p["mode"], "predicted": p["predicted"],
                   "actual": actual, "bound": p["bound"]}
            if actual is None:
                pending += 1
                details.append({**row, "distance": None, "hit": None, "status": "pending"})
                continue
            dist = math.dist(p["predicted"], actual)
            hit = dist < p["bound"]
            hits, total = hits + hit, total + 1
            details.append({**row, "distance": round(dist, 4), "hit": hit, "status": "verified"})
        self._compare = {"tick": self.tick, "hits": hits, "total": total,
                         "hit_rate": round(hits / total, 4) if total else 1.0,
                         "pending": pending, "details": details}
        if snap is None:
            self._compare["no_observation"] = True
        return self._compare

    def verify_run(self, n: int = 10) -> Dict:
        """generate → 世界演化 → perceive → verify，重复 n 次。"""
        rates, v = [], self._compare
        for _ in range(max(0, int(n))):
            self.generate(horizon=1)
            self.world.step(n=1)
            self.perceive()
            v = self.verify()
            rates.append(v["hit_rate"])
        return {"status": "ok", "ticks": int(n), "tick": self.tick,
                "rolling_hit_rate": round(sum(rates) / len(rates), 4) if rates else 1.0,
                "last": v}

    # ================= 导出 =================

    def graph(self) -> Dict:
        return {"tick": self.tick,
                "nodes": {eid: {**n.to_dict(), "conditions": self._conditions.get(eid, {})}
                          for eid, n in self.nodes.items()},
                "edges": [e.to_dict() for e in self.edges], "node_count": len(self.nodes),
                "edge_count": len(self.edges), "history_len": len(self.history),
                "anomaly_count": len(self._anomalies)}

    def anomalies(self, limit: int = 20) -> List[Dict]:
        return self._anomalies[-max(1, int(limit)):]

    def history_view(self, limit: int = 10) -> List[Dict]:
        return self.history[-max(1, int(limit)):]

    def state(self) -> Dict:
        return {"status": "ok", "tick": self.tick, "size": self.size,
                "node_count": len(self.nodes), "edge_count": len(self.edges),
                "history_len": len(self.history), "anomaly_count": len(self._anomalies)}
