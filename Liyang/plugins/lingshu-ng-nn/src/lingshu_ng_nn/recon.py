# -*- coding: utf-8 -*-
"""recon · 单图「区域 → 关系连接 → 复原」，层序（z）显式写进描述。

- ``extract_regions``：按扫描序取种子、4 邻洪泛，色差 ``Σ|Δ| ≤ 3·th`` 相对种子色（旧语义），
  小于 4 像素的碎屑不入列。
- ``regions_to_connections``：每条连接带 ``z`` = 包围盒严格包含它的区域数（包含深度）。
  bbox A ⊂ B ⇒ z(A) > z(B)，所以容器/背景一定在被包含者之下——层序是描述的一部分，
  不再依赖扫描序（nn-05：占住 (0,0) 的物体先于背景入列，被背景整幅 bbox 盖掉）。
- ``reconstruct``：按 ``(z, −面积, id)`` 排序绘制——与连接列表的排列无关；
  旧描述（无 z）由包围盒现场推出同一层序。
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Sequence, Tuple

import numpy as np


def _flood(img: np.ndarray, sy: int, sx: int, th3: int, visited: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    seed = img[sy, sx].astype(np.int64)
    close = np.abs(img.astype(np.int64) - seed).sum(axis=-1) <= th3
    mask = np.zeros((h, w), dtype=bool)
    q = deque([(sy, sx)])
    visited[sy, sx] = mask[sy, sx] = True
    while q:
        y, x = q.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and close[ny, nx]:
                visited[ny, nx] = mask[ny, nx] = True
                q.append((ny, nx))
    return mask


def extract_regions(img: np.ndarray, color_th: int = 30) -> Tuple[List[Dict], np.ndarray]:
    """均匀色块连通域（扫描序种子）。返回 (区域列表, 残差图)。"""
    arr = np.asarray(img)
    h, w = arr.shape[:2]
    visited = np.zeros((h, w), dtype=bool)
    residual = arr.astype(np.int16).copy()
    regions = []
    for yy in range(h):
        for xx in np.nonzero(~visited[yy])[0]:
            if visited[yy, xx]:
                continue
            mask = _flood(arr, yy, int(xx), color_th * 3, visited)
            n = int(mask.sum())
            if n < 4:
                continue
            ys, xs = np.nonzero(mask)
            color = arr[mask].mean(axis=0).astype(np.uint8)
            regions.append({"bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                            "color": [int(c) for c in color], "pixels": n, "mask_indices": (ys, xs)})
            residual[mask] -= color.astype(np.int16)
    return regions, residual.clip(0, 255).astype(np.uint8)


def containment_depth(bboxes: Sequence[Sequence[int]]) -> List[int]:
    """每个包围盒被多少个（不同的）包围盒包含；相同包围盒按序号先后视为外层在先。"""
    out = []
    for i, (x0, y0, x1, y1) in enumerate(bboxes):
        d = 0
        for j, (a0, b0, a1, b1) in enumerate(bboxes):
            if j == i or not (a0 <= x0 and b0 <= y0 and a1 >= x1 and b1 >= y1):
                continue
            same = (a0, b0, a1, b1) == (x0, y0, x1, y1)
            d += int(not same or j < i)
        out.append(d)
    return out


def _rel(cx: float, cy: float, px: float, py: float) -> str:
    if cx > px:
        return "right_of"
    if cx < px:
        return "left_of"
    return "below" if cy > py else "above"


def regions_to_connections(regions: List[Dict], img_shape: Tuple[int, ...]) -> Dict:
    """区域 → 关系连接描述（JSON 可存；含显式 z 与像素级包围盒）。"""
    h, w = img_shape[:2]
    depth = containment_depth([r["bbox"] for r in regions])
    conns = []
    for i, r in enumerate(regions):
        x0, y0, x1, y1 = r["bbox"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        conn = {"id": i, "type": "region", "color": r["color"], "z": depth[i], "bbox": [x0, y0, x1, y1],
                "center": [round(cx / w, 4), round(cy / h, 4)],
                "size": [round((x1 - x0 + 1) / w, 4), round((y1 - y0 + 1) / h, 4)], "pixels": r["pixels"]}
        if i > 0:
            pb = regions[i - 1]["bbox"]
            conn["rel_prev"] = _rel(cx, cy, (pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2)
        conns.append(conn)
    return {"image_size": [w, h], "n_regions": len(regions), "connections": conns}


def _conn_box(conn: Dict, w: int, h: int) -> Tuple[int, int, int, int]:
    if "bbox" in conn:
        x0, y0, x1, y1 = conn["bbox"]
        return x0, y0, x1 + 1, y1 + 1
    cx, cy = int(conn["center"][0] * w), int(conn["center"][1] * h)
    sw, sh = int(conn["size"][0] * w), int(conn["size"][1] * h)
    return max(0, cx - sw // 2), max(0, cy - sh // 2), min(w, cx + sw // 2 + 1), min(h, cy + sh // 2 + 1)


def draw_order(connections: Dict) -> List[Dict]:
    """绘制顺序：(z, −面积, id)；缺 z 的旧描述按包围盒包含深度补出。"""
    w, h = connections["image_size"]
    conns = list(connections["connections"])
    boxes = [_conn_box(c, w, h) for c in conns]
    ids = [c.get("id", 0) for c in conns]
    if any("z" not in c for c in conns):
        order = sorted(range(len(conns)), key=lambda i: ids[i])
        dep = containment_depth([boxes[i] for i in order])
        zs = {order[k]: dep[k] for k in range(len(order))}
    else:
        zs = {i: c["z"] for i, c in enumerate(conns)}
    area = [(b[2] - b[0]) * (b[3] - b[1]) for b in boxes]
    return [conns[i] for i in sorted(range(len(conns)), key=lambda i: (zs[i], -area[i], ids[i]))]


def reconstruct(connections: Dict, background: int = 128) -> np.ndarray:
    """关系连接描述 → 图像（包围盒实心填色，层序见 draw_order）。"""
    w, h = connections["image_size"]
    img = np.full((h, w, 3), background, dtype=np.uint8)
    for conn in draw_order(connections):
        x0, y0, x1, y1 = _conn_box(conn, w, h)
        img[y0:y1, x0:x1] = tuple(conn["color"])
    return img


def pixel_accuracy(original: np.ndarray, recon: np.ndarray, th: int = 8) -> float:
    """逐像素匹配率：RGB 差总和 ≤ th 的像素占比。"""
    diff = np.abs(original.astype(int) - recon.astype(int)).sum(axis=-1)
    return float((diff <= th).mean())


def psnr(original: np.ndarray, recon: np.ndarray) -> float:
    """峰值信噪比（dB），完全一致返回 100。"""
    mse = float(((original.astype(float) - recon.astype(float)) ** 2).mean())
    return 100.0 if mse == 0 else float(10 * np.log10(255 ** 2 / mse))
