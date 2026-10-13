# -*- coding: utf-8 -*-
"""compat.rust_bridge · 旧 ``lingshu.nn.rust_bridge`` 的 plan / Python 参考执行器同名适配。

plan 生成与旧实现逐位一致（缺省 n_params=375 只对 K1=K2=6 正确，保留以兼容 Rust 基线）；
执行器委托 :func:`lingshu_ng.nn.train.execute_plan`（seq = py_executor，par = py_executor_par），
plan 越界显式 ValueError。Rust 二进制打包/调用接口不在 ng 重写范围（无 hex_nn.exe）。
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from .. import train as TR

LEGACY_N_PARAMS = 6 * 7 + 6 * 6 * 7 + 9 * (6 + 3)


def make_plan(n: int, steps: int, batch: int, samples: int, seed: int, n_params: Optional[int] = None) -> Dict:
    """训练计划；n_params 必须等于被训练网络参数数（None → 旧缺省 375）。"""
    return TR.make_plan(n, steps, batch, samples, seed, LEGACY_N_PARAMS if n_params is None else n_params)


def _run(lat, obj_idx, shape_idx, vec0, plan, net, lr, eps, deadzone, mode) -> np.ndarray:
    v0 = np.asarray(vec0, dtype=np.float64)
    top = max((max(s) for s in plan["plan_sample"] if s), default=-1)
    if top >= v0.size:
        raise ValueError(f"plan 采样索引上界 {top} 超出参数向量长度 {v0.size}：make_plan 需传 n_params=net.n_params()")
    net.ng.params.set_vec(v0)
    return TR.execute_plan(net.ng, np.asarray(lat, dtype=np.float64), np.asarray(obj_idx), np.asarray(shape_idx),
                           plan, lr=lr, eps=eps, deadzone=deadzone, mode=mode)


def py_executor(lat: np.ndarray, obj_idx: np.ndarray, shape_idx: np.ndarray, vec0: np.ndarray, plan: Dict, net,
                lr: float = 0.1, eps: float = 1e-3, deadzone: float = 1e-6) -> np.ndarray:
    """顺序坐标下降执行器（旧 Rust train 语义）。"""
    return _run(lat, obj_idx, shape_idx, vec0, plan, net, lr, eps, deadzone, "seq")


def py_executor_par(lat: np.ndarray, obj_idx: np.ndarray, shape_idx: np.ndarray, vec0: np.ndarray, plan: Dict,
                    net, lr: float = 0.1, eps: float = 1e-3, deadzone: float = 1e-6) -> np.ndarray:
    """步初快照批量评估 → 统一收敛（旧 Rust train_par 语义）。"""
    return _run(lat, obj_idx, shape_idx, vec0, plan, net, lr, eps, deadzone, "par")
