# -*- coding: utf-8 -*-
"""net · 蜂窝网络：参数仓（原子更新）+ 层算子（前向/解析反向）+ 两种拓扑。

- :class:`ParamStore`：全部参数平铺在一条连续向量里，按名字取视图；所有读写在实例锁内。
  ``get_vec/set_vec`` 是快照式（拷贝），读改写请用 ``update_vec(fn)`` / ``apply_delta``
  ——在锁内完成（#197：旧实现 get/set 两次独立调用，并发下丢更新）。
- 确定性：构造只接受显式 ``rng``（``np.random.Generator`` 或整数种子），模块内无全局随机源。
- 拓扑：
  * :class:`ShallowHexNet`（旧 HexNet / M2）：conv(K) → lrelu → mix(M×K) → lrelu → RMS → fc(C×M)
  * :class:`HierHexNet`（旧 HexHierNet / M3–M4.2）：conv1(K1, RGB 共享核) → lrelu
    →[stacked] conv2(K2×K1) → lrelu → RMS →[deep_norm/amp] ⊕ 均值色(3) → head(9×·)
  两者都有 ``forward_cache``（保留中间量）与 ``backward``（解析梯度，与有限差分逐项对照测试）。
  ``perturbed_logits`` 利用卷积对核参数的线性性，只重算受单个参数影响的通道
  （有限差分训练的增量求值；与整网重算 1e-12 一致）。
"""
from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from .conv import hex_conv, hex_conv_backward, im2col, kernel_smooth, prior_family

RngLike = Union[int, np.random.Generator]
LRELU_A = 0.05
LN2 = 0.6931471805599453
LEGACY_KERNELS = ("smooth", "edge_v", "edge_h", "laplacian", "center_surround")


def as_rng(rng: RngLike) -> np.random.Generator:
    """整数种子或 Generator → Generator（不接受 None：随机源必须显式注入）。"""
    if isinstance(rng, np.random.Generator):
        return rng
    if isinstance(rng, (int, np.integer)):
        return np.random.default_rng(int(rng))
    raise TypeError("rng 必须是 int 种子或 np.random.Generator")


def legacy_kernel(name: str) -> np.ndarray:
    """旧 DEFAULT_KERNELS 的同名核（float32 值，float64 存储——与旧数值逐位一致）。"""
    from .conv import kernel_center_surround, kernel_edge, kernel_laplacian
    table = {"smooth": kernel_smooth, "edge_v": lambda: kernel_edge(True),
             "edge_h": lambda: kernel_edge(False), "laplacian": kernel_laplacian,
             "center_surround": kernel_center_surround}
    return table[name]().astype(np.float32).astype(np.float64)


