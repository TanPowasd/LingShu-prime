# -*- coding: utf-8 -*-
"""neardup · 近重复候选（:meth:`lingshu_ng.store.textindex.TextIndex.near_duplicate_candidates` 的主体，stab-r10 拆出）

算法与 rel-v1.25 相同（前缀 + 逐步校验 + 剪枝，结果 = 「Jaccard(A, B) ≥ t 且 |B| 在长度窗口内或未知」的节点集合，
tests_ng/test_perf_scale.py 对照全层暴力比对与 v1.25 实现逐值相同）。stab-r10 只改实现的常数，不改任何判定：

  * 前缀倒排的长度过滤用 65536 项查表 + ``itertools.compress``，计数用 ``Counter.update``（C 层循环），
    v1.25 为逐条 Python 循环；
  * 每个候选的下限 need_B 只依赖 |B|，按 |B| 记忆化（同一表达式、同一浮点运算顺序）；
  * 剪枝「已命中 + 剩余可命中 < need_B」改为按缺口 need_B − 已命中 分桶：剩余数每步减一，只需弹出缺口恰好越界的那一桶，
    v1.25 每步扫全部存活候选（100k 库每次写入的存活候选上千、步数数十）；
  * 读整条倒排求交改为集合交（C 层）。
各步「读整条倒排 / 主键点查」的分支条件与 v1.25 相同（存活数相同），因此读的块也相同。
"""
from __future__ import annotations

import math
import sys
from collections import Counter
from itertools import compress
from typing import Any, Dict, List, Set, Tuple

__all__ = ["candidates"]

_BIG = sys.byteorder == "big"


def _mask(lo: int, hi: int) -> bytes:
    """|B| 合格表：下标 g（0 ≤ g < 65536）合格 ⇔ g == 0（未知）或 lo ≤ g ≤ hi。"""
    tbl = bytearray(65536)
    tbl[0] = 1
    a, b = max(1, lo), min(65535, hi)
    if a <= b:
        tbl[a:b + 1] = b"\x01" * (b - a + 1)
    return bytes(tbl)


_HI0 = bytes([1] + [0] * 255)


def _select(gs: Any, lo: int, hi: int, tbl: bytes) -> Any:
    """窄编码 grams 数组的合格位（每条一个 0/1）。uint8 数组（schema v7）直接按字节查表；uint16 且 hi < 256 时按字节查表：低字节查 tbl、高字节须为 0，两串按位与
    （与逐条查 65536 项表结果相同）；否则逐条查表。"""
    if gs.itemsize == 1:                  # v7 uint8 块：值都 < 256，直接按字节查表
        return gs.tobytes().translate(tbl[:256])
    if hi < 256 and gs.itemsize == 2 and not _BIG:
        raw = gs.tobytes()
        n = len(gs)
        a = int.from_bytes(raw[0::2].translate(tbl[:256]), "little")
        b = int.from_bytes(raw[1::2].translate(_HI0), "little")
        return (a & b).to_bytes(n, "little")
    return list(map(tbl.__getitem__, gs))


def _prefix(ti: Any, terms: List[str], lo: int, hi: int) -> Tuple[Counter, Dict[int, int]]:
    """前缀倒排 → (候选命中数, 候选 |B|)；只计 |B| 合格的行（与 v1.25 ``postings_len`` 相同的过滤）。"""
    cnt: Counter = Counter()
    nb: Dict[int, int] = {}
    tbl = None
    for g in terms:
        ks, gs = ti.postings_arrays(g)
        if gs.typecode in ("H", "B"):
            if tbl is None:
                tbl = _mask(lo, hi)
            sel = _select(gs, lo, hi, tbl)
        else:
            sel = [x == 0 or lo <= x <= hi for x in gs]
        k2 = list(compress(ks, sel))
        cnt.update(k2)
        nb.update(zip(k2, compress(gs, sel)))
    return cnt, nb


def _deficits(cnt: Counter, nb: Dict[int, int], need: int, a: int, threshold: float, left: int) -> Dict[int, int]:
    """候选的缺口 need_B − 已命中（need_B 同 v1.25：|B| 已知时 max(need, ⌈t/(1+t)·(|A|+|B|)⌉)，未知时 need），
    只留缺口 ≤ left（= 首个校验步的剩余可命中数；v1.25 首步即剔除其余候选，无校验步时 left = 0 即最终判定）。"""
    t1 = threshold / (1.0 + threshold) * (1 - 1e-9)
    q = {n: (max(need, math.ceil(t1 * (a + n))) if n else need) for n in set(nb.values())}
    return {k: d for k, n in nb.items() if (d := q[n] - cnt[k]) <= left}


def _verify(ti: Any, rest: List[str], dfs: Dict[str, int], alive: Dict[int, int], a: int, done: int) -> None:
    """其余二元组按 df 升序逐个校验（原地更新 alive：键 → 缺口）。每步先剔除缺口 > 剩余可命中数的候选，存活为空即停；
    读整条倒排 / 点查的分支同 v1.25（df 不超过存活数读整条倒排，否则点查）。"""
    buckets: Dict[int, Set[int]] = {}
    for k, d in alive.items():
        s = buckets.get(d)
        if s is None:
            s = buckets[d] = set()
        s.add(k)
    top = max(buckets) if buckets else 0
    for g in rest:
        left = a - done
        while top > left:
            for k in buckets.pop(top, ()):
                del alive[k]
            top -= 1
        if not alive:
            break
        d = dfs.get(g, 0)
        if d > 0:
            if d <= len(alive):
                got = alive.keys() & set(ti.postings_arrays(g)[0])
            else:
                got = ti.members(g, sorted(alive))
            for k in got:
                x = alive[k]
                buckets[x].discard(k)
                alive[k] = x - 1
                s = buckets.get(x - 1)
                if s is None:
                    s = buckets[x - 1] = set()
                s.add(k)
        done += 1


def candidates(ti: Any, grams: frozenset, threshold: float) -> Set[str]:
    """0 < t ≤ 1 时的近重复候选（调用方已 flush、grams 非空）；同时写 ``ti.last_probe``（与 v1.25 相同）。"""
    a = len(grams)
    need = max(1, math.ceil(threshold * a - 1e-9))
    dfs = ti.df(grams)
    ti.last_probe = (grams, dfs)          # 写入期矛盾检测（conflict C1）复用，免再查一次 df
    if len(dfs) < need:
        return set()                      # 库里连 need 个二元组都凑不齐 ⇒ 不可能近重复
    order = sorted(grams, key=lambda g: (dfs.get(g, 0), g))
    r = a - need + 1
    lo = math.floor(threshold * a * (1 - 1e-9))
    hi = math.ceil(a / threshold * (1 + 1e-9))
    cnt, nb = _prefix(ti, [g for g in order[:r] if dfs.get(g, 0) > 0], lo, hi)
    alive = _deficits(cnt, nb, need, a, threshold, a - r)
    _verify(ti, order[r:], dfs, alive, a, r)
    return set(ti.node_ids([k for k, d in alive.items() if d <= 0]).values())
