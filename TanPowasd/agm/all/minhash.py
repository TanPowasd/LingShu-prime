# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""模块 2：单置换 MinHash（OPH，Li/Owen/Zhang 2012；空桶右旋致密化，Shrivastava & Li 2014）+ LSH 带化 + 名次表近重复折叠。
PREREG_all.md §7。哈希 blake2b-64（不依赖 PYTHONHASHSEED）。"""
import hashlib, re

K_BINS, BANDS, ROWS = 64, 16, 4
SHINGLE, MIN_SHINGLES = 5, 8
TAU, WINDOW, SCAN = 0.8, 10, 100
_NW = re.compile(r"[\W_]+", re.U)
_EMPTY = (1 << 64) - 1


def shingles(text):
    s = _NW.sub("", text.lower())
    return {s[i:i + SHINGLE] for i in range(len(s) - SHINGLE + 1)}


def _h(x):
    return int.from_bytes(hashlib.blake2b(x.encode("utf-8"), digest_size=8).digest(), "little")


def signature(text):
    """返回 64 维签名；特征 < MIN_SHINGLES 返回 None（短文本不判重）。"""
    sh = shingles(text)
    if len(sh) < MIN_SHINGLES:
        return None
    sig = [_EMPTY] * K_BINS
    for x in sh:
        h = _h(x)
        b, v = h % K_BINS, h // K_BINS
        if v < sig[b]:
            sig[b] = v
    full = [i for i in range(K_BINS) if sig[i] != _EMPTY]
    out = list(sig)
    for i in range(K_BINS):                    # 右旋致密化：取右侧最近非空桶，加偏移避免偶然相等
        if sig[i] == _EMPTY:
            j, d = (i + 1) % K_BINS, 1
            while sig[j] == _EMPTY:
                j, d = (j + 1) % K_BINS, d + 1
            out[i] = sig[j] + d * (1 << 58)
    return tuple(out) if full else None


def bands(sig):
    return [sig[b * ROWS:(b + 1) * ROWS] for b in range(BANDS)]


def jaccard_est(a, b):
    return sum(x == y for x, y in zip(a, b)) / K_BINS


def fold(order, sig_of, tau=TAU, window=WINDOW, scan=SCAN):
    """order：名次表（轮号）；sig_of(t) → 签名或 None。与已保留更高名次者 LSH 撞带且估计 Jaccard ≥ tau ⇒ 推迟。
    保留满 window 个即停；推迟者接在其后，其余原序。返回 (新序, 被折叠轮号列表)。"""
    kept, late, buckets = [], [], {}
    i, lim = 0, min(scan, len(order))
    while i < lim and len(kept) < window:
        t = order[i]; i += 1
        s = sig_of(t)
        dup = False
        if s is not None:
            cand = set()
            for b, key in enumerate(bands(s)):
                cand.update(buckets.get((b, key), ()))
            dup = any(jaccard_est(s, sig_of(u)) >= tau for u in sorted(cand))
        if dup:
            late.append(t); continue
        kept.append(t)
        if s is not None:
            for b, key in enumerate(bands(s)):
                buckets.setdefault((b, key), []).append(t)
    return kept + late + list(order[i:]), late
