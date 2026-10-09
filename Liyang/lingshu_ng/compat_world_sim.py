# -*- coding: utf-8 -*-
"""compat_world_sim · 旧世界外观中「模拟 / 世界模型」六个方法在 ng 门面上的委托

voxel_world / spacetime_consistency / world_model / world_learner / curiosity_explorer / seven_layer_loop
的动作协议与旧 ``lingshu.core.world_facade`` 相同（动作名、参数名、默认值、返回键），实现全部委托
ng 世界线 ``lingshu_ng.world.{voxel, spacetime, world_model, world_learner, curiosity, seven_layer_loop}``
（惰性导入：记忆引擎本体仍零依赖；numpy 不可用时返回旧版同名 ``*_not_ready`` 状态字典）。

与旧外观的差异（均为旧缺陷）：
  * ``init`` 一律按参数重建并返回重建后的状态（#243：旧版多个外观声明 init 却没有 init 分支）；
  * 数值参数先做 isfinite / 整数解析，非法输入与组件抛出的 ``ValueError`` 统一返回 ``status=error``，
    不再以异常穿出门面（#55 退化输入）。
不变量：这里的方法不写记忆库。
"""
from __future__ import annotations

import importlib
import math
from typing import Any, Callable, Dict, Optional, Tuple

__all__ = ["WorldSimFacade", "SIM_FACADES"]

Handler = Callable[[Any, Dict], Dict]


def _int(p: Dict, key: str, default: int) -> int:
    v = p.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ValueError(f"参数 {key} 必须是整数")
    f = float(v)
    if not math.isfinite(f) or f != int(f):
        raise ValueError(f"参数 {key} 必须是有限整数")
    return int(f)


def _float(p: Dict, key: str, default: float) -> float:
    f = float(p.get(key, default))
    if not math.isfinite(f):
        raise ValueError(f"参数 {key} 必须是有限值")
    return f


def _vec(p: Dict, key: str, default: Tuple[float, ...]) -> Tuple[float, ...]:
    raw = p.get(key)
    v = tuple(float(x) for x in (default if raw is None else raw))
    if len(v) != 3 or not all(math.isfinite(x) for x in v):
        raise ValueError(f"{key} 必须是 3 个有限数值")
    return v


# ------------------------------------------------------------------ 共用动作（场景 / 实体 / 路径）
def _scene_actions(target: Callable[[Any], Any], trees: int, water: bool) -> Dict[str, Handler]:
    """create / entity / path：作用在 ``target(obj)``（世界模型类是 obj.world，其余是 obj 本身）。"""
    def _create(o: Any, p: Dict) -> Dict:
        return {"status": "ok", "scene": target(o).create_scene(trees=_int(p, "trees", trees),
                                                                water=bool(p.get("water", water)))}

    def _entity(o: Any, p: Dict) -> Dict:
        eid = target(o).add_entity(str(p.get("category", "entity")), behavior=str(p.get("behavior", "wander")),
                                   pos=_vec(p, "pos", (2, 1.5, 2)), speed=_float(p, "speed", 0.3),
                                   goal=str(p.get("goal", "")))
        return {"status": "ok", "entity_id": eid}

    def _path(o: Any, p: Dict) -> Dict:
        target(o).add_path(str(p.get("path_id", "")), p.get("points", []))
        return {"status": "ok", "path_id": str(p.get("path_id", ""))}

    return {"create": _create, "entity": _entity, "path": _path}


def _world_of(o: Any) -> Any:
    return o.world


def _self(o: Any) -> Any:
    return o


def _ok(key: str, fn: Callable[[Any, Dict], Any]) -> Handler:
    return lambda o, p: {"status": "ok", key: fn(o, p)}


