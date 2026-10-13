# -*- coding: utf-8 -*-
"""infogap · 信息差门控递归训练（旧 hex_train.train_infogap / pretrain_selfsup 的 ng 实现）。

语义与旧实现一致：全局死区收敛、支路死区冻结、停滞 → 生长（+1 核，mix 新列置零）→
验证 → 固化或撤销。差异：
- 撤销恢复**全部**参数快照（旧实现只恢复 conv/mix，验证期间改过的 fc 留在网络里）；
- 求值走增量扰动缓存（见 :mod:`train`）；参数写入经参数仓原子接口；
- 随机源显式注入，调用顺序与旧实现相同（permutation → choice，验证环节同序）。
"""
from __future__ import annotations

import time
from typing import Dict, List

import numpy as np

from .conv import hex_conv, im2col
from .net import RngLike, as_rng
from .train import ce_loss_fn, fd_sign_sweep


def _loss(model, x: np.ndarray, y: np.ndarray) -> float:
    return ce_loss_fn(y)(model.forward_cache(x)["logits"])


def _sweep(model, x: np.ndarray, y: np.ndarray, g: np.random.Generator, cfg: Dict,
           always: bool = False) -> Dict:
    idx = g.permutation(len(x))[:cfg["batch"]]
    cache = model.forward_cache(x[idx])
    lf = ce_loss_fn(y[idx])
    d = lf(cache["logits"])
    n = model.params.size
    sample = g.choice(n, size=min(cfg["samples_per_step"], n), replace=False)
    return {"idx": idx, "d": d, "cache": cache, "lf": lf, "sample": sample}


def _grow_and_verify(model, x, y, g, cfg: Dict, xb, yb, step: int) -> Dict:
    d_before = _loss(model, xb, yb)
    snap = [(n, model.params.view(n).copy()) for n in model.params.names()]
    model.grow_kernel()
    for _ in range(cfg["verify_steps"]):
        s = _sweep(model, x, y, g, cfg)
        fd_sign_sweep(model, s["cache"], s["lf"], s["sample"], cfg["lr"], cfg["eps"], 0.0, always=True)
    d_after = _loss(model, xb, yb)
    if d_after <= d_before * cfg["retain_gain"]:
        return {"grew": True, "d_after": d_after, "entry": {
            "step": step, "D": round(d_after, 5), "K": model.K, "verdict": "GROW",
            "note": f"新条件分支通过验证({d_before:.4f}->{d_after:.4f})"}}
    model.params.rebuild(snap)
    return {"grew": False, "d_after": d_after, "entry": {
        "step": step, "D": round(d_after, 5), "K": model.K, "verdict": "REVERT",
        "note": f"新分支验证失败,撤销不固化({d_before:.4f}->{d_after:.4f})"}}


DEFAULT_CFG = dict(lr=0.05, eps=1e-3, samples_per_step=24, batch=128, dead_zone_ratio=0.05,
                   branch_resolution=1e-6, stall_patience=8, stall_eps=0.005, max_growth=3,
                   max_steps=200, verify_steps=4, retain_gain=0.98)


def train_infogap(model, x: np.ndarray, y: np.ndarray, rng: RngLike = 7, **kw) -> Dict:
    """信息差门控递归训练（参数见 DEFAULT_CFG）。返回演化史与统计。"""
    cfg = dict(DEFAULT_CFG, **kw)
    g = as_rng(rng)
    t0 = time.time()
    d0 = _loss(model, x[:cfg["batch"]], y[:cfg["batch"]])
    dead = d0 * cfg["dead_zone_ratio"]
    st = {"best": d0, "stall": 0, "growths": 0, "reverts": 0, "frozen": 0}
    history: List[Dict] = []
    for step in range(cfg["max_steps"]):
        s = _sweep(model, x, y, g, cfg)
        if s["d"] <= dead:
            history.append({"step": step, "D": round(s["d"], 5), "verdict": "CONVERGED",
                            "note": "全局信息差落入死区"})
            break
        upd, frz = fd_sign_sweep(model, s["cache"], s["lf"], s["sample"], cfg["lr"], cfg["eps"],
                                 cfg["branch_resolution"])
        st["frozen"] += frz
        history.append(_after_step(model, x, y, g, cfg, st, s, step, upd))
    return {"algo": "hex_train-ng", "dead_zone": round(dead, 5), "final_D": history[-1]["D"] if history else round(d0, 5),   # #254：max_steps=0
            "steps": len(history), "growths": st["growths"], "reverts": st["reverts"],
            "final_K": model.K, "n_params": model.params.size, "frozen_total": st["frozen"],
            "seconds": round(time.time() - t0, 1), "history": history}


