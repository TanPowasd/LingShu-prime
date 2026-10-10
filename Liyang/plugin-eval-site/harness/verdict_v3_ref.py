"""verdict_v3 的独立参考实现（验证计划 v0 门槛 1 的对照）。

刻意与主实现走不同代码路径：
- 题目分→场景差：用 numpy 数组与 np.bincount 聚合，而不是逐 pair 字典累加；
- RNG：SplitMix64 向量化（一次生成 B·G 个 uint64，状态 = seed + k·γ 直接计算，不迭代）；
- 统计量：重抽下标矩阵 (B,G) → 每行 Σw·d / Σw；
- 百分位：numpy.percentile(method="linear")；
- 五状态：按"先排除精度、再按区间位置查表"的写法独立重写。
冻结规格（RNG、下标映射、抽取顺序、聚合顺序、百分位）与 verdict_v3 文档一致；只共享规格，不共享代码。
"""
from __future__ import annotations

import hashlib
import math

import numpy as np

DEF = dict(a=5.0, b=5.0, max_half_width=5.0, B=10000, conf=0.95, min_scenarios=8, min_reruns=3)


def seed_of(analysis_id: str) -> int:
    h = hashlib.sha256(analysis_id.encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def splitmix_block(seed: int, count: int) -> np.ndarray:
    with np.errstate(over="ignore"):
        k = np.arange(1, count + 1, dtype=np.uint64)
        z = np.uint64(seed) + k * np.uint64(0x9E3779B97F4A7C15)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        z = z ^ (z >> np.uint64(31))
    return z


def boot_interval(d: np.ndarray, w: np.ndarray, B: int, seed: int, conf: float):
    G = d.shape[0]
    x = splitmix_block(seed, B * G)
    idx = np.floor((x >> np.uint64(11)).astype(np.float64) * (2.0 ** -53) * G).astype(np.int64).reshape(B, G)
    stat = (w[idx] * d[idx]).sum(axis=1) / w[idx].sum(axis=1)
    lo, hi = np.percentile(stat, [100 * (1 - conf) / 2, 100 * (1 + conf) / 2], method="linear")
    return float(lo), float(hi)


def scenario_arrays(spec: dict):
    """返回 (sids, d, w, base, plug, reruns) 或抛 ValueError(code)。"""
    kind = spec.get("metric", {}).get("kind", "continuous")
    smax = float(spec.get("metric", {}).get("scale_max", 1.0))
    W = spec["weights"]
    rows = [p for p in spec.get("pairs", []) if p.get("valid") is True]
    if not rows:
        raise ValueError("NO_VALID_PAIRS")
    sids = sorted({p["scenario_id"] for p in rows}, key=str)
    pos = {s: i for i, s in enumerate(sids)}
    sidx, dd, bb, pp, iw = [], [], [], [], {}
    for p in rows:
        items = sorted(p["base"])
        if p.get("plug") is None or sorted(p["plug"]) != items:
            raise ValueError("ITEM_MISMATCH")
        wv = np.array([W[q] for q in items], dtype=np.float64)
        bv = np.array([p["base"][q] for q in items], dtype=np.float64)
        pv = np.array([p["plug"][q] for q in items], dtype=np.float64)
        div = 1.0 if kind == "binary" else smax
        sb = 100.0 * float(np.dot(wv, bv / div)) / float(wv.sum())
        sp = 100.0 * float(np.dot(wv, pv / div)) / float(wv.sum())
        sidx.append(pos[p["scenario_id"]]); dd.append(sp - sb); bb.append(sb); pp.append(sp)
        iw[p["scenario_id"]] = float(wv.sum())
    sidx = np.array(sidx)
    n = np.bincount(sidx, minlength=len(sids)).astype(np.float64)
    d = np.bincount(sidx, weights=np.array(dd), minlength=len(sids)) / n
    base = np.bincount(sidx, weights=np.array(bb), minlength=len(sids)) / n
    plug = np.bincount(sidx, weights=np.array(pp), minlength=len(sids)) / n
    if spec.get("scenario_weighting", "equal") == "equal":
        w = np.ones(len(sids))
    else:
        w = np.array([iw[s] for s in sids])
    return sids, d, w, base, plug, n.astype(int)


def five_state(L, U, a, b, hw_max):
    if any(isinstance(v, float) and math.isnan(v) for v in (L, U)) or L > U:
        raise ValueError("BAD_INTERVAL")
    if (U - L) / 2 > hw_max:
        return "❓"
    table = [("✅", L > a), ("❌", U < -b), ("➖", (L > -b) and (U < a))]
    for st, cond in table:
        if cond:
            return st
    return "❓"


def ref_analyze(spec: dict) -> dict:
    """只覆盖主实现的数值核心与五状态映射（有效输入）。返回与 verdict_v3.normalize 可比的字段。"""
    p = {**DEF, **(spec.get("params") or {})}
    sids, d, w, base, plug, n = scenario_arrays(spec)
    L, U = boot_interval(d, w, p["B"], seed_of(spec["analysis_id"]), p["conf"])
    est = float((w * d).sum() / w.sum())
    if len(sids) < p["min_scenarios"] or n.min() < p["min_reruns"]:
        obs = "❓"
    else:
        obs = five_state(L, U, p["a"], p["b"], p["max_half_width"])
    return {"estimate": est, "interval": [L, U], "half_width": (U - L) / 2, "capability_observed": obs,
            "n_scenarios": len(sids), "reruns_per_scenario": int(n.min()),
            "base_abs": float((w * base).sum() / w.sum()), "plug_abs": float((w * plug).sum() / w.sum()),
            "numpy": np.__version__}
