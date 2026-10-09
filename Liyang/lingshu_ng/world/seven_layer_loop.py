# -*- coding: utf-8 -*-
"""seven_layer_loop · 七层闭环（旧 ``lingshu.world.seven_layer_loop`` 的 ng 实现，同名 API）。

每 tick：L7 决策（好奇选观测）→ L4 预测 → L6 物理演化 → L1 感知（选中子集）→
L5 验证（外部观察者全实体）→ L2 记忆 / L3 认知（重新学习），并留七层审计。

与旧版相比修正的缺陷类别：

- **seed 不透传**：旧构造器把 seed 只给了 CuriosityExplorer，物理世界恒为 42；这里透传
  给 SceneSimulator（缺省 42 与旧行为一致），探索器共享同一世界。
- L5 验证拒绝非有限的预测/实际位置（旧版 nan 距离 → ``nan < bound`` 恒假，被静默记为未命中）。
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .curiosity import CuriosityExplorer
from .scene_sim import SceneSimulator
from .validate import finite_xyz

__all__ = ["SevenLayerLoop"]

Vec3 = Tuple[float, float, float]


def _mean(xs: List[float]) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 1.0


class SevenLayerLoop:
    """七层闭环：感知→记忆→理解→预测→验证→物理→决策。"""

    LAYERS = ("L1_perception", "L2_memory", "L3_cognition", "L4_prediction",
              "L5_verification", "L6_physics", "L7_decision")

    def __init__(self, size: int = 24, ground_level: int = 1, seed: int = 42,
                 window: int = 6, budget: int = 2, policy: str = "curiosity",
                 world: Optional[SceneSimulator] = None):
        self.world = world or SceneSimulator(size=size, ground_level=ground_level, seed=seed)
        self.explorer = CuriosityExplorer(size=size, ground_level=ground_level, seed=seed,
                                          window=window, world=self.world)
        self.budget = max(1, int(budget))
        if policy not in CuriosityExplorer.POLICIES:     # #233：构造期即拒未知策略（此前静默退化为轮询）
            raise ValueError(f"未知 L7 策略 {policy!r}（允许 {CuriosityExplorer.POLICIES}）")
        self.policy = policy
        self.audit: List[Dict] = []
        self.hit_history: List[float] = []
        self.tick = 0

    # ---- 场景构建 ----

    def create_scene(self, trees: int = 2, water: bool = False) -> Dict:
        return self.world.create_scene(trees=trees, water=water)

    def add_entity(self, category: str, behavior: str = "wander", pos: Vec3 = (2, 1.5, 2),
                   speed: float = 0.3, goal: str = "") -> str:
        return self.world.add_entity(category=category, behavior=behavior, pos=pos,
                                     speed=speed, goal=goal)

    def add_path(self, path_id: str, points: List[Vec3]) -> None:
        self.world.add_path(path_id, points)

    # ---- 七层一步 ----

    def _verify(self, predictions: Dict) -> Dict:
        """L5：外部观察者（有世界访问权）全实体对比。"""
        hits, details = 0, []
        for eid, p in predictions.items():
            e = self.world.entities.get(eid)
            if e is None:
                continue
            dist = math.dist(finite_xyz(p["predicted"], "predicted"), finite_xyz(e.pos, "actual"))
            hit = dist < p["bound"]
            hits += hit
            details.append({"entity": eid, "mode": p["mode"], "hit": hit,
                            "distance": round(dist, 4)})
        total = len(details)
        return {"hits": hits, "total": total,
                "hit_rate": round(hits / total, 4) if total else 1.0, "details": details}

    def step(self) -> Dict:
        ex = self.explorer
        chosen, scores = ex._select(self.budget, self.policy)
        rec: Dict = {"L7_decision": {"chosen": list(chosen), "ig_scores": scores,
                                     "policy": self.policy, "budget": self.budget}}
        if not ex.model:
            ex.learn()
        pred = ex.predict(horizon=1)
        rec["L4_prediction"] = {"predictions": pred["predictions"]}
        self.world.step(n=1)
        rec["L6_physics"] = {"world_tick": self.world.tick_count,
                             "entities": len(self.world.entities)}
        ex.observe(entities=chosen)
        rec["L1_perception"] = {"observed": list(chosen), "observed_count": len(chosen)}
        ver = self._verify(pred["predictions"])
        rec["L5_verification"] = {"hit_rate": ver["hit_rate"], "hits": ver["hits"],
                                  "total": ver["total"]}
        self.hit_history.append(ver["hit_rate"])
        rec["L2_memory"] = {"history_len": len(ex.history),
                            "entities": {eid: list(n.pos) for eid, n in ex.nodes.items()}}
        ex.learn()
        rec["L3_cognition"] = {"relations": list(ex.model.get("relations", [])),
                               "entity_count": len(ex.nodes)}
        self.tick += 1
        rec["tick"] = self.tick
        self.audit.append(rec)
        return rec

    def run(self, n: int = 30) -> Dict:
        """持续运行；尚无观测时先全带宽感知 1 + window tick 作认知种子。"""
        if not self.explorer.history:
            self.explorer.observe()
            self.explorer.run(n=self.explorer.window)
        steps = max(0, int(n))                            # #233：n ≤ 0 不推进；ticks 报实际推进数
        for _ in range(steps):
            self.step()
        return {"status": "ok", "ticks": steps, "loop_tick": self.tick,
                "overall_hit_rate": self._overall_hit_rate()}

    def _overall_hit_rate(self) -> float:
        return _mean(self.hit_history)

    # ---- 报告与审计 ----

    def _enhancement(self) -> Dict:
        h = self.hit_history
        early, late = h[:max(1, len(h) // 2)], h[len(h) // 2:]
        imp = round(sum(late) / len(late) - sum(early) / len(early), 4) if early and late else 0.0
        return {"early_hit_rate": _mean(early), "late_hit_rate": _mean(late), "improvement": imp}

    def report(self) -> Dict:
        ex = self.explorer
        obs = dict(ex.obs_counts)
        return {"component": "seven_layer_loop", "loop_tick": self.tick,
                "L1_perception": {"observations": len(ex.history), "obs_distribution": obs},
                "L2_memory": {"history_len": len(ex.history), "entities": len(ex.nodes)},
                "L3_cognition": {"relations": len(ex.model.get("relations", [])),
                                 "entity_count": len(ex.nodes)},
                "L4_prediction": {"entity_count": len(ex._last_prediction)},
                "L5_verification": {"overall_hit_rate": self._overall_hit_rate(),
                                    "recent": self.hit_history[-10:]},
                "L6_physics": {"world_tick": self.world.tick_count,
                               "entities": len(self.world.entities)},
                "L7_decision": {"policy": self.policy, "budget": self.budget,
                                "obs_distribution": dict(obs)},
                "closed_loop_enhancement": self._enhancement(), "loop_closed": True}

    def audit_view(self, limit: int = 10) -> List[Dict]:
        return self.audit[-max(1, int(limit)):]

    def verify_state(self) -> Dict:
        return {"hit_rate": self._overall_hit_rate(), "hit_history": self.hit_history[-20:]}

    def decision_state(self) -> Dict:
        return {"policy": self.policy, "budget": self.budget,
                "obs_distribution": dict(self.explorer.obs_counts),
                "latest": self.audit[-1]["L7_decision"] if self.audit else {}}

    def memory_state(self) -> Dict:
        ex = self.explorer
        return {"history_len": len(ex.history),
                "entities": {eid: list(n.pos) for eid, n in ex.nodes.items()},
                "history_view": ex.history[-5:]}

    def graph_state(self) -> Dict:
        ex = self.explorer
        return {"relations": ex.model.get("relations", []),
                "entities": {eid: {"category": n.category, "pos": list(n.pos)}
                             for eid, n in ex.nodes.items()}}

    def state(self) -> Dict:
        return {"status": "ok", "loop_tick": self.tick, "audit_len": len(self.audit),
                "overall_hit_rate": self._overall_hit_rate(), "world_tick": self.world.tick_count,
                "entities": len(self.world.entities), "policy": self.policy,
                "budget": self.budget}