class ParamStore:
    """命名参数的连续向量仓；线程安全的快照读、整体写、锁内读改写。"""

    def __init__(self, arrays: Sequence[Tuple[str, np.ndarray]]):
        self._lock = threading.RLock()
        self._layout: List[Tuple[str, Tuple[int, ...], int, int]] = []
        self._vec = np.zeros(0)
        self.rebuild(arrays)

    def rebuild(self, arrays: Sequence[Tuple[str, np.ndarray]]) -> None:
        """按新的 (名字, 数组) 序列重排（生长/撤销用）。"""
        with self._lock:
            layout, chunks, i = [], [], 0
            for name, arr in arrays:
                a = np.asarray(arr, dtype=np.float64)
                layout.append((name, a.shape, i, i + a.size))
                chunks.append(a.ravel())
                i += a.size
            self._layout = layout
            self._vec = np.concatenate(chunks) if chunks else np.zeros(0)

    def __getstate__(self) -> dict:
        """pickle/deepcopy：锁不参与复制（旧 AtomicVecMixin 口径，#197）。"""
        with self._lock:
            st = dict(self.__dict__)
            st["_vec"] = self._vec.copy()
        st.pop("_lock", None)
        return st

    def __setstate__(self, st: dict) -> None:
        """恢复后每实例新建一把锁。"""
        self.__dict__.update(st)
        self._lock = threading.RLock()

    @property
    def size(self) -> int:
        """参数总数。"""
        return int(self._vec.size)

    def names(self) -> List[str]:
        """参数名（平铺顺序）。"""
        return [n for n, _, _, _ in self._layout]

    def slice_of(self, name: str) -> Tuple[int, int]:
        """参数在平铺向量中的 [起, 止)。"""
        for n, _, a, b in self._layout:
            if n == name:
                return a, b
        raise KeyError(name)

    def view(self, name: str) -> np.ndarray:
        """只读视图（不拷贝）；需要可写请走 update_vec。"""
        for n, shape, a, b in self._layout:
            if n == name:
                v = self._vec[a:b].reshape(shape)
                v.flags.writeable = False
                return v
        raise KeyError(name)

    def live(self, name: str) -> np.ndarray:
        """可写视图（旧网络属性口径：``net.head[1, -1] = 8`` 原地改当前参数）。下一次整体写入
        （set_vec/update_vec/apply_delta 都换新向量）后该视图即成旧值快照，与旧版属性被重新赋值同语义。"""
        for n, shape, a, b in self._layout:
            if n == name:
                return self._vec[a:b].reshape(shape)
        raise KeyError(name)

    def get_vec(self) -> np.ndarray:
        """快照（拷贝）。"""
        with self._lock:
            return self._vec.copy()

    def set_vec(self, vec: np.ndarray) -> None:
        """整体写入（长度必须一致、全部有限）。"""
        v = np.asarray(vec, dtype=np.float64).ravel()
        if v.size != self._vec.size:
            raise ValueError(f"参数向量长度 {v.size} ≠ {self._vec.size}")
        if not np.all(np.isfinite(v)):
            raise ValueError("参数向量含非有限值")
        with self._lock:
            self._vec = v.copy()

    def update_vec(self, fn: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
        """锁内读改写：``fn(当前快照) → 新向量``，返回写入后的快照。"""
        with self._lock:
            self.set_vec(fn(self._vec.copy()))
            return self._vec.copy()

    def apply_delta(self, idx: Union[int, Sequence[int], np.ndarray], delta: Union[float, np.ndarray]) -> None:
        """锁内原子增量：``vec[idx] += delta``（重复下标累加）。"""
        with self._lock:
            v = self._vec.copy()
            np.add.at(v, np.asarray(idx, dtype=np.int64), delta)
            self.set_vec(v)


# ==================== 算子 ====================

def lrelu(v: np.ndarray, a: float = LRELU_A) -> np.ndarray:
    """leaky ReLU。"""
    return np.where(v > 0, v, a * v)


def lrelu_grad(v: np.ndarray, a: float = LRELU_A) -> np.ndarray:
    """leaky ReLU 导数（v>0 → 1，否则 a）。"""
    return np.where(v > 0, 1.0, a)


def rms_pool(h: np.ndarray) -> np.ndarray:
    """(B,R,C,K) → (B,K) 空间 RMS 能量池化。"""
    return np.sqrt((h ** 2).mean(axis=(1, 2)) + 1e-12)


def rms_pool_backward(h: np.ndarray, pooled: np.ndarray, g: np.ndarray) -> np.ndarray:
    """RMS 池化的反向：dL/dh = g·h / (N·pooled)。"""
    n = h.shape[1] * h.shape[2]
    return h * (g / (n * pooled))[:, None, None, :]


def softmax(z: np.ndarray) -> np.ndarray:
    """稳定 softmax（最后一维）。"""
    zz = z - z.max(axis=-1, keepdims=True)
    e = np.exp(zz)
    return e / e.sum(axis=-1, keepdims=True)


def tied_full(w: np.ndarray, cin: int) -> np.ndarray:
    """共享核 (K,7) → 全卷积核 (K,cin,7)（每个输入通道同一核，输出跨通道求和）。"""
    return np.repeat(np.asarray(w, dtype=np.float64)[:, None, :], cin, axis=1)


def delta_conv(x: np.ndarray, w_out: np.ndarray) -> np.ndarray:
    """单输入通道增量卷积：x (B,R,C) × w_out (Cout,7) → (B,R,C,Cout)。"""
    return hex_conv(x[..., None], np.asarray(w_out)[:, None, :])


def ce_from_logits(logits: np.ndarray, y: np.ndarray) -> float:
    """交叉熵（稳定 log-softmax）。"""
    z = logits - logits.max(axis=1, keepdims=True)
    logp = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
    return float(-logp[np.arange(len(y)), y].mean())


# ==================== 拓扑一：浅层网络（旧 HexNet） ====================

class ShallowHexNet:
    """conv(K 核, 灰度) → lrelu → mix(M×K) → lrelu → RMS → fc(C×M)。参数平铺 conv|mix|fc。"""

    def __init__(self, n_kernels: int = 4, n_mix: int = 8, n_class: int = 10, rng: RngLike = 7):
        g = as_rng(rng)
        conv = np.stack([legacy_kernel(LEGACY_KERNELS[i % 5]) for i in range(n_kernels)])
        mix = g.normal(0, 0.3, (n_mix, n_kernels))
        fc = g.normal(0, 0.3, (n_class, n_mix))
        self.params = ParamStore([("conv", conv), ("mix", mix), ("fc", fc)])

    @property
    def K(self) -> int:
        """卷积核数。"""
        return self.params.view("conv").shape[0]

    @property
    def M(self) -> int:
        """混合层宽度。"""
        return self.params.view("mix").shape[0]

    @property
    def C(self) -> int:
        """类别数。"""
        return self.params.view("fc").shape[0]

    def forward_cache(self, x: np.ndarray) -> Dict[str, np.ndarray]:
        """前向并保留中间量。x: (B,R,C,≥1)，只用第 0 通道（旧语义）。"""
        p = self.params
        x1 = np.asarray(x, dtype=np.float64)[..., :1]
        pre1 = hex_conv(x1, p.view("conv")[:, None, :])
        h1 = lrelu(pre1)
        pre2 = h1 @ p.view("mix").T
        h2 = lrelu(pre2)
        pooled = rms_pool(h2)
        return {"x": x1, "pre1": pre1, "h1": h1, "pre2": pre2, "h2": h2, "pooled": pooled,
                "logits": pooled @ p.view("fc").T}

    def forward(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """→ (logits (B,C), pooled (B,M))。"""
        c = self.forward_cache(x)
        return c["logits"], c["pooled"]

    def backward(self, cache: Dict[str, np.ndarray], dlogits: np.ndarray) -> np.ndarray:
        """解析梯度（平铺顺序同 get_vec）。"""
        p = self.params
        g_fc = dlogits.T @ cache["pooled"]
        g_pool = dlogits @ p.view("fc")
        g_h2 = rms_pool_backward(cache["h2"], cache["pooled"], g_pool)
        g_pre2 = g_h2 * lrelu_grad(cache["pre2"])
        g_mix = np.einsum("brcm,brck->mk", g_pre2, cache["h1"])
        g_pre1 = (g_pre2 @ p.view("mix")) * lrelu_grad(cache["pre1"])
        _, g_conv = hex_conv_backward(cache["x"], p.view("conv")[:, None, :], g_pre1)
        return np.concatenate([g_conv[:, 0, :].ravel(), g_mix.ravel(), g_fc.ravel()])

    def grow_kernel(self) -> None:
        """+1 核（手写核族轮转初始化，mix 新列置零——不改变当前输出）。"""
        p = self.params
        conv = np.vstack([p.view("conv"), legacy_kernel(LEGACY_KERNELS[self.K % 5])[None]])
        mix = np.hstack([p.view("mix"), np.zeros((self.M, 1))])
        p.rebuild([("conv", conv), ("mix", mix), ("fc", p.view("fc").copy())])


# ==================== 拓扑二：层级网络（旧 HexHierNet） ====================

def _hier_init(n1: int, n2: int, g: np.random.Generator, stacked: bool, conv2_mode: str,
               prior: str) -> List[Tuple[str, np.ndarray]]:
    if prior == "extended":
        conv = np.stack([k.astype(np.float32).astype(np.float64) for k in prior_family(n1)])
    else:
        conv = np.stack([legacy_kernel(LEGACY_KERNELS[i % 5]) for i in range(n1)])
    out = [("conv", conv)]
    if stacked:
        if conv2_mode == "asym":
            fam = ([k.astype(np.float32).astype(np.float64) for k in prior_family(n2)]
                   if prior == "extended" else
                   [legacy_kernel(LEGACY_KERNELS[(k + 1) % 5]) for k in range(n2)])
            conv2 = np.stack([np.tile(fam[k], (n1, 1)) + g.normal(0, 0.02, (n1, 7)) for k in range(n2)])
        else:
            conv2 = np.tile(legacy_kernel("smooth"), (n2, n1, 1)) + g.normal(0, 0.02, (n2, n1, 7))
        out.append(("conv2", conv2))
    return out


class HierHexNet:
    """L1 共享核 conv → [L1.5 conv2] → RMS → [方向/幅度分离] ⊕ 均值色 → L3 head(9)。"""

    def __init__(self, n_kernels: int = 6, n_kernels2: int = 6, rng: RngLike = 7, stacked: bool = True,
                 conv2_mode: str = "sym", head_scale: float = 0.3, deep_norm: bool = False,
                 amp_sep: bool = False, amp_log: bool = False, prior: str = "legacy", n_out: int = 9):
        g = as_rng(rng)
        self.stacked, self.deep_norm, self.amp_sep, self.amp_log = stacked, deep_norm, amp_sep, amp_log
        arrays = _hier_init(n_kernels, n_kernels2, g, stacked, conv2_mode, prior)
        head_in = (n_kernels2 if stacked else n_kernels) + 3 + int(deep_norm and amp_sep)
        arrays.append(("head", g.normal(0, head_scale, (n_out, head_in))))
        self.params = ParamStore(arrays)

    @property
    def K(self) -> int:
        """L1 核数。"""
        return self.params.view("conv").shape[0]

    @property
    def K2(self) -> int:
        """L1.5 核数（非堆叠为 0）。"""
        return self.params.view("conv2").shape[0] if self.stacked else 0

    def _pool_feat(self, deep: np.ndarray) -> Dict[str, np.ndarray]:
        out = {"deep": deep}
        if not self.deep_norm:
            out["feat"] = deep
            return out
        amp = np.linalg.norm(deep, axis=1, keepdims=True)
        unit = deep / (amp + 1e-12)
        out.update(amp=amp, unit=unit)
        if self.amp_sep:
            a = np.log1p(amp) - LN2 if (self.amp_log and self.stacked) else amp
            out["feat"] = np.concatenate([unit, a], axis=1)
        else:
            out["feat"] = unit
        return out

    def forward_cache(self, lat: np.ndarray) -> Dict[str, np.ndarray]:
        """前向并保留中间量。lat: (B,R,C,Cin)。"""
        p = self.params
        x = np.asarray(lat, dtype=np.float64)
        pre1 = hex_conv(x, tied_full(p.view("conv"), x.shape[3]))
        h1 = lrelu(pre1)
        c = {"x": x, "pre1": pre1, "h1": h1, "color": x.mean(axis=(1, 2))}
        if self.stacked:
            c["pre2"] = hex_conv(h1, p.view("conv2"))
            c["top"] = lrelu(c["pre2"])
        else:
            c["top"] = np.abs(h1)
        c.update(self._pool_feat(rms_pool(c["top"])))
        c["F"] = np.concatenate([c["feat"], c["color"]], axis=1)
        c["logits"] = c["F"] @ p.view("head").T
        return c

    def l1(self, lat: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """(|h1| 能量图 (B,R,C,K1), 均值色 (B,3))。"""
        p = self.params
        x = np.asarray(lat, dtype=np.float64)
        h1 = lrelu(hex_conv(x, tied_full(p.view("conv"), x.shape[3])))
        return np.abs(h1), x.mean(axis=(1, 2))

    def l2_features(self, lat: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """(深度特征, 均值色)。"""
        c = self.forward_cache(lat)
        return c["feat"], c["color"]

    def l3_logits(self, feat: np.ndarray, color: np.ndarray) -> np.ndarray:
        """组合头：[特征 ⊕ 色] @ head.T。"""
        return np.concatenate([feat, color], axis=1) @ self.params.view("head").T

    def l4_position(self, energy: np.ndarray, top_frac: float = 0.1) -> np.ndarray:
        """能量图 → 3×3 象限 one-hot (B,9)：只取能量前 top_frac 的 cell 求质心。"""
        b, r, c, _ = energy.shape
        w = np.abs(energy).sum(axis=-1)
        thr = np.quantile(w, 1.0 - top_frac, axis=(1, 2), keepdims=True)
        wm = w * (w >= thr)
        yy, xx = np.mgrid[0:r, 0:c]
        den = wm.sum(axis=(1, 2)) + 1e-9
        cy, cx = (wm * yy).sum(axis=(1, 2)) / den, (wm * xx).sum(axis=(1, 2)) / den
        qy = np.clip((cy / r * 3).astype(int), 0, 2)
        qx = np.clip((cx / c * 3).astype(int), 0, 2)
        out = np.zeros((b, 9))
        out[np.arange(b), qy * 3 + qx] = 1.0
        return out

    def _feat_backward(self, c: Dict[str, np.ndarray], gfeat: np.ndarray) -> np.ndarray:
        if not self.deep_norm:
            return gfeat
        k = c["deep"].shape[1]
        d, amp = c["deep"], c["amp"]
        n = amp + 1e-12
        g_unit = gfeat[:, :k]
        g = g_unit / n - d * (d * g_unit).sum(axis=1, keepdims=True) / (np.maximum(amp, 1e-300) * n * n)
        if self.amp_sep:
            g_amp = gfeat[:, k:k + 1]
            if self.amp_log and self.stacked:
                g_amp = g_amp / (1.0 + amp)
            g = g + g_amp * d / np.maximum(amp, 1e-300)
        return g

    def backward(self, c: Dict[str, np.ndarray], dlogits: np.ndarray) -> np.ndarray:
        """解析梯度（平铺顺序同 get_vec：conv | conv2 | head）。"""
        p = self.params
        head = p.view("head")
        g_head = dlogits.T @ c["F"]
        nf = c["feat"].shape[1]
        g_deep = self._feat_backward(c, (dlogits @ head)[:, :nf])
        g_top = rms_pool_backward(c["top"], c["deep"], g_deep)
        parts = []
        if self.stacked:
            g_pre2 = g_top * lrelu_grad(c["pre2"])
            g_h1, g_conv2 = hex_conv_backward(c["h1"], p.view("conv2"), g_pre2)
            parts.append(g_conv2.ravel())
        else:
            g_h1 = g_top * np.sign(c["h1"])
        g_pre1 = g_h1 * lrelu_grad(c["pre1"])
        _, g_full = hex_conv_backward(c["x"], tied_full(p.view("conv"), c["x"].shape[3]), g_pre1)
        return np.concatenate([g_full.sum(axis=1).ravel()] + parts + [g_head.ravel()])

    def _from_top(self, c: Dict[str, np.ndarray], top: np.ndarray, only: Optional[int] = None) -> Dict[str, np.ndarray]:
        if only is None:
            deep = rms_pool(top)
        else:                                   # 只有通道 only 变了：其余通道沿用缓存的 RMS
            deep = c["deep"].copy()
            deep[:, only] = np.sqrt((top[..., only] ** 2).mean(axis=(1, 2)) + 1e-12)
        u = self._pool_feat(deep)
        u["top"] = top
        u["F"] = np.concatenate([u["feat"], c["color"]], axis=1)
        u["logits"] = u["F"] @ self.params.view("head").T
        return u

    def _locate(self, flat_idx: int) -> Tuple[str, Tuple[int, ...]]:
        p = self.params
        for name in p.names():
            a, b = p.slice_of(name)
            if a <= flat_idx < b:
                return name, tuple(int(i) for i in np.unravel_index(flat_idx - a, p.view(name).shape))
        raise IndexError(flat_idx)

    def perturb(self, c: Dict[str, np.ndarray], flat_idx: int, delta: float) -> Dict[str, np.ndarray]:
        """参数 ``flat_idx`` 加 ``delta`` 后被改变的中间量（只重算受影响通道）。"""
        name, loc = self._locate(flat_idx)
        if name == "head":
            out = c["logits"].copy()
            out[:, loc[0]] += delta * c["F"][:, loc[1]]
            return {"logits": out}
        if name == "conv2":
            o, i, k = loc
            if "h1cols" not in c:
                c["h1cols"] = im2col(c["h1"])
            pre2 = c["pre2"].copy()
            pre2[..., o] += delta * c["h1cols"][:, :, k, i].reshape(pre2.shape[:3])
            top = c["top"].copy()
            top[..., o] = lrelu(pre2[..., o])
            return dict(self._from_top(c, top, only=o), pre2=pre2)
        o, k = loc
        if "xcols" not in c:
            c["xcols"] = im2col(c["x"]).sum(axis=3)
        pre1, h1 = c["pre1"].copy(), c["h1"].copy()
        pre1[..., o] += delta * c["xcols"][:, :, k].reshape(pre1.shape[:3])
        h1[..., o] = lrelu(pre1[..., o])
        upd = {"pre1": pre1, "h1": h1, "h1_changed": o}
        if not self.stacked:
            top = c["top"].copy()
            top[..., o] = np.abs(h1[..., o])
            return dict(self._from_top(c, top, only=o), **upd)
        pre2 = c["pre2"] + delta_conv(h1[..., o] - c["h1"][..., o], self.params.view("conv2")[:, o, :])
        return dict(self._from_top(c, lrelu(pre2)), pre2=pre2, **upd)

    def perturbed_logits(self, c: Dict[str, np.ndarray], flat_idx: int, delta: float) -> np.ndarray:
        """参数 ``flat_idx`` 加 ``delta`` 后的 logits（与整网重算 1e-12 一致）。"""
        return self.perturb(c, flat_idx, delta)["logits"]

    def commit(self, c: Dict[str, np.ndarray], flat_idx: int, delta: float) -> None:
        """原子写入参数增量，并把缓存就地推进到新参数状态（顺序坐标下降用）。"""
        upd = self.perturb(c, flat_idx, delta)
        o = upd.pop("h1_changed", None)
        self.params.apply_delta(flat_idx, delta)
        c.update(upd)
        if o is not None and "h1cols" in c:
            c["h1cols"][..., o] = im2col(c["h1"][..., o:o + 1])[..., 0]


def _shallow_perturb(net: ShallowHexNet, c: Dict[str, np.ndarray], flat_idx: int,
                     delta: float) -> Dict[str, np.ndarray]:
    p = net.params
    a_mix, b_mix = p.slice_of("mix")
    fc = p.view("fc")
    if flat_idx >= b_mix:
        o, m = np.unravel_index(flat_idx - b_mix, fc.shape)
        out = c["logits"].copy()
        out[:, o] += delta * c["pooled"][:, m]
        return {"logits": out}
    if flat_idx >= a_mix:
        m, k = np.unravel_index(flat_idx - a_mix, p.view("mix").shape)
        pre2 = c["pre2"].copy()
        pre2[..., m] += delta * c["h1"][..., k]
        h1, pre1, changed = c["h1"], c["pre1"], None
    else:
        k, j = np.unravel_index(flat_idx, p.view("conv").shape)
        if "xcols" not in c:
            c["xcols"] = im2col(c["x"])[..., 0]
        pre1, h1 = c["pre1"].copy(), c["h1"].copy()
        pre1[..., k] += delta * c["xcols"][:, :, j].reshape(pre1.shape[:3])
        h1[..., k] = lrelu(pre1[..., k])
        pre2 = c["pre2"] + (h1[..., k] - c["h1"][..., k])[..., None] * p.view("mix")[:, k]
        changed = k
    h2 = lrelu(pre2)
    pooled = rms_pool(h2)
    upd = {"pre1": pre1, "h1": h1, "pre2": pre2, "h2": h2, "pooled": pooled, "logits": pooled @ fc.T}
    return upd if changed is None else dict(upd, h1_changed=changed)


def _shallow_perturbed_logits(self: ShallowHexNet, c: Dict[str, np.ndarray], flat_idx: int,
                              delta: float) -> np.ndarray:
    """参数 ``flat_idx`` 加 ``delta`` 后的 logits（增量求值）。"""
    return _shallow_perturb(self, c, flat_idx, delta)["logits"]


def _shallow_commit(self: ShallowHexNet, c: Dict[str, np.ndarray], flat_idx: int, delta: float) -> None:
    """原子写入参数增量并推进缓存。"""
    upd = _shallow_perturb(self, c, flat_idx, delta)
    upd.pop("h1_changed", None)
    self.params.apply_delta(flat_idx, delta)
    c.update(upd)


ShallowHexNet.perturb = lambda self, c, i, d: _shallow_perturb(self, c, i, d)
ShallowHexNet.perturbed_logits = _shallow_perturbed_logits
ShallowHexNet.commit = _shallow_commit
