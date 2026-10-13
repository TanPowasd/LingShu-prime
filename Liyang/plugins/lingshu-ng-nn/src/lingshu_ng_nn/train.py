# -*- coding: utf-8 -*-
"""train · 信息差门控符号更新训练（零链式法则主路径 + 解析梯度对照路径）。

主路径保持旧语义：随机抽支路 → 中心差分 → ``-lr·sign(g)``，|g| 低于分辨率的支路冻结。
差异只在求值方式：
- 每步一次整网前向得到缓存，单支路扰动走 ``model.perturb``（只重算受影响通道）；
- ``mode="seq"``（默认，= 旧实现的顺序坐标下降）：每次更新经 ``model.commit`` 原子写入
  参数仓并把缓存就地推进，下一支路在新参数上求差分；
- ``mode="par"``（= Rust train_par 语义）：全部支路在步初快照上求差分，最后统一写入。
- ``train_sign_grad``：同一符号更新规则，梯度取 ``model.backward``（审计/基准对照用）。

随机性：每个入口只接受显式 ``rng``（种子或 Generator），抽样调用顺序与旧实现一致。
形状辅助损失按 OBJ 的「形状主序」分组 ``p[:, 3i:3i+3]``（旧 train_hier 误用 ``p[:, i::3]``
按颜色分组，PR #70）。
"""
from __future__ import annotations

from typing import Callable, Dict, List, Sequence, Tuple

import numpy as np

from .net import RngLike, as_rng, softmax

LossFn = Callable[[np.ndarray], float]


def joint_hier_loss(logits: np.ndarray, obj_idx: np.ndarray, shape_idx: np.ndarray,
                    n_colors: int = 3) -> float:
    """物体 CE + 0.5·形状边缘 CE（OBJ = 形状主序 shape|color）。"""
    p = softmax(logits)
    ps = p.reshape(len(p), -1, n_colors).sum(axis=2)
    d_obj = -np.log(p[np.arange(len(obj_idx)), obj_idx] + 1e-12).mean()
    d_shape = -np.log(ps[np.arange(len(shape_idx)), shape_idx] + 1e-12).mean()
    return float(d_obj + 0.5 * d_shape)


def joint_dlogits(p: np.ndarray, obj_idx: np.ndarray, shape_idx: np.ndarray, n_colors: int = 3) -> np.ndarray:
    """joint_hier_loss 对 logits 的解析梯度（输入 p = softmax(logits)）。"""
    b = len(p)
    d = p.copy()
    d[np.arange(b), obj_idx] -= 1.0
    grp = p.reshape(b, -1, n_colors)
    sel = grp.sum(axis=2)[np.arange(b), shape_idx][:, None, None]
    mask = np.zeros_like(grp)
    mask[np.arange(b), shape_idx] = 1.0
    d_shape = grp * (1.0 - mask / sel)
    return (d + 0.5 * d_shape.reshape(b, -1)) / b


def fd_sign_sweep(model, cache: Dict, loss: LossFn, sample: Sequence[int], lr: float, eps: float,
                  resolution: float, strict: bool = False, mode: str = "seq",
                  always: bool = False) -> Tuple[int, int]:
    """一轮支路符号更新。返回 (更新数, 冻结数)。

    strict=True：|g|>res 才更新（否则 ≥）；always=True：不设死区（旧生长验证环节语义，
    sign(0)=0 自然不动）。"""
    pending: List[Tuple[int, float]] = []
    updates = frozen = 0
    for pi in sample:
        pi = int(pi)
        g = (loss(model.perturb(cache, pi, eps)["logits"])
             - loss(model.perturb(cache, pi, -eps)["logits"])) / (2 * eps)
        ok = always or (abs(g) > resolution if strict else abs(g) >= resolution)
        if not ok:
            frozen += 1
            continue
        updates += 1
        step = -lr * float(np.sign(g))
        if mode == "seq":
            model.commit(cache, pi, step)
        else:
            pending.append((pi, step))
    if pending:
        idx, d = zip(*pending)
        model.params.apply_delta(list(idx), np.array(d))
    return updates, frozen


