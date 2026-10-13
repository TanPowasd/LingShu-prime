# -*- coding: utf-8 -*-
"""stcnn · 3D 时空卷积与时空原语（尺度无关）+ 时空记忆（时间锚点、写入日志自校验）。

- 体素：``frames_to_voxel`` min-max 归一化到 [0,1]；**所有**下游量（运动量、帧差掩码、
  质心轨迹、周期）都在归一化体素上算（NEW-nn-01：旧实现帧差在原始帧上用固定阈值）。
- 运动量：``motion_energy`` = 运动核响应的均值（与分辨率、帧数无关）；``moving`` 由
  「是否存在 >2 个变化像素的帧」判定，与帧差/轨迹同一口径，不再出现 moving=True 却静止。
- 时间锚点：``t_first/t_last`` = 运动实际发生的帧区间（闭区间，diffs[i] 是帧 i→i+1）；
  无运动取整段 ``[0, n−1]``。记忆事件区间 = ``t_start + [t_first, t_last]``（NEW-nn-03）。
- 记忆自校验：写入日志保存每条事件的快照与 sha256 摘要；``verify_consistency`` 逐条比对
  事件内容与摘要，并要求每条都能按自身回忆字段被召回（nn-08：旧实现恒真）。
- conv3d / max_pool3d：滑窗视图 + tensordot，无 Python 三重循环。
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Dict, List, Optional, Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

DIFF_THRESHOLD = 0.08
MIN_CHANGED_PX = 2
RECALL_KEYS = ("direction", "moving", "period", "label")

MOTION_KERNEL = np.zeros((2, 3, 3))
MOTION_KERNEL[1] = 1.0 / 9.0
MOTION_KERNEL[0] = -1.0 / 9.0
SPATIAL_KERNEL = np.full((1, 3, 3), 1.0 / 9.0)


def frames_to_voxel(frames, width: Optional[int] = None, height: Optional[int] = None) -> np.ndarray:
    """帧序列 (T,H,W[,C]) → 归一化体素 (T,H,W) float64 ∈ [0,1]（彩色先取通道均值）。"""
    arr = np.asarray(frames, dtype=np.float64)
    if arr.ndim == 4:
        arr = arr.mean(axis=-1)
    if width is not None or height is not None:
        arr = arr[:, :(height or arr.shape[1]), :(width or arr.shape[2])]
    lo, hi = float(arr.min()), float(arr.max())
    return (arr - lo) / (hi - lo) if hi > lo else arr - lo


def conv3d(voxel: np.ndarray, kernel: np.ndarray, stride: Tuple[int, int, int] = (1, 1, 1)) -> np.ndarray:
    """valid 3D 相关：(T,H,W) × (kt,kh,kw) → (ot,oh,ow)。"""
    win = sliding_window_view(np.asarray(voxel, dtype=np.float64), kernel.shape)
    win = win[::stride[0], ::stride[1], ::stride[2]]
    return np.tensordot(win, np.asarray(kernel, dtype=np.float64), axes=3)


def max_pool3d(feat: np.ndarray, size: Tuple[int, int, int] = (2, 2, 2)) -> np.ndarray:
    """不重叠 3D 最大池化（尾部不足一窗的部分丢弃）。"""
    kt, kh, kw = size
    t, h, w = (s // k for s, k in zip(feat.shape, size))
    v = feat[:t * kt, :h * kh, :w * kw].reshape(t, kt, h, kh, w, kw)
    return v.max(axis=(1, 3, 5))


def frame_diff(voxel: np.ndarray, threshold: float = DIFF_THRESHOLD) -> np.ndarray:
    """帧差掩码 (T−1,H,W)：|v(t+1)−v(t)| > threshold（输入应为归一化体素）。"""
    return (np.abs(np.diff(np.asarray(voxel, dtype=np.float64), axis=0)) > threshold).astype(np.float64)


def motion_direction(centroids: List[Tuple[float, float]]) -> str:
    """质心首末位移 → 主方向（向右/向左/向下/向上/静止）。"""
    if len(centroids) < 2:
        return "静止"
    dx = centroids[-1][0] - centroids[0][0]
    dy = centroids[-1][1] - centroids[0][1]
    if abs(dx) + abs(dy) < 1.0:
        return "静止"
    if abs(dx) >= abs(dy):
        return "向右" if dx > 0 else "向左"
    return "向下" if dy > 0 else "向上"


def motion_speed(centroids: List[Tuple[float, float]], frames_per_unit: float = 1.0) -> float:
    """平均每帧 L1 位移。"""
    if len(centroids) < 2:
        return 0.0
    c = np.asarray(centroids)
    return float(np.abs(np.diff(c, axis=0)).sum() / (len(c) - 1) / frames_per_unit)


def detect_period(signal, min_period: int = 2, floor: float = 0.05) -> Optional[int]:
    """前沿（低→高跳变）间隔的众数；间隔至少重复两次才算周期。"""
    sig = np.asarray(signal, dtype=np.float64)
    edges = [i for i in range(1, len(sig)) if sig[i] > floor and sig[i - 1] <= floor]
    if len(edges) < 2:
        return None
    period, count = Counter(np.diff(edges).tolist()).most_common(1)[0]
    return int(period) if count >= 2 and period >= min_period else None


def intensity_period(voxel: np.ndarray, min_period: int = 2) -> Optional[int]:
    """亮度周期：逐帧平均亮度按中值二值化后取前沿间隔众数（至少重复两次）。

    时隐时现（闪烁 / 周期遮挡）的事件周期就是可见性信号的周期；运动量信号在占空比 1/2 时
    「亮→灭」「灭→亮」两次跳变各产生一次运动，只能读出半周期。亮度近常数（纯平移）时返回 None。"""
    if voxel.shape[0] < 2 * min_period:
        return None
    sig = voxel.reshape(voxel.shape[0], -1).mean(axis=1).astype(np.float64)
    lo, hi = float(sig.min()), float(sig.max())
    if hi - lo < 1e-3:
        return None
    on = sig > (lo + hi) / 2
    edges = [i for i in range(1, len(on)) if on[i] and not on[i - 1]]
    if len(edges) < 2:
        return None
    period, count = Counter(np.diff(edges).tolist()).most_common(1)[0]
    return int(period) if count >= 2 and period >= min_period else None


def centroid_track(diffs: np.ndarray) -> List[Tuple[float, float]]:
    """逐帧差掩码质心（>2 像素才记；中间缺帧沿用上一点）。"""
    out: List[Tuple[float, float]] = []
    for region in diffs:
        ys, xs = np.nonzero(region)
        if len(xs) > MIN_CHANGED_PX:
            out.append((float(xs.mean()), float(ys.mean())))
        elif out:
            out.append(out[-1])
    return out


def extract_spatiotemporal_primitives(frames) -> Tuple[Dict, np.ndarray]:
    """时空原语（全部在归一化体素上）：运动量/方向/速度/周期/运动帧区间。"""
    voxel = frames_to_voxel(frames)
    feat = conv3d(voxel, MOTION_KERNEL)
    diffs = frame_diff(voxel)
    centroids = centroid_track(diffs)
    counts = diffs.reshape(len(diffs), -1).sum(axis=1)
    active = np.nonzero(counts > MIN_CHANGED_PX)[0]
    n = int(voxel.shape[0])
    t_first, t_last = (int(active[0]), int(active[-1]) + 1) if active.size else (0, max(0, n - 1))
    prims = {"motion_magnitude": round(float(np.abs(feat).sum()), 4),
             "motion_energy": round(float(np.abs(feat).mean()) if feat.size else 0.0, 6),
             "direction": motion_direction(centroids), "speed": round(motion_speed(centroids), 4),
             "period": _period(voxel, counts), "moving": bool(active.size > 0),
             "trajectory_len": len(centroids), "t_first": t_first, "t_last": t_last, "n_frames": n}
    return prims, feat


def _period(voxel: np.ndarray, counts: np.ndarray) -> Optional[int]:
    """周期：可见性（亮度）周期优先，其次运动量信号的前沿周期。"""
    p = intensity_period(voxel)
    return p if p is not None else detect_period(counts.tolist())


def event_digest(event: Dict) -> str:
    """事件内容的稳定 sha256（键排序 JSON；不依赖 PYTHONHASHSEED）。"""
    return hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False, default=str)
                          .encode("utf-8")).hexdigest()


class SpatiotemporalMemory:
    """时空记忆：事件 = 时间锚点 + 运动模式；写入日志 = 快照 + 摘要。"""

    def __init__(self) -> None:
        self.events: List[Dict] = []
        self._log: List[Tuple[Dict, str]] = []

    def remember(self, prims: Dict, label: str, t_start: int = 0) -> Dict:
        """写入一次「看见」：区间 = t_start + 运动帧区间（无区间键的旧原语按旧公式）。"""
        if "t_first" in prims:
            t0, t1 = t_start + int(prims["t_first"]), t_start + int(prims["t_last"])
        else:
            t0, t1 = t_start, t_start + max(1, prims.get("trajectory_len", 1) - 1)
        event = {"t_start": t0, "t_end": t1, "direction": prims.get("direction", "静止"),
                 "speed": prims.get("speed", 0.0), "period": prims.get("period"),
                 "moving": prims.get("moving", False), "label": label}
        self.events.append(event)
        self._log.append((dict(event), event_digest(event)))
        return event

    def recall(self, query: Optional[Dict] = None) -> List[Dict]:
        """按白名单字段（direction/moving/period/label）精确匹配召回；None 返回全部。"""
        if query is None:
            return list(self.events)
        q = {k: v for k, v in query.items() if k in RECALL_KEYS}
        return [e for e in self.events if all(e.get(k) == v for k, v in q.items())]

    def verify_consistency(self) -> bool:
        """事件与写入日志逐条一致（内容 + 摘要），且每条可按自身回忆字段召回。"""
        if len(self.events) != len(self._log):
            return False
        for e, (snap, dig) in zip(self.events, self._log):
            if e != snap or event_digest(e) != dig:
                return False
        return all(any(r is e for r in self.recall({k: e[k] for k in RECALL_KEYS})) for e in self.events)


def synth_ball_rolling(frames: int = 10, size: int = 32, start: int = 3, speed_px: int = 2,
                       period: Optional[int] = None) -> List[np.ndarray]:
    """合成：3×3 小球水平匀速右移（可选周期隐现）。"""
    out, row = [], size // 2
    for t in range(frames):
        f = np.zeros((size, size), dtype=np.float32)
        if period is None or (t % period) < period // 2:
            col = min(start + speed_px * t, size - 4)
            f[row:row + 3, col:col + 3] = 1.0
        out.append(f)
    return out


def synth_static(frames: int = 6, size: int = 32) -> List[np.ndarray]:
    """合成：静止场景。"""
    return [np.full((size, size), 0.5, dtype=np.float32) for _ in range(frames)]


def synth_blinking(frames: int = 12, size: int = 32, period: int = 3) -> List[np.ndarray]:
    """合成：全屏周期闪烁。"""
    return [np.full((size, size), 1.0 if (t % period) < period // 2 else 0.0, dtype=np.float32)
            for t in range(frames)]