def _after_step(model, x, y, g, cfg: Dict, st: Dict, s: Dict, step: int, upd: int) -> Dict:
    d = s["d"]
    if (st["best"] - d) / max(1e-9, st["best"]) < cfg["stall_eps"]:
        st["stall"] += 1
    else:
        st["stall"], st["best"] = 0, min(st["best"], d)
    if st["stall"] >= cfg["stall_patience"] and st["growths"] + st["reverts"] < cfg["max_growth"]:
        st["stall"] = 0
        r = _grow_and_verify(model, x, y, g, cfg, x[s["idx"]], y[s["idx"]], step)
        if r["grew"]:
            st["growths"] += 1
            st["best"] = r["d_after"]
        else:
            st["reverts"] += 1
        return r["entry"]
    return {"step": step, "D": round(d, 5), "updates": upd, "frozen": int(s["sample"].size - upd),
            "K": model.K, "verdict": "ACCEPT_ADJUST"}


def pretrain_selfsup(model, x: np.ndarray, rng: RngLike = 7, mask_ratio: float = 0.25, lr: float = 0.05,
                     eps: float = 1e-3, samples_per_step: int = 16, batch: int = 64, steps: int = 60) -> Dict:
    """x-prediction 掩码重建：只调 conv 段（坐标梯度步，非符号）。

    与旧实现的差异：
    - 重建损失对核参数是二次的，中心差分同时给出梯度 g 与曲率 c；步长取 ``min(lr, 1/c)``——
      不越过该坐标上的极小点，单步损失不升（旧实现固定 lr，曲率大于 2/lr 时发散）。
    - ``init/final/curve`` 在**固定探针**（训练前一次抽定的样本与掩码）上度量，``init`` 为训练前损失；
      旧实现每步换批换掩码后报告该步自己的损失，首末两点是不同掩码上的读数。画幅内晶格上
      掩码间标准差（≈0.15）大于 20 步的真实下降（≈0.07），首末比较由噪声决定；旧越界晶格约 41%
      cell 为画幅外常数零填充、平凡可重建，方差小（≈0.06）且降幅大，掩盖了该口径问题。
      逐步训练损失另存 ``batch_curve``。"""
    g = as_rng(rng)
    a, b = model.params.slice_of("conv")
    probe = np.asarray(x[g.permutation(len(x))[:batch]], dtype=np.float64)[..., :1]
    probe_hole = g.random(probe.shape[:3]) < mask_ratio
    probe_in = np.where(probe_hole[..., None], 0.0, probe)
    probe_tgt = probe[..., 0][probe_hole]

    def probe_loss() -> float:
        return round(float(((_recon_pred(model, probe_in)[probe_hole] - probe_tgt) ** 2).mean()), 5)

    curve, batch_curve = [probe_loss()], []
    for _ in range(steps):
        xb = np.asarray(x[g.permutation(len(x))[:batch]], dtype=np.float64)[..., :1]
        masked = xb.copy()
        hole = g.random(xb.shape[:3]) < mask_ratio
        masked[hole] = 0.0
        cols = im2col(masked)[..., 0]                         # (B,N,7)
        tgt = xb[..., 0][hole]
        sample = g.choice(b - a, size=min(samples_per_step, b - a), replace=False)
        for pi in sample:
            pred = _recon_pred(model, masked)
            dcol = cols[:, :, int(pi) % 7].reshape(pred.shape) / model.params.view("conv").shape[0]
            l0 = float(((pred[hole] - tgt) ** 2).mean())
            lp = float((((pred + eps * dcol)[hole] - tgt) ** 2).mean())
            lm = float((((pred - eps * dcol)[hole] - tgt) ** 2).mean())
            grad, curv = (lp - lm) / (2 * eps), (lp - 2 * l0 + lm) / (eps * eps)
            step = lr if curv <= 1e-12 else min(lr, 1.0 / curv)
            model.params.apply_delta(a + int(pi), -step * grad)
        batch_curve.append(round(float(((_recon_pred(model, masked)[hole] - tgt) ** 2).mean()), 5))
        curve.append(probe_loss())
    return {"algo": "hex_train-ng+selfsup", "init": curve[0], "final": curve[-1], "curve": curve,
            "batch_curve": batch_curve}


def _recon_pred(model, masked: np.ndarray) -> np.ndarray:
    return hex_conv(masked, model.params.view("conv")[:, None, :]).mean(axis=-1)
