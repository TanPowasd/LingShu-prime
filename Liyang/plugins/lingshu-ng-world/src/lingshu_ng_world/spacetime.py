# -*- coding: utf-8 -*-
"""spacetime · 时空一致性验证（旧 ``lingshu.world.spacetime_consistency`` 的 ng 实现，同名 API）。

持续运行：每 tick 先预测下一状态，再让世界 step，逐实体判命中；滚动命中率、漂移事件、
世界状态不变量、自洽判定与旧版口径一致。

与旧版相比修正的缺陷类别：

- **影子与世界是两份手抄公式**：旧 ``_shadow_decide`` 抄了一遍 ``SceneSimulator._decide``，
  世界侧改成「seek 按剩余距离截断、follow 到达半径 0.0075」后影子没跟上，follow 巡逻
  150 tick 的逐位距离最大 0.46（test_scene_follow_patrol F 组）。这里影子只调用
  :func:`scene_sim.deterministic_dir` / :func:`scene_sim.apply_move`——与世界同一函数，
  不存在第二份公式可分叉。
- **seed 不透传**：旧构造器不接受 seed，物理世界随机流恒为 42；这里 ``seed`` 透传给
  SceneSimulator（缺省 42 与旧行为一致）。
- 外部瞬移坐标拒收 NaN/inf（旧版会把非有限位置排进事件队列）。
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .scene_sim import SceneSimulator, apply_move, deterministic_dir
from .validate import finite_vec3

__all__ = ["SpacetimeConsistency"]

Vec3 = Tuple[float, float, float]


def _round3(p) -> Vec3:
    return (round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2))


class SpacetimeConsistency:
    """时空一致性验证器：封装 SceneSimulator，持续运行 + 一致性验证。"""

    def __init__(self, size: int = 24, ground_level: int = 1, window: int = 20,
                 hit_threshold: float = 0.5, drift_rate: float = 0.7, drift_ticks: int = 5,
                 consistent_rate: float = 0.85, min_consistent_ticks: int = 50,
                 wander_bound_factor: float = 1.5, wander_bound_pad: float = 0.2,
                 seed: int = 42, scene: Optional[SceneSimulator] = None):
        self.scene = scene if scene is not None else SceneSimulator(
            size=size, ground_level=ground_level, seed=seed)
        self.window = max(1, int(window))
        self.hit_threshold = float(hit_threshold)
        self.drift_rate = float(drift_rate)
        self.drift_ticks = max(1, int(drift_ticks))
        self.consistent_rate = float(consistent_rate)
        self.min_consistent_ticks = max(1, int(min_consistent_ticks))
        self.wander_bound_factor = float(wander_bound_factor)
        self.wander_bound_pad = float(wander_bound_pad)
        self._results: List[Dict] = []
        self._rolling: List[float] = []
        self._drift_events: List[Dict] = []
        self._active_drift: Optional[Dict] = None
        self._low_streak = 0
        self._invariant_violations = 0
        self._pending_events: List[Tuple[str, Vec3]] = []
        self.tick_count = 0

    # ---- 场景构建（透传）----

    def create_scene(self, trees: int = 4, water: bool = True) -> Dict:
        return self.scene.create_scene(trees=trees, water=water)

    def add_entity(self, category: str, behavior: str = "wander", pos: Vec3 = (2, 1.5, 2),
                   speed: float = 0.3, goal: str = "") -> str:
        return self.scene.add_entity(category=category, behavior=behavior, pos=pos,
                                     speed=speed, goal=goal)

    def add_path(self, path_id: str, points: List[Vec3]) -> None:
        self.scene.add_path(path_id, points)

    def scene_state(self) -> Dict:
        return self.scene.scene_state()

    def behavior_log(self, limit: int = 30) -> List[Dict]:
        return self.scene.behavior_log(limit=limit)

    def evolution(self) -> List[Dict]:
        return self.scene.evolution()

    # ---- 预测模型 ----

    def _is_deterministic(self, e) -> bool:
        """不消耗 RNG 的确定性分支（与 deterministic_dir 的分支条件一致）。"""
        if e.behavior in ("seek", "avoid"):
            return e.goal in self.scene.entities
        return e.behavior == "follow" and bool(self.scene.paths.get(e.goal))

    def _apply_move_at(self, pos: Vec3, speed: float, d: Vec3) -> Vec3:
        """与世界同一位移函数；零方向时返回两位小数的原位置（观测口径）。"""
        if tuple(d) == (0.0, 0.0, 0.0):
            return _round3(pos)
        return apply_move(pos, d, speed, self.scene.world.size)

    def _shadow_decide(self, e, shadow: Dict[str, Vec3],
                       follow_target: Optional[Dict[str, int]] = None) -> Vec3:
        """影子决策 = 世界同一公式 :func:`deterministic_dir`（读影子位置，不碰 RNG）。"""
        fi = follow_target if follow_target is not None else {}
        d = deterministic_dir(e, shadow.get(e.id, e.pos), shadow, self.scene.paths, fi)
        return d if d is not None else (0.0, 0.0, 0.0)

    def _predict_next(self) -> Dict[str, Tuple[Vec3, str, str, str, float]]:
        """按插入序重放（后决策者看到前序已移动位置）→ {eid: (位置, mode, 类别, 行为, bound)}。"""
        shadow = {eid: tuple(e.pos) for eid, e in self.scene.entities.items()}
        follow_target = dict(self.scene._follow_target)
        pred: Dict[str, Tuple[Vec3, str, str, str, float]] = {}
        for eid, e in self.scene.entities.items():
            exact, bound = self._exactness(e, pred)
            if exact:
                p = self._apply_move_at(shadow[eid], e.speed,
                                        self._shadow_decide(e, shadow, follow_target))
                shadow[eid] = p
                pred[eid] = (p, "exact", e.category, e.behavior, 0.0)
            else:
                pred[eid] = (shadow[eid], "bounded", e.category, e.behavior, bound)
        return pred

    def _exactness(self, e, pred: Dict) -> Tuple[bool, float]:
        """确定性且目标不是「已判 bounded 的前序实体」→ exact；否则 bounded + 传播后的命中域。"""
        if not self._is_deterministic(e):
            return False, self._reach_bound(e)
        if e.behavior in ("seek", "avoid"):
            g = self.scene.entities.get(e.goal)
            if g is not None and g.id in pred and pred[g.id][1] == "bounded":
                return False, max(self._reach_bound(e), self._reach_bound(g)) + self.hit_threshold
        return True, 0.0

    def _reach_bound(self, e) -> float:
        return max(self.hit_threshold, e.speed * self.wander_bound_factor + self.wander_bound_pad)

    # ---- 不变量 ----

    def _check_invariants(self) -> Tuple[bool, List[str]]:
        """实体在界内 · 不下穿地面 · 位置有限。"""
        issues = []
        size = self.scene.world.size
        gnd = float(self.scene.world.ground_level)
        for eid, e in self.scene.entities.items():
            x, y, z = e.pos
            if not (0.5 <= x <= size - 0.5 and 0.5 <= z <= size - 0.5):
                issues.append("out_of_bounds:" + eid)
            if y < gnd + 0.4:
                issues.append("below_ground:" + eid)
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                issues.append("non_finite:" + eid)
        return not issues, issues

    # ---- 闭环 ----

    def _outcome(self, eid: str, pp: Vec3, mode: str, category: str, behavior: str,
                 bound: float) -> Dict:
        e = self.scene.entities.get(eid)
        if e is None:
            return {"entity": eid, "category": category, "behavior": behavior, "mode": mode,
                    "predicted": list(pp), "actual": None, "distance": None, "hit": False,
                    "missing": True}
        ap = _round3(e.pos)
        dist = math.dist(pp, ap)
        lim = self.hit_threshold if mode == "exact" else (bound if bound > 0 else self._reach_bound(e))
        return {"entity": eid, "category": e.category, "behavior": e.behavior, "mode": mode,
                "predicted": list(pp), "actual": list(ap), "distance": round(dist, 4),
                "hit": dist < lim, "missing": False}

    def step_verified(self) -> Dict:
        """预测 → 外部事件（模型未知）→ 世界 step → 逐实体命中 → 统计/不变量/漂移。"""
        pred = self._predict_next()
        for eid, pos in self._pending_events:
            if eid in self.scene.entities:
                self.scene.entities[eid].pos = pos
        self._pending_events.clear()
        self.scene.step(n=1)
        self.tick_count = self.scene.tick_count
        outcomes = [self._outcome(eid, *v) for eid, v in pred.items()]
        hits = sum(1 for o in outcomes if o["hit"])
        rate = round(hits / len(outcomes), 4) if outcomes else 1.0
        self._rolling = (self._rolling + [rate])[-self.window:]
        rolling = self._rolling_rate()
        inv_ok, inv_issues = self._check_invariants()
        self._invariant_violations += 0 if inv_ok else 1
        self._update_drift(rolling)
        rec = {"tick": self.tick_count, "hits": hits, "total": len(outcomes), "rate": rate,
               "rolling": round(rolling, 4), "outcomes": outcomes, "invariants_ok": inv_ok,
               "invariant_issues": inv_issues, "drift_active": self._active_drift is not None}
        self._results.append(rec)
        return rec

    def _rolling_rate(self) -> float:
        return round(sum(self._rolling) / len(self._rolling), 4) if self._rolling else 1.0

    def _update_drift(self, rolling: float) -> None:
        if rolling >= self.drift_rate:
            if self._active_drift is not None:
                self._active_drift["end_tick"] = self.tick_count - 1
                self._drift_events.append(self._active_drift)
                self._active_drift = None
            self._low_streak = 0
            return
        self._low_streak += 1
        if self._low_streak < self.drift_ticks:
            return
        if self._active_drift is None:
            self._active_drift = {"start_tick": self.tick_count, "min_rate": rolling,
                                  "ticks": self._low_streak}
        else:
            self._active_drift["ticks"] = self._low_streak
            self._active_drift["min_rate"] = min(self._active_drift["min_rate"], rolling)

    def run(self, n: int = 1) -> Dict:
        for _ in range(max(0, int(n))):
            self.step_verified()
        return {"status": "ok", "ticks": int(n), "tick": self.tick_count,
                "rolling_hit_rate": self._rolling_rate(),
                "drift_active": self._active_drift is not None}

    def teleport(self, entity_id: str, pos: Vec3) -> bool:
        """排队一次模型无法解释的瞬移（下个验证 tick 预测之后生效）；坐标须有限。"""
        if entity_id not in self.scene.entities:
            return False
        p = finite_vec3(pos, "pos")
        self._pending_events.append((entity_id, (float(p[0]), float(p[1]), float(p[2]))))
        return True

    # ---- 统计与报告 ----

    def rolling_hit_rate(self, window: Optional[int] = None) -> float:
        if window is not None and 0 < window < len(self._rolling):
            recent = self._rolling[-int(window):]
            return round(sum(recent) / len(recent), 4)
        return self._rolling_rate()

    def overall_hit_rate(self) -> float:
        totals = sum(x["total"] for x in self._results)
        return round(sum(x["hits"] for x in self._results) / totals, 4) if totals else 1.0

    def per_behavior_rates(self) -> Dict:
        stats: Dict[str, Dict] = {}
        det, sto = {"outcomes": 0, "hits": 0}, {"outcomes": 0, "hits": 0}
        for rec in self._results:
            for o in rec["outcomes"]:
                for s in (stats.setdefault(o["behavior"], {"outcomes": 0, "hits": 0}),
                          det if o["mode"] == "exact" else sto):
                    s["outcomes"] += 1
                    s["hits"] += 1 if o["hit"] else 0
        for s in list(stats.values()) + [det, sto]:
            s["rate"] = round(s["hits"] / s["outcomes"], 4) if s["outcomes"] else 1.0
        return {"per_behavior": stats, "deterministic": det, "stochastic": sto}

    def drift_events(self) -> List[Dict]:
        return list(self._drift_events)

    def drift_active(self) -> bool:
        return self._active_drift is not None

    def prediction_history(self, limit: int = 10) -> List[Dict]:
        return self._results[-max(1, int(limit)):]

    def _verdict(self, overall: float, recent_inv: int) -> str:
        if self._active_drift is not None:
            return "drift_detected"
        if recent_inv > 0:
            return "invariant_violated"
        if overall < self.consistent_rate:
            return "inconsistent"
        return "self_consistent" if self.tick_count >= self.min_consistent_ticks else "running"

    def consistency_report(self) -> Dict:
        overall = self.overall_hit_rate()
        recent_inv = sum(1 for r in self._results[-self.window:] if not r["invariants_ok"])
        verdict = self._verdict(overall, recent_inv)
        pbr = self.per_behavior_rates()
        return {"component": "spacetime_consistency", "tick": self.tick_count,
                "sustained": self.tick_count >= self.min_consistent_ticks,
                "min_consistent_ticks": self.min_consistent_ticks, "window": self.window,
                "overall_hit_rate": overall, "rolling_hit_rate": self._rolling_rate(),
                "consistent_rate": self.consistent_rate, "per_behavior": pbr["per_behavior"],
                "deterministic_rate": pbr["deterministic"]["rate"],
                "stochastic_rate": pbr["stochastic"]["rate"],
                "drift_events": list(self._drift_events),
                "drift_active": self._active_drift is not None, "drift_rate": self.drift_rate,
                "invariant_violations": self._invariant_violations,
                "recent_invariant_violations": recent_inv, "verdict": verdict,
                "self_consistent": verdict == "self_consistent"}

    def self_consistent(self) -> bool:
        return self.consistency_report()["self_consistent"]
