# -*- coding: utf-8 -*-
"""world_learner · 自监督世界学习（旧 ``lingshu.world.world_learner`` 的 ng 实现，同名 API）。

学习者只看观测（位置/类别），从观测序列估计白箱参数（每实体速度/方向持续性、趋向/远离
关系、追逐随机目标集合），用学得模型预测下一状态；评估时外部裁判对比学得 vs naive vs
真模型上界（:class:`spacetime.SpacetimeConsistency` 的影子重放，与世界同一公式）。

与旧版相比修正的缺陷类别：

- **seed 不透传**：旧构造器不把 seed 传给 SceneSimulator，「换 seed 重跑」只换了模型侧随机流；
  这里透传（缺省 42 与旧行为一致）。
- **真模型上界硬编码 size=24**：旧 ``_oracle_predict`` 新建 ``SpacetimeConsistency(size=24)``
  再把 scene 换掉；这里直接包住同一个世界（不另建一个 24 格场景）。
- ``_last_prediction`` 在构造时初始化（旧版首次 predict 前读取即 AttributeError）。
- 观测位置拒收 NaN/inf。
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from .scene_sim import SceneSimulator, normalize_xz
from .spacetime import SpacetimeConsistency
from .validate import finite_vec3
from .world_model import best_tendency, motion_stats, pair_tendency_n, window_series

__all__ = ["LNNode", "WorldLearner"]

Vec3 = Tuple[float, float, float]


@dataclass
class LNNode:
    """学习者的观测节点（仅由观测更新）。"""
    eid: str
    category: str
    pos: Vec3
    first_seen: int = 0
    last_seen: int = 0
    attrs: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


def _rate(h: int, denom: int) -> Optional[float]:
    return round(h / denom, 4) if denom else None


class WorldLearner:
    """自监督世界学习者：run（采集）→ learn（估参）→ predict → eval_phase/evaluate。"""

    def __init__(self, size: int = 24, ground_level: int = 1, seed: int = 42,
                 window: int = 6, world: Optional[SceneSimulator] = None):
        self.world = world or SceneSimulator(size=size, ground_level=ground_level, seed=seed)
        self.size = self.world.world.size
        self.seed = seed
        self.window = max(2, int(window))
        self.nodes: Dict[str, LNNode] = {}
        self.history: List[Dict] = []
        self.tick = 0
        self.model: Dict = {}
        self.losses: List[float] = []
        self.evals: List[Dict] = []
        self._last_prediction: Dict[str, Dict] = {}
        self._rng = random.Random(seed)
        self.pad = 0.2
        self.hit_threshold = 0.5
        self.entropy_threshold = 0.7

    # ================= 观测面 =================

    def _read(self, eids=None) -> Dict[str, Dict]:
        out = {}
        for eid, e in self.world.entities.items():
            if eids is None or eid in eids:
                p = finite_vec3(e.pos, "observed pos")
                out[eid] = {"category": e.category, "pos": (float(p[0]), float(p[1]), float(p[2]))}
        return out

    def _record(self, obs: Dict[str, Dict]) -> None:
        for eid, o in obs.items():
            n = self.nodes.get(eid)
            if n is None:
                n = self.nodes[eid] = LNNode(eid=eid, category=o["category"], pos=o["pos"],
                                             first_seen=self.tick)
            n.pos, n.last_seen = o["pos"], self.tick
        self.history.append({"tick": self.tick, "entities": obs})

    def observe(self) -> Dict:
        """观测物理世界全部实体（只读位置/类别）。"""
        self.tick += 1
        obs = self._read()
        self._record(obs)
        return {"status": "ok", "tick": self.tick, "observed": len(obs)}

    def run(self, n: int = 1) -> Dict:
        for _ in range(max(0, int(n))):
            self.world.step(n=1)
            self.observe()
        return {"status": "ok", "ticks": int(n), "tick": self.tick}

    # ================= 自监督特征 =================

    def _pos_view(self, window: Optional[int]) -> List[Dict]:
        w = window or self.window
        h = self.history
        key = (w, len(h), id(h[-1]) if h else None, id(h))
        if getattr(self, "_pv_key", None) == key:     # 同一次 learn/_select 内逐对复用
            return self._pv_val
        recs = h[-w:]
        val = [{"entities": {k: v["pos"] for k, v in r["entities"].items()}} for r in recs]
        self._pv_key, self._pv_val = key, val
        return val

    def _motion_stats(self, eid: str, window: Optional[int] = None) -> Tuple[float, float]:
        return motion_stats(self._pos_view(window), eid)

    def _pair_tendency(self, a: str, b: str, window: Optional[int] = None) -> Tuple[float, int]:
        return pair_tendency_n(self._pos_view(window), a, b)

    def _recent_dir(self, eid: str) -> Optional[Vec3]:
        prev, last = None, None
        for rec in self.history:
            cur = rec["entities"].get(eid)
            if cur is not None and prev is not None:
                dx, dz = cur["pos"][0] - prev[0], cur["pos"][2] - prev[2]
                if math.hypot(dx, dz) > 1e-6:
                    last = normalize_xz(dx, 0.0, dz)
            prev = cur["pos"] if cur is not None else None
        return last

    # ================= 学习 =================

    def _best_relation(self, a: str, eids: List[str], w: int) -> Tuple[Optional[str], float]:
        best_t, best_c = None, 0.0
        for b in eids:
            if b == a:
                continue
            c, n = self._pair_tendency(a, b, w)
            if n >= 3 and abs(c) > abs(best_c):          # 样本不足不采信
                best_t, best_c = b, c
        return best_t, best_c

    def learn(self, window: Optional[int] = None) -> Dict:
        """估参：per_entity{speed_est, persistence}、relations、stochastic_targets（D1）。

        与逐对调用 :meth:`_motion_stats` / :meth:`_pair_tendency` 的 :meth:`_learn_reference`
        逐位相同；先把窗口内序列与位移抽一次，免去逐对重建视图。"""
        eids = list(self.nodes)
        ser, disp, stats = window_series(self.history[-(window or self.window):], eids, "pos")
        model: Dict = {"per_entity": {e: {"speed_est": st[1], "persistence": st[0]}
                                      for e, st in stats.items()},
                       "relations": [], "stochastic_targets": []}
        for a in eids:
            self._add_relation(model, a, *best_tendency(a, eids, ser, disp, min_n=3))
        self.model = model
        return model

    def _add_relation(self, model: Dict, a: str, t: Optional[str], c: float) -> None:
        if t is None or abs(c) < 0.5:
            return
        rel = "seek" if c > 0 else "flee"
        model["relations"].append({"source": a, "relation": rel, "target": t,
                                   "confidence": round(abs(c), 3)})
        if rel == "seek" and model["per_entity"][t]["persistence"] < self.entropy_threshold:
            model["stochastic_targets"].append(a)

    def _learn_reference(self, window: Optional[int] = None) -> Dict:
        """逐对参考实现（测试对拍用；不改 self.model）。"""
        w = window or self.window
        eids = list(self.nodes)
        model: Dict = {"per_entity": {}, "relations": [], "stochastic_targets": []}
        for eid in eids:
            pers, speed = self._motion_stats(eid, w)
            model["per_entity"][eid] = {"speed_est": speed, "persistence": pers}
        for a in eids:
            self._add_relation(model, a, *self._best_relation(a, eids, w))
        return model

    # ================= 预测 =================

    def _reach(self, speed: float) -> float:
        return max(self.hit_threshold, speed * 1.5 + self.pad)

    def _apply_move(self, pos: Vec3, speed: float, d: Vec3, max_step: Optional[float] = None) -> Vec3:
        if tuple(d) == (0.0, 0.0, 0.0):
            return tuple(round(v, 2) for v in pos)
        if max_step is not None:      # seek 步长按剩余距离封顶，与物理世界同式（#249）
            speed = min(speed, max_step)
        nx = max(0.5, min(self.size - 0.5, pos[0] + d[0] * speed))
        nz = max(0.5, min(self.size - 0.5, pos[2] + d[2] * speed))
        return (round(nx, 2), pos[1], round(nz, 2))

    def _param(self, eid: str, key: str, default: float) -> float:
        return self.model.get("per_entity", {}).get(eid, {}).get(key, default)

    def _predict_rel(self, eid: str, rel: Dict, shadow: Dict[str, Vec3], speed: float,
                     stochastic: bool) -> Dict:
        t, p = shadow[rel["target"]], shadow[eid]
        sign = -1.0 if rel["relation"] == "flee" else 1.0
        d = normalize_xz(sign * (t[0] - p[0]), 0.0, sign * (t[2] - p[2]))
        if stochastic:
            bound = max(self._reach(speed), self._reach(self._param(rel["target"], "speed_est", 0.3)))
            return {"predicted": list(p), "bound": round(bound + self.hit_threshold, 3),
                    "mode": "chase_stochastic"}
        cap = math.hypot(t[0] - p[0], t[2] - p[2]) if rel["relation"] == "seek" else None
        shadow[eid] = self._apply_move(p, speed, d, max_step=cap)
        if rel["relation"] == "seek":
            return {"predicted": list(shadow[eid]), "bound": round(self.hit_threshold + 0.05, 3),
                    "mode": "exact"}
        return {"predicted": list(shadow[eid]), "bound": round(self.hit_threshold + speed * 0.3, 3),
                "mode": "bounded_noisy"}

    def _predict_one(self, eid: str, shadow: Dict[str, Vec3], rel: Optional[Dict],
                     stoch: set) -> Dict:
        speed = self._param(eid, "speed_est", 0.3)
        pers = self._param(eid, "persistence", 0.0)
        if rel is not None and rel["target"] in shadow and (pers >= self.entropy_threshold or eid in stoch):
            return self._predict_rel(eid, rel, shadow, speed, eid in stoch)
        dr = self._recent_dir(eid) if pers >= self.entropy_threshold else None
        if dr:
            shadow[eid] = self._apply_move(shadow[eid], speed, dr)
            return {"predicted": list(shadow[eid]),
                    "bound": round(self.hit_threshold + speed * 0.4, 3), "mode": "bounded_noisy"}
        return {"predicted": list(shadow[eid]), "bound": round(self._reach(speed), 3),
                "mode": "bounded_stochastic"}

    def predict(self, horizon: int = 1) -> Dict:
        """学得模型 → 下一状态（按 first_seen 序顺序外推 + 不确定边界）。"""
        if not self.model:
            self.learn()
        shadow = {eid: tuple(n.pos) for eid, n in self.nodes.items()}
        rel_by_src = {r["source"]: r for r in self.model.get("relations", [])}
        stoch = set(self.model.get("stochastic_targets", []))
        pred = {eid: self._predict_one(eid, shadow, rel_by_src.get(eid), stoch)
                for eid, _ in sorted(self.nodes.items(), key=lambda kv: kv[1].first_seen)}
        self._last_prediction = pred
        return {"tick": self.tick, "horizon": horizon, "predictions": pred}

    # ================= 自监督损失 =================

    def masked_loss(self, mask_last: int = 1) -> Dict:
        """遮住每实体最后一个观测，用前两点线性外推重建 → 均方距离。"""
        losses = []
        for eid in self.nodes:
            traj = [rec["entities"][eid]["pos"] for rec in self.history if eid in rec["entities"]]
            if len(traj) < 3:
                continue
            p1, p2, actual = traj[-3], traj[-2], traj[-1]
            rx, rz = p2[0] + (p2[0] - p1[0]), p2[2] + (p2[2] - p1[2])
            losses.append((rx - actual[0]) ** 2 + (rz - actual[2]) ** 2)
        mean_loss = round(sum(losses) / len(losses), 4) if losses else 0.0
        self.losses.append(mean_loss)
        return {"loss": mean_loss, "samples": len(losses), "curve_len": len(self.losses)}

    def next_state_loss(self, eval_ticks: int = 10) -> Dict:
        dists = []
        for _ in range(max(1, int(eval_ticks))):
            lp = self.predict(horizon=1)
            self.world.step(n=1)
            self.observe()
            dists += [math.dist(p["predicted"], self.nodes[eid].pos)
                      for eid, p in lp["predictions"].items() if eid in self.nodes]
        return {"mean_distance": round(sum(dists) / len(dists), 4) if dists else 0.0,
                "samples": len(dists)}

    # ================= 评估（外部裁判）=================

    def _oracle_predict(self) -> Dict:
        """真模型上界：对同一世界做与世界同一公式的影子重放（审计者有世界访问权）。"""
        try:
            return SpacetimeConsistency(scene=self.world)._predict_next()
        except Exception:
            return {}

    def _score_tick(self, acc: Dict) -> None:
        lp = self.predict(horizon=1)
        op = self._oracle_predict()
        before = {eid: tuple(e.pos) for eid, e in self.world.entities.items()}
        self.world.step(n=1)
        self.observe()
        actual = {eid: tuple(e.pos) for eid, e in self.world.entities.items()}
        for eid, p in lp["predictions"].items():
            if eid in actual:
                acc["total"] += 1
                acc["learned"] += math.dist(p["predicted"], actual[eid]) < p["bound"]
                acc["naive"] += math.dist(before.get(eid, actual[eid]), actual[eid]) < self.hit_threshold
        for eid, (pp, _m, _c, _b, bound) in op.items():
            if eid in actual:
                acc["oracle_total"] += 1
                acc["oracle"] += math.dist(pp, actual[eid]) < max(bound, 0.5)

    def eval_phase(self, eval_ticks: int = 15) -> Dict:
        """学得 vs naive vs 真模型上界；三者各用各自分母，oracle 不可用时 None。"""
        acc = dict.fromkeys(("learned", "naive", "oracle", "total", "oracle_total"), 0)
        for _ in range(max(1, int(eval_ticks))):
            self._score_tick(acc)
        learned = _rate(acc["learned"], acc["total"])
        learned = 1.0 if learned is None else learned
        oracle = _rate(acc["oracle"], acc["oracle_total"])
        naive = _rate(acc["naive"], acc["total"])
        res = {"tick": self.tick, "eval_ticks": int(eval_ticks), "outcomes": acc["total"],
               "learned_rate": learned, "naive_rate": 1.0 if naive is None else naive,
               "oracle_outcomes": acc["oracle_total"], "oracle_rate": oracle,
               "oracle_unavailable": acc["oracle_total"] == 0,
               "gap_to_oracle": round(max(0.0, oracle - learned), 4) if oracle is not None else None}
        self.evals.append(res)
        return res

    def evaluate(self, train_ticks: int = 30, eval_ticks: int = 15) -> Dict:
        self.run(n=train_ticks)
        self.learn()
        res = self.eval_phase(eval_ticks)
        res["train_ticks"] = int(train_ticks)
        return res

    def learning_curve(self, epochs: int = 5, per_epoch_ticks: int = 15,
                       eval_ticks: int = 12) -> Dict:
        curve = []
        for e in range(max(1, int(epochs))):
            self.run(n=per_epoch_ticks)
            self.learn()
            res = self.eval_phase(eval_ticks)
            loss = self.next_state_loss(eval_ticks)
            curve.append({"epoch": e + 1, "observations": self.tick,
                          "learned_rate": res["learned_rate"], "naive_rate": res["naive_rate"],
                          "oracle_rate": res["oracle_rate"], "mean_distance": loss["mean_distance"]})
        return {"curve": curve,
                "improvement": round(curve[-1]["learned_rate"] - curve[0]["learned_rate"], 4),
                "distance_drop": round(curve[0]["mean_distance"] - curve[-1]["mean_distance"], 4)}

    # ================= 导出 =================

    def model_params(self) -> Dict:
        return self.model

    def history_view(self, limit: int = 10) -> List[Dict]:
        return self.history[-max(1, int(limit)):]

    def state(self) -> Dict:
        return {"status": "ok", "tick": self.tick, "size": self.size,
                "entities": len(self.nodes), "observations": len(self.history),
                "losses": len(self.losses), "evals": len(self.evals)}
