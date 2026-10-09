# -*- coding: utf-8 -*-
"""compat_stubs · 兼容门面中**未迁移**的旧方法（显式清单）

两类：
  * :data:`WORLD_FACADE` —— 世界模型外观 13 个方法（#178）。已移到 :mod:`lingshu_ng.compat_world`：
    有 ng 世界线实现的（world3d / vprim_query / _load_vprims_from_memory / scene_simulator）委托
    ``lingshu_ng.world``；voxel_world / spacetime_consistency / world_model / world_learner /
    curiosity_explorer / seven_layer_loop 由 :mod:`lingshu_ng.compat_world_sim` 委托 ng 世界线；
    其余 3 个（:data:`WORLD_MISSING`）ng 世界线尚无组件，保持桩（NotImplementedError）。
  * :data:`NOT_READY` —— 旧版依赖仓外器官模块（预测/生命周期/飞轮/视觉/注意力/自我认知/
    语义空间/学习闭环……，#169），公开仓形态下这些方法本就恒返回「未装配」状态字典；
    ng 照原样返回同形状态字典（而非伪造成功），并在 ``error`` 里注明 ng 未内置。

不变量：这里的方法**从不写库**。
"""
from __future__ import annotations

from typing import Any, Callable, Dict

__all__ = ["StubsMixin", "WORLD_FACADE", "WORLD_MISSING", "NOT_READY", "UNSUPPORTED"]

WORLD_FACADE = ("world3d", "voxel_world", "wm_simloop", "scene_simulator", "spacetime_consistency",
                "world_model", "world_learner", "curiosity_explorer", "seven_layer_loop",
                "world_generator", "world_semantics", "vprim_query", "_load_vprims_from_memory")

_ERR = "ng 未内置该器官组件（旧版依赖仓外模块，公开仓形态下同样未装配）"


def _status(key: str, value: str) -> Callable[..., Dict]:
    return lambda *a, **k: {key: value, "error": _ERR}


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
    "sync_body_state": _status("status", "v112_not_ready"),
    "get_emotional_bias": _status("status", "v112_not_ready"),
    "get_self_reliability": _status("status", "v112_not_ready"),
    "learning_impact": _status("status", "v112_not_ready"),
    "lifecycle_cycle": _status("status", "v110_not_ready"),
    "start_lifecycle": _status("status", "v110_not_ready"),
    "stop_lifecycle": _status("status", "v110_not_ready"),
    "resolve_crisis": _status("status", "v110_not_ready"),
    "confirm_standby": _status("status", "v110_not_ready"),
    "enter_standby": _status("status", "v110_not_ready"),
    "wake_lifecycle": _status("status", "v110_not_ready"),
    "predict_routes": _status("status", "v19_not_ready"),
    "update_prediction_feedback": _status("status", "v19_not_ready"),
    "get_prediction_stats": _status("status", "v19_not_ready"),
    "render_semantic_map_2d": _status("status", "v19_not_ready"),
    "render_semantic_cube_3d": _status("status", "v19_not_ready"),
    "semantic_neighbors": lambda *a, **k: [],
    "attend_query": lambda *a, **k: [], "filter_attention": lambda signals, threshold=None: list(signals),
    "allocate_depth": lambda *a, **k: 1, "attention_shift": lambda *a, **k: 0.0,
    "adjust_attention_weight": _status("status", "v18_not_ready"),
    "run_learning_cycle": _status("status", "v13_not_ready"),
    "learn_next": _status("status", "v13_not_ready"),
    "get_next_candidate": lambda *a, **k: None,
    "query_by_semantics": lambda *a, **k: [],
    "resolve_concepts": lambda *a, **k: [], "compute_semantic_coordinates": lambda *a, **k: {},
    "annotate_semantics": lambda *a, **k: False, "compiler_introspect": _status("status", "not_ready"),
    "semantic_blindspot_report": _status("status", "not_ready"),
    "export_trajectory": _status("status", "not_ready"),
    "export_structured_trajectories": _status("status", "not_ready"),
    "pattern_separation_scan": lambda *a, **k: {"created": 0, "error": _ERR},
    "reconstruct_scene": lambda *a, **k: {"scene": [], "error": _ERR},
    "exploration_budget": lambda *a, **k: 1.0,
    "get_body_capabilities": lambda *a, **k: {"modalities": {"text": True, "image": False, "audio": False,
                                                             "video": False}, "devices": [], "note": _ERR},
    "set_vision_provider": lambda *a, **k: None, "get_vision_provider": lambda *a, **k: None,
    "set_attention_policy": lambda *a, **k: None, "get_attention_policy": lambda *a, **k: None,
    "set_semantic_provider": lambda *a, **k: None, "get_semantic_provider": lambda *a, **k: None,
}

#: ng 世界线（lingshu_ng.world）尚无对应组件的世界外观——保持桩：调用即 NotImplementedError
WORLD_MISSING = ("wm_simloop", "world_generator", "world_semantics")
#: 明确不支持（调用即 NotImplementedError）的方法
UNSUPPORTED = WORLD_MISSING


class StubsMixin:
    """把 :data:`NOT_READY` 与 :data:`UNSUPPORTED` 挂到门面上（``__getattr__`` 仅在常规查找失败时触发）。"""

    def __getattr__(self, name: str) -> Any:
        if name in NOT_READY:
            fn = NOT_READY[name]
            return lambda *a, **k: fn(*a, **k)
        if name in UNSUPPORTED:
            def _unsupported(*a: Any, **k: Any) -> Any:
                raise NotImplementedError(
                    f"{name} 未迁移：ng 世界线 lingshu_ng.world 尚无对应组件（世界外观已与记忆引擎解耦，#178；"
                    f"不回落旧 lingshu.world）")
            return _unsupported
        raise AttributeError(name)
