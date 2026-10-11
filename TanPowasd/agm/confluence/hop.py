# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""两跳排名：第一跳 QMD 排名 + 追问检索式各自跑 v3（及可选 QMD 通道），加权 RRF 融合；可钉住第一跳前 P 段。"""
import collections


def fuse(o1, follows, v3, w1=1.0, wh=1.0, pin=0, k=60, skip_found=False, found=False, split=True):
    if not follows or (skip_found and found):
        return o1
    sc = collections.defaultdict(float)
    for i, t in enumerate(o1[:400]):
        sc[t] += w1 / (k + i + 1)
    w = wh / len(follows) if split else wh
    for f in follows:
        for i, t in enumerate(v3(f)[:400]):
            sc[t] += w / (k + i + 1)
    head = o1[:pin]; hs = set(head)
    o = head + [t for t in sorted(sc, key=lambda t: -sc[t]) if t not in hs]
    s = set(o)
    return o + [t for t in o1 if t not in s]
