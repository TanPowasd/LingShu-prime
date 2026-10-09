# -*- coding: utf-8 -*-
"""世界线「模拟 / 世界模型 / 多视角 / 锚点」对比：本仓旧 lingshu.world vs lingshu_ng.world。

同进程跑两边（旧包按原名导入，不装 compat 别名），固定种子：

- shadow：follow / 追逐链影子重放与世界逐位一致性（SpacetimeConsistency，150 tick × 随机场景）；
- seek：静止目标追逐的距离翻转（越过目标后来回振荡）次数；
- seed：SevenLayerLoop / UnifiedWorldModel / WorldLearner 换 seed 后物理世界演化是否不同；
- multiview：同类两物体各 2 视角观测后的融合 3D 误差；
- support：叠放 vs 并排对的「支撑」判定准确率；
- timing：step_verified / verify_run / 七层 step 的中位耗时。

被 bench_world.py 调用写入 BENCH_WORLD.json 的 "sim" 段；也可单跑：python tests_ng/world/bench_world_sim.py
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from typing import Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from lingshu.world import multiview as o_mv  # noqa: E402
from lingshu.world import semantic_anchor_graph as o_sag  # noqa: E402
from lingshu.world import seven_layer_loop as o_sl  # noqa: E402
from lingshu.world import spacetime_consistency as o_stc  # noqa: E402
from lingshu.world import world3d as o_w3  # noqa: E402
from lingshu.world import world_learner as o_wl  # noqa: E402
from lingshu.world import world_model as o_wm  # noqa: E402
from lingshu.world.scene_simulator import SceneSimulator as OSim  # noqa: E402
from lingshu_ng.world import anchor_graph as n_sag  # noqa: E402
from lingshu_ng.world import compat as n_c  # noqa: E402
from lingshu_ng.world import multiview as n_mv  # noqa: E402
from lingshu_ng.world import seven_layer_loop as n_sl  # noqa: E402
from lingshu_ng.world import spacetime as n_stc  # noqa: E402
from lingshu_ng.world import world_learner as n_wl  # noqa: E402
from lingshu_ng.world import world_model as n_wm  # noqa: E402
from lingshu_ng.world.scene_sim import SceneSimulator as NSim  # noqa: E402

SEED, N = 20261009, 40
PATH = [(9.0, 1.5, 9.0), (1.0, 1.5, 9.0), (1.0, 1.5, 1.0)]
SIDES = {"legacy": dict(stc=o_stc.SpacetimeConsistency, sim=OSim, mv=o_mv, cam=o_w3.Camera3D,
                        sag=o_sag, sl=o_sl.SevenLayerLoop, wm=o_wm.UnifiedWorldModel,
                        wl=o_wl.WorldLearner),
         "ng": dict(stc=n_stc.SpacetimeConsistency, sim=NSim, mv=n_mv, cam=n_c.Camera3D, sag=n_sag,
                    sl=n_sl.SevenLayerLoop, wm=n_wm.UnifiedWorldModel, wl=n_wl.WorldLearner)}


def shadow(S: Dict) -> Dict:
    rng = random.Random(SEED)
    worst, miss_ticks, exact = 0.0, 0, 0
    for _ in range(N):
        stc = S["stc"](size=24)
        stc.add_path("loop", PATH)
        f = stc.add_entity("f", "follow", (rng.uniform(1, 23), 1.5, rng.uniform(1, 23)),
                           rng.uniform(0.1, 2.5), "loop")
        stc.add_entity("s", "seek", (rng.uniform(1, 23), 1.5, rng.uniform(1, 23)), rng.uniform(0.1, 1.5), f)
        for _ in range(150):
            for o in stc.step_verified()["outcomes"]:
                if o["mode"] == "exact":
                    exact += 1
                    worst = max(worst, o["distance"] or 0.0)
                    miss_ticks += not o["hit"]
    return {"scenes": N, "exact_outcomes": exact, "max_distance": round(worst, 4),
            "exact_misses": miss_ticks}


def seek(S: Dict) -> Dict:
    rng, flips, overs = random.Random(SEED + 1), 0, 0
    for _ in range(N):
        sim = S["sim"](size=24)
        t = sim.add_entity("t", "idle", (rng.uniform(2, 22), 1.5, rng.uniform(2, 22)), 0.0)
        s = sim.add_entity("s", "seek", (rng.uniform(2, 22), 1.5, rng.uniform(2, 22)), rng.uniform(0.2, 1.5), t)
        d = []
        for _ in range(200):                       # ≥ 最远距离 / 最低速度 ≈ 142 tick
            sim.step(1)
            a, b = sim.entities[s].pos, sim.entities[t].pos
            d.append(math.hypot(a[0] - b[0], a[2] - b[2]))
        flips += sum(1 for x, y, z in zip(d, d[1:], d[2:]) if (y - x) * (z - y) < -1e-12)
        overs += d[-1] > 0.0075
    return {"scenes": N, "distance_reversals": flips, "not_arrived_after_200": overs}


def _traj(sim) -> List:
    sim.add_entity("w", "wander", (12, 1.5, 12), 0.5)
    sim.step(10)
    return [tuple(e.pos) for e in sim.entities.values()]


def seed(S: Dict) -> Dict:
    out = {}
    for name in ("sl", "wm", "wl"):
        out[name + "_seed_changes_world"] = _traj(S[name](size=24, seed=1).world) != \
            _traj(S[name](size=24, seed=2).world)
    return out


def multiview(S: Dict) -> Dict:
    rng, errs, objs = random.Random(SEED + 2), [], []
    for _ in range(N):
        pts = [(rng.uniform(-3, -1), rng.uniform(0, 1), rng.uniform(5, 8)),
               (rng.uniform(1, 3), rng.uniform(0, 1), rng.uniform(5, 8))]
        f = S["mv"].MultiViewFusion()
        for x in (-3.0, 3.0):
            cam = S["cam"].look_at((x, 1.5, 0.0), (0.0, 0.5, 6.5))
            for p in pts:
                f.add_observation("chair", S["mv"].ViewObs(cam, cam.project(p, 800, 600), 800, 600))
        fused = f.fused_objects()
        objs.append(len(fused))
        for p in pts:
            errs.append(min((math.dist(o["center"], p) for o in fused), default=float("inf")))
    errs.sort()
    return {"scenes": N, "truth_objects_per_scene": 2, "fused_objects_mean": sum(objs) / len(objs),
            "err_median_m": round(errs[len(errs) // 2], 4), "err_max_m": round(errs[-1], 4)}


def support(S: Dict) -> Dict:
    rng, ok, n = random.Random(SEED + 3), 0, 0
    for _ in range(N):
        g = S["sag"].SemanticAnchorGraph()
        h = rng.uniform(0.4, 1.0)
        base = g.add("table", (0.0, h / 2, 5.0), (1.2, h, 0.8))
        top_h = rng.uniform(0.05, 0.3)
        cup = g.add("cup", (rng.uniform(-.4, .4), h + top_h / 2, 5.0), (0.1, top_h, 0.1))
        side = g.add("chair", (rng.uniform(0.9, 1.3), h / 2, 5.0), (0.5, h, 0.5))
        g.infer_relations()
        rel = {frozenset((e.source, e.target)): e.relation for e in g.edges}
        ok += rel.get(frozenset((base, cup))) == "支撑"
        ok += rel.get(frozenset((base, side))) != "支撑"
        n += 2
    return {"pairs": n, "accuracy": round(ok / n, 4)}


def _median_ms(fn, reps: int = 15) -> float:
    ts = []
    for _ in range(reps):
        t = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t)
    return round(sorted(ts)[len(ts) // 2] * 1000, 3)


def timing(S: Dict) -> Dict:
    stc = S["stc"](size=24)
    stc.add_path("loop", PATH)
    ids = [stc.add_entity("e%d" % i, "follow" if i % 2 else "wander", (2 + i, 1.5, 3 + i), 0.3,
                          "loop") for i in range(10)]
    wm = S["wm"](size=24)
    for i in range(10):
        wm.world.add_entity("e%d" % i, "seek" if i else "wander", (2 + i, 1.5, 3), 0.3,
                            list(wm.world.entities)[0] if i else "")
    wm.perceive()
    sl = S["sl"](size=24, seed=3)
    for i in range(6):
        sl.add_entity("e%d" % i, "wander", (3 + 2 * i, 1.5, 5), 0.3)
    sl.run(1)
    return {"entities": len(ids), "step_verified_ms": _median_ms(stc.step_verified),
            "wm_verify_run_ms": _median_ms(lambda: wm.verify_run(1)),
            "seven_layer_step_ms": _median_ms(sl.step)}


def sim_metrics() -> Dict:
    return {side: {"shadow": shadow(S), "seek": seek(S), "seed": seed(S), "multiview": multiview(S),
                   "support": support(S), "timing": timing(S)} for side, S in SIDES.items()}


if __name__ == "__main__":
    print(json.dumps(sim_metrics(), ensure_ascii=False, indent=1))
