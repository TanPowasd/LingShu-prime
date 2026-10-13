# -*- coding: utf-8 -*-
"""verify · 构造性验证：一切读数来自成图像素（加噪前），不回显输入。

每个部件的读数（写进落格日志，``judge`` 只比对读数与描述）：
- ``painted_px``   可见像素数（= 本部件改动过、且未被更高层再改动的像素）；
- ``zone_landed``  可见像素质心所在 3×3 格（无可见像素 → None）；
- ``color_rgb``    可见像素在成图上的众数色；
- ``pattern_read`` 由可见像素的邻接结构读出：有水平相邻 → solid；否则有垂直相邻 → striped；
  否则（≥2 个孤立点）→ dotted；不足 2 像素 → None（读不出就不算兑现）；
- ``coverage``     描述应画的掩码（形状 × 尺寸档 × 花纹，在布局中心处由验证器自行栅格化）
  中，成图上确为描述色的比例；
- ``spill``        本部件改动的像素中落在应画掩码之外的比例。
兑现 = 可见 ∧ 落格一致 ∧ 众数色 = 描述色 ∧ 花纹读数一致 ∧ coverage ≥ 0.9 ∧ spill ≤ 0.1
∧ 形状在渲染器词表内。渲染器什么都不画、画错位置/颜色/花纹/形状/尺寸、被遮挡，都会失败（nn-04）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from ..nn.render import RENDERABLE, Footprint, part_mask

COVERAGE_MIN = 0.9
SPILL_MAX = 0.1


def read_pattern(mask: np.ndarray) -> Optional[str]:
    """可见像素的花纹读数（见模块说明）。"""
    if int(mask.sum()) < 2:
        return None
    if np.any(mask[:, 1:] & mask[:, :-1]):
        return "solid"
    if np.any(mask[1:] & mask[:-1]):
        return "striped"
    return "dotted"


def zone_of_mask(mask: np.ndarray) -> Optional[str]:
    """掩码质心所在格 r{row*3+col}（旧口径：int(均值)*3//边长）。"""
    if not mask.any():
        return None
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    return f"r{min(2, int(ys.mean()) * 3 // h) * 3 + min(2, int(xs.mean()) * 3 // w)}"


def mode_color(img: np.ndarray, mask: np.ndarray) -> Optional[tuple]:
    """掩码内的众数 RGB。"""
    if not mask.any():
        return None
    px = img[mask].reshape(-1, 3).astype(np.int64)
    key = (px[:, 0] << 16) | (px[:, 1] << 8) | px[:, 2]          # 打包成整数后计众数（并列取最小色，同旧 unique+argmax）
    vals, cnt = np.unique(key, return_counts=True)
    k = int(vals[cnt.argmax()])
    return (k >> 16) & 255, (k >> 8) & 255, k & 255


def expected_mask(shape: str, cx: int, cy: int, rad: int, pattern: str, h: int, w: int) -> Optional[np.ndarray]:
    """描述应画的掩码（形状不在词表内 → None）。"""
    if shape not in RENDERABLE:
        return None
    return part_mask(shape, cx, cy, rad, pattern, h, w)


def read_part(clean: np.ndarray, foot: Footprint, spec: Dict, cx: int, cy: int, rad: int,
              rgb: Sequence[int]) -> Dict:
    """单部件像素读数。spec 只用来栅格化「应画掩码」，读数本身全部来自 clean/foot。"""
    vis = foot.visible
    out = {"painted_px": int(vis.sum()), "zone_landed": zone_of_mask(vis),
           "color_rgb": mode_color(clean, vis), "pattern_read": read_pattern(vis),
           "coverage": 0.0, "spill": 1.0}
    h, w = clean.shape[:2]
    exp = expected_mask(spec["shape"], cx, cy, rad, spec.get("pattern", "solid"), h, w)
    if exp is not None:
        m = rad // 4 + 2                       # 应画掩码只在 [c±rad] 内（多边形留余量），计数在该窗内做
        ys, xs = slice(max(0, cy - rad - m), max(0, cy + rad + m + 1)), slice(max(0, cx - rad - m), max(0, cx + rad + m + 1))
        e = exp[ys, xs]
        n_exp = int(e.sum())
        if n_exp != int(exp.sum()):            # 防御：窗外仍有应画像素则退回全幅
            ys, xs, e, n_exp = slice(None), slice(None), exp, int(exp.sum())
        if n_exp:
            on = np.all(clean[ys, xs] == np.asarray(rgb, dtype=clean.dtype), axis=-1)
            out["coverage"] = round(float((e & on).sum() / n_exp), 4)
            ch = foot.changed
            n_ch = int(ch.sum())
            out["spill"] = round(float((n_ch - int((ch[ys, xs] & e).sum())) / max(1, n_ch)), 4) if n_ch else 1.0
    return out


def judge(spec: Dict, entry: Optional[Dict], rgb: Sequence[int]) -> bool:
    """读数 vs 描述。"""
    if entry is None:
        return False
    return bool(entry.get("painted_px", 0) > 0
                and entry.get("zone_landed") == spec["zone"]
                and entry.get("color_rgb") == tuple(rgb)
                and entry.get("pattern_read") == spec.get("pattern", "solid")
                and spec["shape"] in RENDERABLE
                and entry.get("coverage", 0.0) >= COVERAGE_MIN
                and entry.get("spill", 1.0) <= SPILL_MAX
                and entry.get("shape") == spec["shape"]
                and entry.get("size", "medium") == spec.get("size", "medium"))


def verify(parts: List[Dict], log: List[Dict], palette: Dict[str, tuple]) -> Dict:
    """条件兑现率：{rate, matched, total, misses}。"""
    matched, misses = 0, []
    for i, p in enumerate(parts):
        entry = next((e for e in log if e.get("part") == i), None)
        ok = judge(p, entry, palette.get(p["color"], (-1, -1, -1)))
        matched += int(ok)
        if not ok:
            misses.append({"part": i, "spec": p, "log": entry})
    return {"rate": round(matched / max(1, len(parts)), 4), "matched": matched, "total": len(parts),
            "misses": misses}
