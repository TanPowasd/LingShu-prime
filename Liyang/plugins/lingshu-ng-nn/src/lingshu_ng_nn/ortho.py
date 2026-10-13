# -*- coding: utf-8 -*-
"""ortho · 核族正交去重 + 正交残差金字塔（信息差自适应深度）。

语义同旧 hex_ortho：Gram-Schmidt 新信息占比 < tol 判重复解释；金字塔逐层选对残差解释增益
最大的核，对全部已选原子最小二乘重解，残差能量占比 < dead_zone 即停。
差异：全部候选原子 ``a_c = P_c F₀`` 由一次 im2col 张量收缩得到（float64），不在循环里反复卷积。
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .conv import im2col

DEAD_ZONE = 0.10
ORTHO_TOL = 0.20
MAX_LAYERS = 8
KERNEL_NAMES: List[str] = (["edge_d%d" % d for d in range(6)] + ["smooth", "coarse", "laplacian", "center_surround"]
                           + ["noise_k%d" % i for i in range(8)])


def kname(i: int, names: Optional[Sequence[str]] = None) -> str:
    """核序号 → 名字。"""
    nm = names if names else KERNEL_NAMES
    return nm[i] if i < len(nm) else f"k{i}"


def gram_schmidt_kernels(kernels: Sequence[np.ndarray], tol: float = ORTHO_TOL,
                         names: Optional[Sequence[str]] = None) -> List[Dict]:
    """逐核新信息占比 ‖k − Σproj‖/‖k‖；< tol 判重复解释。"""
    kept: List[np.ndarray] = []
    kept_idx: List[int] = []
    report = []
    for i, k in enumerate(kernels):
        v = np.asarray(k, dtype=np.float64).ravel().copy()
        n0 = float(np.linalg.norm(v))
        expl = []
        for j, u in zip(kept_idx, kept):
            if n0 < 1e-12:
                break
            proj = float(v @ u)
            if abs(proj) > 1e-9:
                expl.append(j)
            v = v - proj * u
        n1 = float(np.linalg.norm(v))
        ratio = n1 / n0 if n0 > 1e-12 else 0.0
        red = ratio < tol
        if not red:
            kept.append(v / (n1 + 1e-12))
            kept_idx.append(i)
        report.append({"idx": i, "name": kname(i, names), "norm": round(n0, 4), "new_info_ratio": round(ratio, 4),
                       "redundant": bool(red), "explained_by": expl if red else []})
    return report


def orthogonal_pool(kernels: Sequence[np.ndarray], tol: float = ORTHO_TOL,
                    names: Optional[Sequence[str]] = None) -> Tuple[List[int], List[Dict]]:
    """(保留核下标, 全量报告)。"""
    rep = gram_schmidt_kernels(kernels, tol, names)
    return [r["idx"] for r in rep if not r["redundant"]], rep


def atoms(f0: np.ndarray, kernels: Sequence[np.ndarray]) -> np.ndarray:
    """全部核在 F₀ 上的逐通道响应，展平为 (n_kernels, N·C)。"""
    cols = im2col(np.asarray(f0, dtype=np.float64)[None])[0]          # (N,7,C)
    ks = np.stack([np.asarray(k, dtype=np.float64) for k in kernels])  # (M,7)
    return np.einsum("nkc,mk->mnc", cols, ks).reshape(len(ks), -1)


def _pick(r: np.ndarray, at: np.ndarray, pool: List[int]) -> Optional[Dict]:
    rn2 = float(r @ r)
    best = None
    for ci in pool:
        a = at[ci]
        an2 = float(a @ a)
        if an2 < 1e-12:
            continue
        inner = abs(float(r @ a))
        gain = inner / np.sqrt(an2)
        if best is None or gain > best["gain"]:
            best = {"idx": ci, "gain": gain, "cos2": inner * inner / (rn2 * an2 + 1e-12)}
    return best


def _layer(flat0: np.ndarray, at: np.ndarray, sel: List[int], norm0: float, prev: float,
           names: Optional[Sequence[str]], cos2: float) -> Tuple[np.ndarray, Dict]:
    a_mat = at[sel].T
    coef = np.linalg.lstsq(a_mat, flat0, rcond=None)[0]       # SVD 最小二乘：残差与列空间正交到机器精度
    r = flat0 - a_mat @ coef
    rn = float(np.linalg.norm(r))
    rs = rn / norm0
    cum = 1.0 - rs ** 2
    # 残差为零向量（F₀ 落在已选原子张成空间内）时余弦无定义，正交性平凡成立 → 0
    ov = 0.0 if rn <= 1e-10 * norm0 else max(
        abs(float(r @ at[j])) / (rn * float(np.linalg.norm(at[j])) + 1e-12) for j in sel)
    return r, {"layer": len(sel) - 1, "kernel_idx": sel[-1], "name": kname(sel[-1], names),
               "coef": round(float(coef[-1]), 5), "cos2": round(cos2, 4), "explained_share": round(cum - prev, 4),
               "cumulative_share": round(cum, 4), "residual_share": round(rs, 4), "orthogonality_gain": round(ov, 6)}


def residual_pyramid(lattice: np.ndarray, kernels: Sequence[np.ndarray], dead_zone: float = DEAD_ZONE,
                     max_layers: int = MAX_LAYERS, tol: float = ORTHO_TOL, use_orthogonal_pool: bool = True,
                     names: Optional[Sequence[str]] = None) -> Dict:
    """正交残差金字塔（停因：card_exhausted / orthogonal_exhausted / dead_zone / max_layers）。"""
    t0 = time.time()
    f0 = np.asarray(lattice, dtype=np.float64)
    f0 = f0[0] if f0.ndim == 4 else f0
    flat0 = f0.ravel()
    norm0 = float(np.linalg.norm(flat0)) + 1e-12
    keep, rep = orthogonal_pool(kernels, tol, names) if use_orthogonal_pool else (list(range(len(kernels))), [])
    at = atoms(f0, kernels)
    pool, sel, layers, r, stop = list(keep), [], [], flat0.copy(), "max_layers"
    while True:
        if not pool:
            stop = "card_exhausted"
            break
        if len(layers) >= max_layers:
            break
        best = _pick(r, at, pool)
        if best is None:
            stop = "card_exhausted"
            break
        if best["cos2"] < tol:
            stop = "orthogonal_exhausted"
            break
        sel.append(best["idx"])
        r, lay = _layer(flat0, at, sel, norm0, layers[-1]["cumulative_share"] if layers else 0.0, names, best["cos2"])
        layers.append(lay)
        pool.remove(best["idx"])
        if lay["residual_share"] < dead_zone:
            stop = "dead_zone"
            break
    rs = float(np.linalg.norm(r)) / norm0
    return {"algo": "hex_ortho-ng", "layers": layers, "depth": len(layers), "stop_reason": stop,
            "energy_spectrum": [l["explained_share"] for l in layers], "residual_share": round(rs, 4),
            "cumulative_share": round(1.0 - rs ** 2, 4), "initial_energy": round(norm0, 4), "selected_kernels": sel,
            "orthogonality": {"pool_size": len(keep), "dropped": len(kernels) - len(keep), "tol": tol, "report": rep},
            "dead_zone": dead_zone, "max_layers": max_layers, "latency_ms": round((time.time() - t0) * 1000, 1)}


def pyramid_report(lattice: np.ndarray, kernels: Sequence[np.ndarray], **kw) -> Dict:
    """一行式摘要。"""
    r = residual_pyramid(lattice, kernels, **kw)
    return {"depth": r["depth"], "stop_reason": r["stop_reason"], "residual_share": r["residual_share"],
            "cumulative_share": r["cumulative_share"], "energy_spectrum": r["energy_spectrum"],
            "dropped_redundant": r["orthogonality"]["dropped"],
            "layers": [{"layer": l["layer"], "name": l["name"], "cos2": l["cos2"], "residual_share": l["residual_share"]}
                       for l in r["layers"]]}