# ------------------------------------------------------------------ 各外观的构造参数与动作表
def _stc_actions() -> Dict[str, Handler]:
    def _teleport(o: Any, p: Dict) -> Dict:
        ok = o.teleport(str(p.get("entity_id", "")), _vec(p, "pos", (0, 0, 0)))
        return {"status": "ok" if ok else "error", "queued": ok}

    def _consistent(o: Any, p: Dict) -> Dict:
        rep = o.consistency_report()
        return {"status": "ok", "self_consistent": rep["self_consistent"], "verdict": rep["verdict"],
                "overall_hit_rate": rep["overall_hit_rate"], "rolling_hit_rate": rep["rolling_hit_rate"]}

    acts = _scene_actions(_self, 4, True)
    acts.update({
        "run": _ok("run", lambda o, p: o.run(n=_int(p, "n", 10))),
        "step": _ok("step", lambda o, p: o.step_verified()),
        "teleport": _teleport,
        "report": _ok("report", lambda o, p: o.consistency_report()),
        "self_consistent": _consistent,
        "drift": lambda o, p: {"status": "ok", "drift_events": o.drift_events(), "drift_active": o.drift_active()},
        "history": _ok("history", lambda o, p: o.prediction_history(limit=_int(p, "limit", 10))),
    })
    return acts


def _wm_actions() -> Dict[str, Handler]:
    acts = _scene_actions(_world_of, 2, False)
    acts.update({
        "perceive": _ok("perceive", lambda o, p: o.perceive(tool=str(p.get("tool", "observer")))),
        "generate": _ok("generate", lambda o, p: o.generate(horizon=_int(p, "horizon", 1))),
        "verify": _ok("verify", lambda o, p: o.verify()),
        "run": _ok("run", lambda o, p: o.verify_run(n=_int(p, "n", 10))),
        "patterns": _ok("patterns", lambda o, p: o.patterns()),
        "anomalies": _ok("anomalies", lambda o, p: o.anomalies(limit=_int(p, "limit", 20))),
        "graph": _ok("graph", lambda o, p: o.graph()),
        "history": _ok("history", lambda o, p: o.history_view(limit=_int(p, "limit", 10))),
        "state": _ok("model", lambda o, p: o.state()),
    })
    return acts


def _wl_actions() -> Dict[str, Handler]:
    acts = _scene_actions(_world_of, 2, False)
    acts.update({
        "run": _ok("run", lambda o, p: o.run(n=_int(p, "n", 10))),
        "learn": _ok("learned", lambda o, p: o.learn()),
        "predict": _ok("predict", lambda o, p: o.predict(horizon=_int(p, "horizon", 1))),
        "evaluate": _ok("evaluate", lambda o, p: o.evaluate(train_ticks=_int(p, "train_ticks", 30),
                                                            eval_ticks=_int(p, "eval_ticks", 15))),
        "curve": _ok("curve", lambda o, p: o.learning_curve(epochs=_int(p, "epochs", 4),
                                                            per_epoch_ticks=_int(p, "per_epoch_ticks", 10),
                                                            eval_ticks=_int(p, "eval_ticks", 8))),
        "masked": _ok("masked", lambda o, p: o.masked_loss()),
        "model": _ok("model", lambda o, p: o.model_params()),
        "history": _ok("history", lambda o, p: o.history_view(limit=_int(p, "limit", 10))),
        "state": _ok("learner", lambda o, p: o.state()),
    })
    return acts


