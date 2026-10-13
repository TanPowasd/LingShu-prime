# -*- coding: utf-8 -*-
"""curiosity · 好奇驱动探索（旧 ``lingshu.world.curiosity_explorer`` 的 ng 实现，同名 API）。

有限带宽传感器：每 tick 只观测 budget 个实体，按信息增益（预测不确定 × 信息瓶颈² ×
新奇度 × 陈旧度 × 异常加成）挑选；对照策略 random / round_robin。

与旧版相比修正的缺陷类别：

- **对照世界不继承配置**：旧 ``compare_policies`` 用 ``CuriosityExplorer(size=24)`` 重建世界，
  丢掉调用方的 seed / size / window（换 seed 对比实验无效）；这里三策略的世界都用本实例的
  seed / size / window 构建（同 seed → 世界随机流一致，公平对比的前提不变）。
- 子集观测拒收非有限位置（继承 :class:`WorldLearner` 观测面）。
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .world_learner import WorldLearner

__all__ = ["CuriosityExplorer"]


class CuriosityExplorer(WorldLearner):
    """好奇驱动探索器：WorldLearner + 有限带宽主动观测。"""

    def __init__(self, size: int = 24, ground_level: int = 1, seed: int = 42,
                 window: int = 6, world=None):
        super().__init__(size=size, ground_level=ground_level, seed=seed, window=window,
                         world=world)
        self.last_observed: Dict[str, int] = {}
        self.obs_counts: Dict[str, int] = {}
        self._anomaly_counts: Dict[str, int] = {}
        self.exploration_log: List[Dict] = []
        self.uncertainty_curve: List[float] = []
        self._rr_index = 0
        self._patterns: Dict = {}

    # ================= 有限带宽传感器 =================

    def _sensor_read(self, eids) -> Dict:
        return self._read(set(eids))

    def observe(self, entities: Optional[List[str]] = None) -> Dict:
        """观测实体子集；entities=None 观测全部（基类口径）。"""
        if entities is None:
            return super().observe()
        self.tick += 1
        obs = self._sensor_read(entities)
        self._record(obs)
        for eid in obs:
            self.last_observed[eid] = self.tick
            self.obs_counts[eid] = self.obs_counts.get(eid, 0) + 1
        self._patterns = {}
        return {"status": "ok", "tick": self.tick, "observed": len(obs)}

    # ================= 信息增益 =================

    def _is_stationary(self, eid: str) -> bool:
        recent = []
        for rec in reversed(self.history):          # 只要最近两次观测：倒序扫到即停
            ent = rec["entities"].get(eid)
            if ent is not None:
                recent.append(ent["pos"])
                if len(recent) == 2:
                    return math.dist(recent[0], recent[1]) < 1e-6
        return False

    def _base_bound(self, eid: str) -> float:
        speed = self._param(eid, "speed_est", 0.3)
        rel = next((r for r in self.model.get("relations", []) if r["source"] == eid), None)
        if rel is None:
            if self._param(eid, "persistence", 0.0) >= self.entropy_threshold:
                return self.hit_threshold + speed * 0.4
            return self._reach(speed)
        if rel["relation"] != "seek":
            return self.hit_threshold + speed * 0.3
        if self._param(rel["target"], "persistence", 0.0) < self.entropy_threshold:
            t_speed = self._param(rel["target"], "speed_est", 0.3)
            return max(self._reach(speed), self._reach(t_speed)) + self.hit_threshold
        return self.hit_threshold + 0.05

    def _prediction_bound(self, eid: str) -> float:
        """预测不确定度；静止 → 阈值；k tick 未观测 → ×(1 + k/max(2,window))。"""
        if not self.model:
            self.learn()
        if self._is_stationary(eid):
            return self.hit_threshold
        last = self.last_observed.get(eid, 0)
        k = max(0, self.tick - last) if last else 0
        return round(self._base_bound(eid) * (1.0 + k / float(max(2, self.window))), 4)

    def _info_gain(self, eid: str) -> float:
        if not self.model:
            self.learn()
        bound = self._prediction_bound(eid)
        bottleneck = 1.0 + sum(1 for r in self.model.get("relations", []) if r["target"] == eid)
        novelty = 1.0 / (1.0 + self.obs_counts.get(eid, 0))
        last = self.last_observed.get(eid, 0)
        staleness = min(1.5, max(0.5, (self.tick - last) / float(self.window))) if last else 1.0
        anom = self._anomaly_counts.get(eid, 0) / float(max(1, self.obs_counts.get(eid, 0)))
        return round(bound * bottleneck ** 2 * (0.2 + novelty) * staleness * (1.0 + anom), 4)

    POLICIES = ("curiosity", "random", "round_robin")

    def _select(self, budget: int, policy: str) -> Tuple[List[str], Dict]:
        if policy not in self.POLICIES:                   # #233：拼错的策略名显式报错
            raise ValueError(f"未知探索策略 {policy!r}（允许 {self.POLICIES}）")
        eids = list(self.world.entities)
        n = len(eids)
        b = max(1, min(int(budget), n))
        if policy == "curiosity":
            scores = {e: self._info_gain(e) for e in eids}
            return sorted(eids, key=lambda e: scores[e], reverse=True)[:b], scores
        if policy == "random":
            chosen = self._rng.sample(eids, b)
            return chosen, {e: 0.0 for e in chosen}
        chosen = [eids[(self._rr_index + i) % n] for i in range(b)]
        self._rr_index = (self._rr_index + b) % n
        return chosen, {}

    # ================= 探索循环 =================

    def _count_anomalies(self, chosen: List[str]) -> int:
        n_anom = 0
        for eid in chosen:
            exp, n = self._last_prediction.get(eid), self.nodes.get(eid)
            if exp is not None and n is not None and math.dist(exp["predicted"], n.pos) >= exp["bound"]:
                self._anomaly_counts[eid] = self._anomaly_counts.get(eid, 0) + 1
                n_anom += 1
        return n_anom

    def explore_tick(self, budget: int = 2, policy: str = "curiosity") -> Dict:
        """选择 → （有模型则预测）→ 观测 → 异常计数 → 学习 → 世界演化。"""
        chosen, scores = self._select(budget, policy)
        if self.model:
            self.predict(horizon=1)
        self.observe(entities=chosen)
        self._count_anomalies(chosen)
        self.learn()
        mean_bound = self.uncertainty()
        entry = {"tick": self.tick, "policy": policy, "chosen": list(chosen),
                 "ig_scores": scores, "mean_bound": mean_bound}
        self.exploration_log.append(entry)
        self.uncertainty_curve.append(mean_bound)
        self.world.step(n=1)
        return entry

    def explore(self, ticks: int = 40, budget: int = 2, policy: str = "curiosity") -> Dict:
        for _ in range(max(1, int(ticks))):
            self.explore_tick(budget=budget, policy=policy)
        return {"status": "ok", "ticks": int(ticks), "tick": self.tick, "policy": policy,
                "budget": int(budget), "final_uncertainty": self.uncertainty_curve[-1],
                "obs_distribution": dict(self.obs_counts)}

    # ================= 不确定度与评估 =================

    def uncertainty(self) -> float:
        bounds = [self._prediction_bound(eid) for eid in self.nodes]
        return round(sum(bounds) / len(bounds), 4) if bounds else 1.0

    def probe(self, ticks: int = 15) -> Dict:
        """全带宽探针：学得模型 held-out 命中率 vs naive。"""
        learned = naive = total = 0
        for _ in range(max(1, int(ticks))):
            lp = self.predict(horizon=1)
            before = {eid: tuple(n.pos) for eid, n in self.nodes.items()}
            self.world.step(n=1)
            self.observe()
            for eid, p in lp["predictions"].items():
                if eid in self.nodes:
                    a = tuple(self.nodes[eid].pos)
                    total += 1
                    learned += math.dist(p["predicted"], a) < p["bound"]
                    naive += math.dist(before.get(eid, a), a) < self.hit_threshold
        return {"tick": self.tick, "probe_ticks": int(ticks), "outcomes": total,
                "learned_rate": round(learned / total, 4) if total else 1.0,
                "naive_rate": round(naive / total, 4) if total else 1.0}

    @staticmethod
    def _build_world(size: int = 24, seed: int = 42, window: int = 6) -> "CuriosityExplorer":
        """标准世界：追逐链 player(wander) ← wolf(seek) ← rabbit(flee)。"""
        ex = CuriosityExplorer(size=size, seed=seed, window=window)
        ex.world.create_scene(trees=2, water=False)
        p = ex.world.add_entity("player", behavior="wander", pos=(2, 1.5, 2), speed=0.5)
        w = ex.world.add_entity("wolf", behavior="seek", pos=(15, 1.5, 15), speed=0.6, goal=p)
        ex.world.add_entity("rabbit", behavior="flee", pos=(10, 1.5, 10), speed=0.5, goal=w)
        return ex

    def compare_policies(self, budget: int = 2, explore_ticks: int = 40,
                         probe_ticks: int = 15) -> Dict:
        """三策略各自在同配置（本实例 seed/size/window）的新世界上探索 + 探针。"""
        results = {}
        for pol in ("curiosity", "random", "round_robin"):
            ex = self._build_world(self.size, self.seed, self.window)
            ex.observe()
            ex.run(n=self.window)
            for _ in range(max(1, int(explore_ticks))):
                ex.explore_tick(budget=budget, policy=pol)
            pr = ex.probe(ticks=probe_ticks)
            results[pol] = {"probe_rate": pr["learned_rate"], "naive_rate": pr["naive_rate"],
                            "final_uncertainty": ex.uncertainty_curve[-1],
                            "uncertainty_min": min(ex.uncertainty_curve),
                            "obs_distribution": dict(ex.obs_counts),
                            "curve": list(ex.uncertainty_curve)}
        return {"budget": int(budget), "explore_ticks": int(explore_ticks), "results": results}

    # ================= 导出 =================

    def exploration_log_view(self, limit: int = 20) -> List[Dict]:
        return self.exploration_log[-max(1, int(limit)):]

    def curiosity_summary(self) -> Dict:
        c = self.uncertainty_curve
        return {"observations": dict(self.obs_counts), "total": sum(self.obs_counts.values()),
                "uncertainty": c[-1] if c else None,
                "uncertainty_trend": (round(c[0], 4), round(c[-1], 4)) if len(c) >= 2 else None,
                "anomaly_counts": dict(self._anomaly_counts)}

    def state(self) -> Dict:
        st = super().state()
        st["exploration_steps"] = len(self.exploration_log)
        st["budget_observations"] = dict(self.obs_counts)
        return st
