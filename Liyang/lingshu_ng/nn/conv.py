# -*- coding: utf-8 -*-
"""conv · 蜂窝 6 邻卷积：im2col（预计算邻接下标表）+ 单次 GEMM。

- 核：7 参数 ``[自身, W, E, 左上, 右上, 左下, 右下]``（邻序见 :mod:`hexgrid`）。
- 边界：出界邻的存储坐标逐轴钳制到晶格内（= 旧实现 edge-replicate 填充的精确语义）。
- 全卷积：``x (B,R,C,Cin)`` × ``W (Cout,Cin,7)`` → ``(B,R,C,Cout)``，
  所有输出核一次 ``(B·R·C, 7·Cin) @ (7·Cin, Cout)``——取代旧实现「逐核 Python 循环 +
  奇偶行 mask 混合」（PR #97 的融合思路，但下标表在晶格层一次算好，不复制旧的
  ``e + mask·(o−e)`` 浮点路径，奇数行直接取奇数行邻居）。
- ``hex_conv_naive``：逐 cell 逐邻的参考实现，供逐位/1e-12 等价测试。
- ``hex_conv_backward``：对输入与核的解析梯度（同一下标表 scatter-add）。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Tuple

import numpy as np

from .hexgrid import EVEN_OFFSETS, ODD_OFFSETS


@lru_cache(maxsize=64)
def neighbor_index(rows: int, cols: int) -> np.ndarray:
    """(rows·cols, 7) int64 扁平下标表：第 0 列自身，1..6 列六邻（钳制边界）。只读。"""
    rr, cc = np.mgrid[0:rows, 0:cols]
    odd = (rr & 1).astype(bool)
    out = np.empty((rows, cols, 7), dtype=np.int64)
    out[..., 0] = rr * cols + cc
    for k in range(6):
        de, dre = EVEN_OFFSETS[k]
        do, dro = ODD_OFFSETS[k]
        dc = np.where(odd, do, de)
        dr = np.where(odd, dro, dre)
        nr = np.clip(rr + dr, 0, rows - 1)
        nc = np.clip(cc + dc, 0, cols - 1)
        out[..., k + 1] = nr * cols + nc
    table = out.reshape(rows * cols, 7)
    table.setflags(write=False)
    return table


def _as4(x: np.ndarray) -> Tuple[np.ndarray, bool]:
    x = np.asarray(x)
    if x.ndim == 3:
        return x[None], True
    if x.ndim != 4:
        raise ValueError(f"期望 (R,C,Cin) 或 (B,R,C,Cin)，得到 {x.shape}")
    return x, False


def im2col(x: np.ndarray) -> np.ndarray:
    """(B,R,C,Cin) → (B, R·C, 7, Cin) 邻域展开。"""
    b, r, c, ch = x.shape
    return x.reshape(b, r * c, ch)[:, neighbor_index(r, c)]


def weights_matrix(w: np.ndarray) -> np.ndarray:
    """核 (Cout,Cin,7) → GEMM 右矩阵 (7·Cin, Cout)，行序与 im2col 展平 (k, cin) 一致。"""
    w = np.asarray(w, dtype=np.float64)
    return np.ascontiguousarray(w.transpose(2, 1, 0).reshape(w.shape[2] * w.shape[1], w.shape[0]))


def hex_conv(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """全连接蜂窝卷积（float64）。x: (B,R,C,Cin) 或 (R,C,Cin)；w: (Cout,Cin,7)。"""
    x4, squeeze = _as4(x)
    w = np.asarray(w, dtype=np.float64)
    if w.ndim != 3 or w.shape[1] != x4.shape[3] or w.shape[2] != 7:
        raise ValueError(f"核形状 {w.shape} 与输入通道 {x4.shape[3]} 不符（期望 (Cout,Cin,7)）")
    b, r, c, ch = x4.shape
    cols = im2col(x4.astype(np.float64, copy=False)).reshape(b * r * c, 7 * ch)
    out = (cols @ weights_matrix(w)).reshape(b, r, c, w.shape[0])
    return out[0] if squeeze else out


def hex_conv_depthwise(x: np.ndarray, k: np.ndarray) -> np.ndarray:
    """逐通道卷积：k 为 (7,)（各通道共享）或 (Cin,7)。输出通道数 = Cin。"""
    x4, squeeze = _as4(x)
    kk = np.asarray(k, dtype=np.float64)
    if kk.ndim == 1:
        kk = np.tile(kk, (x4.shape[3], 1))
    cols = im2col(x4.astype(np.float64, copy=False))          # (B,N,7,C)
    out = np.einsum("bnkc,ck->bnc", cols, kk, optimize=True)
    out = out.reshape(x4.shape)
    return out[0] if squeeze else out


def hex_conv_naive(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """参考实现：逐样本、逐 cell、逐邻、逐通道显式累加（慢，仅测试用）。"""
    x4, squeeze = _as4(x)
    w = np.asarray(w, dtype=np.float64)
    b, rows, cols, ch = x4.shape
    out = np.zeros((b, rows, cols, w.shape[0]), dtype=np.float64)
    for bi in range(b):
        for r in range(rows):
            offs = ODD_OFFSETS if r & 1 else EVEN_OFFSETS
            for c in range(cols):
                cells = [(r, c)] + [(min(max(r + dr, 0), rows - 1), min(max(c + dc, 0), cols - 1))
                                    for dc, dr in offs]
                for o in range(w.shape[0]):
                    acc = 0.0
                    for k, (nr, nc) in enumerate(cells):
                        for i in range(ch):
                            acc += w[o, i, k] * float(x4[bi, nr, nc, i])
                    out[bi, r, c, o] = acc
    return out[0] if squeeze else out


def hex_conv_backward(x: np.ndarray, w: np.ndarray, grad_out: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """解析梯度：返回 (dL/dx 与 x 同形, dL/dw 与 w 同形)。"""
    x4, squeeze = _as4(x)
    g4, _ = _as4(grad_out)
    w = np.asarray(w, dtype=np.float64)
    b, r, c, ch = x4.shape
    cout = w.shape[0]
    cols = im2col(x4.astype(np.float64, copy=False)).reshape(b * r * c, 7 * ch)
    g = g4.reshape(b * r * c, cout).astype(np.float64, copy=False)
    gw = (cols.T @ g).reshape(7, ch, cout).transpose(2, 1, 0)
    gcols = (g @ weights_matrix(w).T).reshape(b, r * c, 7, ch)
    idx = neighbor_index(r, c)
    gx = np.zeros((b, r * c, ch), dtype=np.float64)
    for k in range(7):
        np.add.at(gx, (slice(None), idx[:, k]), gcols[:, :, k, :])
    gx = gx.reshape(b, r, c, ch)
    return (gx[0] if squeeze else gx), np.ascontiguousarray(gw)


def kernel_smooth() -> np.ndarray:
    """各向同性平滑：7 点均匀。"""
    return np.full(7, 1.0 / 7.0)


def kernel_edge(vertical: bool = True) -> np.ndarray:
    """方向边缘：vertical=True 为左右差（W−E 方向），否则上下差。"""
    if vertical:
        return np.array([0.0, -1, 0, 0, 1, 0, 0])
    return np.array([0.0, 0, -1, -1, 0, 1, 1]) / 2.0


def kernel_laplacian() -> np.ndarray:
    """蜂窝离散 Laplacian：邻均值 − 自身（常数场零响应）。"""
    return np.array([-1.0] + [1.0 / 6.0] * 6)


def kernel_center_surround() -> np.ndarray:
    """中心-周围拮抗（= −Laplacian）。"""
    return np.array([1.0] + [-1.0 / 6.0] * 6)


def prior_family(n: int) -> list:
    """n 个互异白箱先验核：六方向 edge + smooth + 粗平滑 + laplacian + center-surround + 微噪变体。"""
    fam = []
    for d in range(6):
        k = np.zeros(7)
        k[1 + d] = -1.0
        k[1 + (d + 3) % 6] = 1.0
        fam.append(k)
    coarse = np.array([1.0] + [1.5] * 6)
    fam += [kernel_smooth(), coarse / coarse.sum(), kernel_laplacian(), kernel_center_surround()]
    i = 0
    while len(fam) < n:
        base = fam[i % 10].copy() + (i + 1) * 1e-3
        fam.append(base / (np.abs(base).sum() + 1e-9))
        i += 1
    return fam[:n]