def _cx_actions() -> Dict[str, Handler]:
    acts = _scene_actions(_world_of, 2, False)
    acts.update({
        "explore": _ok("explore", lambda o, p: o.explore(ticks=_int(p, "n", 30), budget=_int(p, "budget", 2),
                                                         policy=str(p.get("policy", "curiosity")))),
        "step": _ok("step", lambda o, p: o.explore_tick(budget=_int(p, "budget", 2),
                                                        policy=str(p.get("policy", "curiosity")))),
        "probe": _ok("probe", lambda o, p: o.probe(ticks=_int(p, "n", 15))),
        "compare": _ok("compare", lambda o, p: o.compare_policies(budget=_int(p, "budget", 2),
                                                                  explore_ticks=_int(p, "explore_ticks", 40),
                                                                  probe_ticks=_int(p, "probe_ticks", 15))),
        "curiosity": _ok("curiosity", lambda o, p: o.curiosity_summary()),
        "uncertainty": lambda o, p: {"status": "ok", "curve": list(o.uncertainty_curve),
                                     "current": o.uncertainty()},
        "model": _ok("model", lambda o, p: o.model_params()),
        "history": _ok("history", lambda o, p: o.history_view(limit=_int(p, "limit", 10))),
        "state": _ok("explorer", lambda o, p: o.state()),
    })
    return acts


def _sll_actions() -> Dict[str, Handler]:
    acts = _scene_actions(_self, 2, False)
    acts.update({
        "run": _ok("run", lambda o, p: o.run(n=_int(p, "n", 30))),
        "step": _ok("step", lambda o, p: o.step()),
        "report": _ok("report", lambda o, p: o.report()),
        "audit": _ok("audit", lambda o, p: o.audit_view(limit=_int(p, "limit", 10))),
        "verify": _ok("verify", lambda o, p: o.verify_state()),
        "decision": _ok("decision", lambda o, p: o.decision_state()),
        "memory": _ok("memory", lambda o, p: o.memory_state()),
        "graph": _ok("graph", lambda o, p: o.graph_state()),
        "state": _ok("loop", lambda o, p: o.state()),
    })
    return acts


def _common_kw(p: Dict) -> Dict:
    return {"size": _int(p, "size", 24), "ground_level": _int(p, "ground_level", 1), "seed": _int(p, "seed", 42)}


def _stc_kw(p: Dict) -> Dict:
    return {"size": _int(p, "size", 24), "ground_level": _int(p, "ground_level", 1),
            "window": _int(p, "window", 20), "hit_threshold": _float(p, "hit_threshold", 0.5),
            "drift_rate": _float(p, "drift_rate", 0.7), "drift_ticks": _int(p, "drift_ticks", 5),
            "consistent_rate": _float(p, "consistent_rate", 0.85),
            "min_consistent_ticks": _int(p, "min_consistent_ticks", 50), "seed": _int(p, "seed", 42)}


def _wl_kw(p: Dict) -> Dict:
    return {**_common_kw(p), "window": _int(p, "window", 6)}


def _sll_kw(p: Dict) -> Dict:
    return {**_wl_kw(p), "budget": _int(p, "budget", 2), "policy": str(p.get("policy", "curiosity"))}


#: 外观名 → (ng 模块, 类, 实例属性, 构造参数解析, 动作表工厂, init 后返回的动作, 未装配状态名)
SIM_FACADES: Dict[str, Tuple[str, str, str, Callable[[Dict], Dict], Callable[[], Dict[str, Handler]], str, str]] = {
    "spacetime_consistency": ("spacetime", "SpacetimeConsistency", "_stc", _stc_kw, _stc_actions, "report",
                              "stc_not_ready"),
    "world_model": ("world_model", "UnifiedWorldModel", "_wmodel", _common_kw, _wm_actions, "state",
                    "wm_not_ready"),
    "world_learner": ("world_learner", "WorldLearner", "_wlearner", _wl_kw, _wl_actions, "state", "wl_not_ready"),
    "curiosity_explorer": ("curiosity", "CuriosityExplorer", "_curious", _wl_kw, _cx_actions, "state",
                           "cx_not_ready"),
    "seven_layer_loop": ("seven_layer_loop", "SevenLayerLoop", "_sll", _sll_kw, _sll_actions, "state",
                         "sll_not_ready"),
}


def _component(module: str, cls: str) -> Any:
    """惰性导入 ng 世界线组件类（numpy）；不可用时抛 ImportError。"""
    return getattr(importlib.import_module(f"lingshu_ng.world.{module}"), cls)