def train_hier(model, lat: np.ndarray, obj_idx: np.ndarray, shape_idx: np.ndarray, steps: int = 120,
               samples_per_step: int = 20, lr: float = 0.05, eps: float = 1e-3, batch: int = 96,
               rng: RngLike = 7, mode: str = "seq") -> Dict:
    """L2+L3 联合监督的符号更新训练（旧 train_hier 语义，修正形状分组）。"""
    g = as_rng(rng)
    n = model.params.size
    first = np.arange(min(batch, len(lat)))
    d0 = joint_hier_loss(model.forward_cache(lat[first])["logits"], obj_idx[first], shape_idx[first])
    curve = []
    for _ in range(steps):
        idx = g.permutation(len(lat))[:batch]
        cache = model.forward_cache(lat[idx])
        lf = lambda lg, b=idx: joint_hier_loss(lg, obj_idx[b], shape_idx[b])
        curve.append(round(lf(cache["logits"]), 4))
        sample = g.choice(n, size=min(samples_per_step, n), replace=False)
        fd_sign_sweep(model, cache, lf, sample, lr, eps, 1e-6, strict=True, mode=mode)
    return {"init_D": round(d0, 4), "final_D": curve[-1] if curve else round(d0, 4),
            "curve": curve, "steps": steps}


def train_sign_grad(model, lat: np.ndarray, obj_idx: np.ndarray, shape_idx: np.ndarray, steps: int = 120,
                    samples_per_step: int = 20, lr: float = 0.05, batch: int = 96, rng: RngLike = 7,
                    resolution: float = 1e-6) -> Dict:
    """对照路径：同样的抽样与符号更新，梯度来自解析反向（每步一次前向 + 一次反向）。"""
    g = as_rng(rng)
    n = model.params.size
    curve = []
    for _ in range(steps):
        idx = g.permutation(len(lat))[:batch]
        c = model.forward_cache(lat[idx])
        curve.append(round(joint_hier_loss(c["logits"], obj_idx[idx], shape_idx[idx]), 4))
        grad = model.backward(c, joint_dlogits(softmax(c["logits"]), obj_idx[idx], shape_idx[idx]))
        sample = g.choice(n, size=min(samples_per_step, n), replace=False)
        keep = sample[np.abs(grad[sample]) > resolution]
        if keep.size:
            model.params.apply_delta(keep, -lr * np.sign(grad[keep]))
    return {"final_D": curve[-1] if curve else None, "curve": curve, "steps": steps}


def make_plan(n: int, steps: int, batch: int, samples: int, rng: RngLike, n_params: int) -> Dict:
    """训练计划（权威随机性）：采样空间显式 = 被训练网络参数数。"""
    g = as_rng(rng)
    pb = [g.permutation(n)[:batch].tolist() for _ in range(steps)]
    ps = [g.choice(n_params, size=min(samples, n_params), replace=False).tolist() for _ in range(steps)]
    return {"plan_batch": pb, "plan_sample": ps}


def execute_plan(model, lat: np.ndarray, obj_idx: np.ndarray, shape_idx: np.ndarray, plan: Dict,
                 lr: float = 0.1, eps: float = 1e-3, deadzone: float = 1e-6, mode: str = "seq") -> np.ndarray:
    """按外部 plan 执行（seq = 旧 py_executor，par = py_executor_par）；plan 越界显式报错。"""
    n = model.params.size
    top = max((max(s) for s in plan["plan_sample"] if len(s)), default=-1)
    if top >= n:
        raise ValueError(f"plan 采样索引上界 {top} 超出参数向量长度 {n}：make_plan 需传 n_params")
    curve = []
    for bidx, sample in zip(plan["plan_batch"], plan["plan_sample"]):
        b = np.asarray(bidx)
        cache = model.forward_cache(lat[b])
        lf = lambda lg, b=b: joint_hier_loss(lg, obj_idx[b], shape_idx[b])
        curve.append(lf(cache["logits"]))
        fd_sign_sweep(model, cache, lf, sample, lr, eps, deadzone, strict=False, mode=mode)
    return np.array(curve)


def ce_loss_fn(y: np.ndarray) -> LossFn:
    """标签 y 的交叉熵损失闭包（稳定 log-softmax）。"""
    def f(logits: np.ndarray) -> float:
        z = logits - logits.max(axis=1, keepdims=True)
        logp = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
        return float(-logp[np.arange(len(y)), y].mean())
    return f
