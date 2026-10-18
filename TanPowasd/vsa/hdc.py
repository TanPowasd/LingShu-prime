# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""MAP-B 超维原语（THEORY.md §1、§4）。零模型、确定性：原子向量由 blake2b(种子|名字|块号) 派生，不用 Python hash、不用全局 RNG。"""
import hashlib, math

import numpy as np

D = 10000
BLOCK = 1000                     # 原子按 1000 维一块生成，块可独立重算（ri.py 按块投影）
assert D % BLOCK == 0


class CapacityError(ValueError):
    """叠加项数超过 K_MAX（THEORY §4）：拒绝写入，调用方必须分块。"""


def _seed(space_seed, name, block):
    h = hashlib.blake2b(f"{space_seed}|{name}|{block}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little")


class Space:
    """一个超维空间：同种子同名字 ⇒ 同向量（I5）。"""

    def __init__(self, seed="vsa-v1", dim=D, cache_max=50000):
        assert dim % BLOCK == 0
        self.seed, self.dim, self.cache_max = seed, dim, cache_max
        self._cache = {}
        self.tie = self.vec("__tie__")          # sign 平票向量（固定种子）

    def vec_block(self, name, b):
        rng = np.random.default_rng(_seed(self.seed, name, b))
        return (rng.integers(0, 2, BLOCK, dtype=np.int8) * 2 - 1).astype(np.int8)

    def vec(self, name):
        v = self._cache.get(name)
        if v is None:
            v = np.concatenate([self.vec_block(name, b) for b in range(self.dim // BLOCK)])
            if len(self._cache) < self.cache_max:
                self._cache[name] = v
        return v

    def sgn(self, x):
        """整数叠加 → 双极；0 维取平票向量的号（确定性）。"""
        s = np.sign(x).astype(np.int8)
        z = s == 0
        if z.any():
            s[z] = self.tie[z]
        return s


def bind(a, b):
    """⊗ = 逐维乘；双极下自逆（I1）。整数叠加向量也可与双极原子绑定（逐维乘仍是线性的）。"""
    return np.multiply(a, b, dtype=np.int32 if (a.dtype != np.int8 or b.dtype != np.int8) else np.int8)


def unbind(x, key):
    """解绑 = 绑定（R⊗R = 1）。"""
    return bind(x, key)


def bundle(xs):
    """⊕ = 整数逐维求和（不截断）。"""
    xs = list(xs)
    if not xs:
        return np.zeros(D, dtype=np.int32)
    return np.sum(np.stack([np.asarray(x, dtype=np.int32) for x in xs]), axis=0)


def permute(x, n=1):
    """ρ^n = 循环移位；ρ^{-n} 为逆。"""
    return np.roll(x, n)


def cos(a, b):
    a = np.asarray(a, dtype=np.float64); b = np.asarray(b, dtype=np.float64)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return 0.0 if na == 0 or nb == 0 else float(a @ b / (na * nb))


# ---------------------------------------------------------------- 容量理论（THEORY §4）
def cos_int_theory(k):
    """整数叠加 k 个绑定项、解绑后与正确填充的期望余弦 ≈ 1/√k。"""
    return 1.0 / math.sqrt(k)


def cos_sign_theory(k):
    """sign 叠加（k 奇数）：E[x_t·sign(Σx_j)] = C(k−1,(k−1)/2)/2^{k−1}。"""
    assert k % 2 == 1
    return math.comb(k - 1, (k - 1) // 2) / 2 ** (k - 1)


def qfunc(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def qinv(p):
    lo, hi = 0.0, 40.0                         # 二分求 Q⁻¹，单调，60 步精度远超需要
    for _ in range(200):
        mid = (lo + hi) / 2
        if qfunc(mid) > p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def err_bound(k, n_codebook, dim=D):
    """N 个候选码本、痕迹 k 项时清理错误率的并联上界 (N−1)·Q(√(D/(2k−1)))。"""
    return min(1.0, (n_codebook - 1) * qfunc(math.sqrt(dim / (2 * k - 1))))


def k_max(dim=D, n_codebook=1000, eps=1e-3):
    """分块上限：(N−1)·Q(√(D/(2k−1))) ≤ ε 的最大 k。"""
    z = qinv(eps / max(1, n_codebook - 1))
    return int((dim / z ** 2 + 1) // 2)


K_MAX = k_max()                                 # D=10000, N=1000, ε=1e−3 → ≈221
MARGIN_MIN = 2.0 / math.sqrt(D)                 # I7：边距 < 2σ ⇒ 存疑。角色缺席时 top-2 间隙 ≈ Exp(均值 σ/√(2lnN))，P(间隙>2σ)≈e^{−2√(2lnN)}≈1.5e−3（N=200）；
                                                #     角色在场且 k≤K_MAX 时边距 ≈ 1/√k − √(2lnN)σ ≥ 0.067−0.033 > 2σ。（初版 4σ 与此推导矛盾，见 THEORY §5 修订记录）