class WorldSimFacade:
    """混入 SpacetimeMemoryEngine 门面：六个模拟 / 世界模型外观。"""

    def _sim_facade(self, name: str, action: str, params: Optional[dict]) -> dict:
        module, cls, attr, kw, actions, after_init, not_ready = SIM_FACADES[name]
        p = params or {}
        try:
            klass = _component(module, cls)
        except ImportError as exc:
            return {"status": not_ready, "error": str(exc)}
        table = actions()
        try:
            if action == "init" or getattr(self, attr, None) is None:
                setattr(self, attr, klass(**kw(p)))      # #243：init 按参数重建
            if action == "init":
                action = after_init
            handler = table.get(action)
            if handler is None:
                return {"status": "error", "error": f"未知动作 {action}（可用: init/{'/'.join(table)}）"}
            return handler(getattr(self, attr), p)
        except (ValueError, TypeError) as exc:
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    def spacetime_consistency(self, action: str, params: Optional[dict] = None) -> dict:
        """时空一致性验证（init/create/entity/path/run/step/teleport/report/self_consistent/drift/history）。"""
        return self._sim_facade("spacetime_consistency", action, params)

    def world_model(self, action: str, params: Optional[dict] = None) -> dict:
        """统一世界模型（init/create/entity/path/perceive/generate/verify/run/patterns/anomalies/graph/history/state）。"""
        return self._sim_facade("world_model", action, params)

    def world_learner(self, action: str, params: Optional[dict] = None) -> dict:
        """自监督世界学习（init/create/entity/path/run/learn/predict/evaluate/curve/masked/model/history/state）。"""
        return self._sim_facade("world_learner", action, params)

    def curiosity_explorer(self, action: str, params: Optional[dict] = None) -> dict:
        """好奇驱动探索（init/create/entity/path/explore/step/probe/compare/curiosity/uncertainty/model/…）。"""
        return self._sim_facade("curiosity_explorer", action, params)

    def seven_layer_loop(self, action: str, params: Optional[dict] = None) -> dict:
        """七层闭环（init/create/entity/path/run/step/report/audit/verify/decision/memory/graph/state）。"""
        return self._sim_facade("seven_layer_loop", action, params)

    # ------------------------------------------------------------ voxel_world（无 init 动作，旧协议）
    def voxel_world(self, action: str, params: Optional[dict] = None) -> dict:
        """4D 体素沙盒（build/spawn/simulate/trail/state），委托 ng VoxelWorld。"""
        p = params or {}
        try:
            klass = _component("voxel", "VoxelWorld")
        except ImportError as exc:
            return {"status": "voxel_not_ready", "error": str(exc)}
        try:
            if getattr(self, "_voxel", None) is None:
                self._voxel = klass(size=_int(p, "size", 16), ground_level=_int(p, "ground_level", 1))
            vw = self._voxel
            if action == "build":
                blocks = vw.build_flatland(trees=_int(p, "trees", 2), water=bool(p.get("water", True)))
                return {"status": "ok", "blocks": blocks, "world": vw.world_state()}
            if action == "spawn":
                eid = vw.spawn_entity(str(p.get("category", "entity")), _vec(p, "pos", (0, 1, 0)),
                                      velocity=_vec(p, "velocity", (0, 0, 0)))
                return {"status": "ok", "entity_id": eid}
            if action == "simulate":
                moved = vw.simulate(steps=_int(p, "steps", 1))
                return {"status": "ok", "entities_moved": moved, "step": vw.world_state().get("step")}
            if action == "trail":
                eid = str(p.get("entity_id", ""))
                return {"status": "ok", "entity_id": eid, "trail": vw.trail(eid)}
            if action == "state":
                return {"status": "ok", "world": vw.world_state()}
        except (ValueError, TypeError) as exc:
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        return {"status": "error", "error": f"未知动作 {action}（可用: build/spawn/simulate/trail/state）"}
