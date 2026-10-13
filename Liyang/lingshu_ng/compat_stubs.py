# -*- coding: utf-8 -*-
"""compat_stubs · 兼容门面中**不支持**的旧方法（显式清单 + 明确语义，stab-r3）

旧 ``SpacetimeMemoryEngine`` 有一批方法依赖仓外器官模块（飞轮 / 生命周期 / 预测 / 自我认知 / 学习闭环 / 视觉闭环 /
身体设备 / 世界生成……，#169 #178）。公开仓形态下这些器官不存在，上游自己就返回固定的「未装配」缺省值。
ng 不内置这些器官，因此这些方法的语义统一为：

1. **缺省（与上游缺省返回一致者优先）**：返回上游在器官缺失时返回的**同一个值、同一个形状**——
   状态字典（``{"status": "v111_not_ready", "error": …}`` 一类，``error`` 注明 ng 未内置）或上游的空值
   （``[]`` / ``False`` / ``0.0`` / ``1.0`` / ``None``）。调用方的「未装配」分支照常工作，不伪造成功。
   每个方法第一次被调用时打一条 WARNING 并登记进 :func:`lingshu_ng.diag.fallbacks`（键 ``compat_unsupported:<名>``），
   空值返回也看得见。
2. **严格模式**：环境变量 ``LINGSHU_NG_STRICT_UNSUPPORTED=1`` 时，调用任一方法都抛 :class:`NotSupportedError`
   （``NotImplementedError`` 的子类），信息里带 :data:`UNSUPPORTED_INFO` 的原因。适合要求「不支持就失败」的商用集成。
3. **可查询**：:data:`UNSUPPORTED_INFO` 给出每个方法的器官类别、上游缺省返回与原因；
   :func:`support_table` / ``engine.capabilities()["compat_methods"]`` 列出门面每个公开方法的支持状态。

stab-r3 相对 rel-v1.17 的语义变更（均为向上游缺省对齐）：
  * ``wm_simloop`` / ``world_generator`` / ``world_semantics`` 由抛 ``NotImplementedError`` 改为返回上游缺省状态字典
    （``simloop_not_ready`` / ``gen_not_ready`` / ``blindspot``）；严格模式下抛 :class:`NotSupportedError`（仍是 NotImplementedError）。
  * ``adjust_attention_weight`` 未注入注意力策略时返回 ``False``（上游缺省；ng 以前返回 ``v18_not_ready`` 字典）。
  * ``resolve_crisis`` 先校验设计者密钥（失败抛 ``DesignerRequired``，PermissionError 子类，与上游同序），再返回 ``v110_not_ready``。
  * ``get_body_capabilities`` / ``sync_body_state`` / ``export_trajectory`` / ``export_structured_trajectories``
    不依赖器官，已转为真实实现（:mod:`lingshu_ng.compat_body`），不在本清单。

不变量：这里的方法**从不写库**。
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, Tuple

from . import diag
from .governance import require_designer

__all__ = ["StubsMixin", "WORLD_FACADE", "WORLD_MISSING", "NOT_READY", "UNSUPPORTED", "UNSUPPORTED_INFO",
           "NotSupportedError", "STRICT_ENV", "strict_unsupported", "support_table"]

STRICT_ENV = "LINGSHU_NG_STRICT_UNSUPPORTED"

WORLD_FACADE = ("world3d", "voxel_world", "wm_simloop", "scene_simulator", "spacetime_consistency",
                "world_model", "world_learner", "curiosity_explorer", "seven_layer_loop",
                "world_generator", "world_semantics", "vprim_query", "_load_vprims_from_memory")

_ERR = "ng 未内置该器官组件（旧版依赖仓外模块，公开仓形态下同样未装配）"


class NotSupportedError(NotImplementedError):
    """兼容门面中 ng 不支持的旧方法（严格模式下抛出）。是 ``NotImplementedError`` 的子类。"""


def strict_unsupported() -> bool:
    """严格模式是否开启（每次调用时读环境变量）。"""
    return os.environ.get(STRICT_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _status(key: str, value: str) -> Callable[..., Dict]:
    return lambda *a, **k: {key: value, "error": _ERR}


def _resolve_crisis(directive: str = "", designer_key: Any = None, *a: Any, **k: Any) -> Dict:
    require_designer(designer_key, "resolve_crisis")         # 上游同序：先验密钥（PermissionError），再看器官
    return {"status": "v110_not_ready", "error": _ERR}


#: 器官类别 → (方法名, 上游缺省返回的说明)。说明照抄上游器官缺失分支的返回（上游 cb3a6ea lingshu/core/core.py）。
_GROUPS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "flywheel（进化飞轮）": (
        ("evo_distill_cycle", "{status: v111_not_ready, error}"), ("evo_flywheel_metrics", "{status: v111_not_ready, error}"),
        ("test_transfer_capability", "{status: v111_not_ready, error}"), ("universe_calibrate", "{status: v111_not_ready, error}"),
        ("shortest_path", "[]"), ("query_subgraph", "{query, nodes: {}, edges: []}"),
        ("mark_contested", "False"), ("resolve_contested", "False"), ("mark_stale", "False"), ("reverify", "False"),
        ("recency_weighted_update", "False")),
    "vision（视觉闭环）": (("perceive_image", "{status: vision_unavailable, error}"),),
    "body（身体设备注册表）": (("body_devices", "{status: body_not_ready, error, devices: [], health: []}"),
                        ("device_call", "{status: body_not_ready, error}")),
    "self_cognition（自我认知）": (
        ("cognition_cycle", "{status: v112_not_ready, error}"), ("cognition_report", "{status: v112_not_ready, error}"),
        ("get_emotional_bias", "{status: v112_not_ready, error}"), ("get_self_reliability", "{status: v112_not_ready, error}"),
        ("learning_impact", "{status: v112_not_ready, error}"), ("exploration_budget", "1.0")),
    "lifecycle（生命周期）": (
        ("lifecycle_cycle", "{status: v110_not_ready, error}"), ("start_lifecycle", "{status: v110_not_ready, error}"),
        ("stop_lifecycle", "{status: v110_not_ready, error}"),
        ("resolve_crisis", "设计者密钥无效 → DesignerRequired(PermissionError)；否则 {status: v110_not_ready, error}"),
        ("confirm_standby", "{status: v110_not_ready, error}"), ("enter_standby", "{status: v110_not_ready, error}"),
        ("wake_lifecycle", "{status: v110_not_ready, error}")),
    "prediction（预测 / 语义地图）": (
        ("predict_routes", "{status: v19_not_ready, error}"), ("update_prediction_feedback", "{status: v19_not_ready, error}"),
        ("get_prediction_stats", "{status: v19_not_ready, error}"), ("render_semantic_map_2d", "{status: v19_not_ready, error}"),
        ("render_semantic_cube_3d", "{status: v19_not_ready, error}"), ("semantic_neighbors", "[]")),
    "attention（注意力策略的增量接口）": (("attention_shift", "0.0"), ("adjust_attention_weight", "False")),
    "learning_loop（学习闭环）": (("run_learning_cycle", "{status: v13_not_ready, error}"),
                              ("learn_next", "{status: v13_not_ready, error}"), ("get_next_candidate", "None")),
    "semantic_coords（语义坐标列 / 实体注册表）": (("query_by_semantics", "[]"), ("annotate_semantics", "False")),
    "scene_memory（模式分离 / 场景重建）": (("pattern_separation_scan", "{created: 0, error}"),
                                     ("reconstruct_scene", "{scene: [], error}")),
    "world_gen（世界推演 / 生成 / 图像语义）": (
        ("wm_simloop", "{status: simloop_not_ready, error}"), ("world_generator", "{status: gen_not_ready, error}"),
        ("world_semantics", "{status: blindspot, reason, available: []}")),
}

#: 方法名 → 上游缺省返回（ng 照样返回；严格模式下改为抛 NotSupportedError）
NOT_READY: Dict[str, Callable[..., Any]] = {
    "evo_distill_cycle": _status("status", "v111_not_ready"),
    "evo_flywheel_metrics": _status("status", "v111_not_ready"),
    "test_transfer_capability": _status("status", "v111_not_ready"),
    "universe_calibrate": _status("status", "v111_not_ready"),
    "shortest_path": lambda *a, **k: [],
    "query_subgraph": lambda q, max_nodes=15: {"query": q, "nodes": {}, "edges": []},
    "mark_contested": lambda *a, **k: False, "resolve_contested": lambda *a, **k: False,
    "mark_stale": lambda *a, **k: False, "reverify": lambda *a, **k: False,
    "recency_weighted_update": lambda *a, **k: False,
    "perceive_image": _status("status", "vision_unavailable"),
    "body_devices": lambda *a, **k: {"status": "body_not_ready", "error": _ERR, "devices": [], "health": []},
    "device_call": _status("status", "body_not_ready"),
    "cognition_cycle": _status("status", "v112_not_ready"),
    "cognition_report": _status("status", "v112_not_ready"),
    "get_emotional_bias": _status("status", "v112_not_ready"),
    "get_self_reliability": _status("status", "v112_not_ready"),
    "learning_impact": _status("status", "v112_not_ready"),
    "exploration_budget": lambda *a, **k: 1.0,
    "lifecycle_cycle": _status("status", "v110_not_ready"),
    "start_lifecycle": _status("status", "v110_not_ready"),
    "stop_lifecycle": _status("status", "v110_not_ready"),
    "resolve_crisis": _resolve_crisis,
    "confirm_standby": _status("status", "v110_not_ready"),
    "enter_standby": _status("status", "v110_not_ready"),
    "wake_lifecycle": _status("status", "v110_not_ready"),
    "predict_routes": _status("status", "v19_not_ready"),
    "update_prediction_feedback": _status("status", "v19_not_ready"),
    "get_prediction_stats": _status("status", "v19_not_ready"),
    "render_semantic_map_2d": _status("status", "v19_not_ready"),
    "render_semantic_cube_3d": _status("status", "v19_not_ready"),
    "semantic_neighbors": lambda *a, **k: [],
    "attention_shift": lambda *a, **k: 0.0,
    "adjust_attention_weight": lambda *a, **k: False,
    "run_learning_cycle": _status("status", "v13_not_ready"),
    "learn_next": _status("status", "v13_not_ready"),
    "get_next_candidate": lambda *a, **k: None,
    "query_by_semantics": lambda *a, **k: [],
    "annotate_semantics": lambda *a, **k: False,
    "pattern_separation_scan": lambda *a, **k: {"created": 0, "error": _ERR},
    "reconstruct_scene": lambda *a, **k: {"scene": [], "error": _ERR},
    "wm_simloop": _status("status", "simloop_not_ready"),
    "world_generator": _status("status", "gen_not_ready"),
    "world_semantics": lambda *a, **k: {"status": "blindspot", "reason": _ERR, "available": []},
}

#: ng 世界线（lingshu_ng.world）尚无对应组件的世界外观（已并入 NOT_READY，返回上游缺省状态字典）
WORLD_MISSING = ("wm_simloop", "world_generator", "world_semantics")
#: 兼容旧名：不支持的方法全集（= NOT_READY 的键）
UNSUPPORTED = tuple(NOT_READY)

#: 方法名 → {organ, upstream_default, reason}
UNSUPPORTED_INFO: Dict[str, Dict[str, str]] = {
    name: {"organ": organ, "upstream_default": ret, "reason": _ERR}
    for organ, items in _GROUPS.items() for name, ret in items
}
assert set(UNSUPPORTED_INFO) == set(NOT_READY), "UNSUPPORTED_INFO 与 NOT_READY 必须一一对应"


def _call(name: str, a: Tuple, k: Dict) -> Any:
    info = UNSUPPORTED_INFO[name]
    if strict_unsupported():
        raise NotSupportedError(f"{name} 不受 lingshu_ng 支持：{info['reason']}（器官：{info['organ']}；"
                                f"非严格模式下返回上游缺省 {info['upstream_default']}）")
    diag.warn_once(f"compat_unsupported:{name}", f"{name} 未支持，返回上游缺省 {info['upstream_default']}（{info['organ']}）")
    return NOT_READY[name](*a, **k)


def support_table(cls: type) -> Dict[str, Dict[str, Any]]:
    """门面类 ``cls`` 每个公开方法的支持状态：``supported``（类上有真实实现）或 ``unsupported``（本清单，附原因与上游缺省）。"""
    out: Dict[str, Dict[str, Any]] = {}
    for name in dir(cls):
        if name.startswith("_") or name in NOT_READY:
            continue
        obj = getattr(cls, name, None)
        if callable(obj) and not isinstance(obj, type):
            out[name] = {"status": "supported"}
    strict = strict_unsupported()
    for name, info in UNSUPPORTED_INFO.items():
        out[name] = {"status": "unsupported", "on_call": "raise NotSupportedError" if strict else "upstream_default", **info}
    return dict(sorted(out.items()))


class StubsMixin:
    """把 :data:`NOT_READY` 挂到门面上（``__getattr__`` 仅在常规查找失败时触发）。"""

    def __getattr__(self, name: str) -> Any:
        if name in NOT_READY:
            def _unsupported(*a: Any, **k: Any) -> Any:
                return _call(name, a, k)
            _unsupported.__name__ = name
            _unsupported.__doc__ = f"不支持（{UNSUPPORTED_INFO[name]['organ']}）：返回上游缺省 {UNSUPPORTED_INFO[name]['upstream_default']}"
            return _unsupported
        raise AttributeError(name)
