# -*- coding: utf-8 -*-
"""gen 同格多部件布局：cellpack 证书摆位、盒搜索向量化对拍、局部渲染与全幅公式一致、兑现率回归。"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lingshu_ng.gen import cellpack as CP          # noqa: E402
from lingshu_ng.gen import hexgen as H             # noqa: E402
from lingshu_ng.gen import layout as LY            # noqa: E402
from lingshu_ng.gen.verify import COVERAGE_MIN, SPILL_MAX  # noqa: E402
from lingshu_ng.nn import render                    # noqa: E402

import gen_diag as GD                               # noqa: E402

SHAPES = sorted(render.RENDERABLE)


def _rate(size, seed0, n):
    ok = tot = 0
    for t, parts in GD.protocol_cases(seed0, n):
        v = H.verify_parts(parts, H.render(parts, size=size, seed=t).log)
        ok, tot = ok + v["matched"], tot + v["total"]
    return ok / tot


@pytest.mark.parametrize("size,seed0,n,floor", [(96, 98, 200, 0.99), (48, 99, 200, 0.985), (96, 24, 30, 0.99),
                                                (48, 23, 30, 0.984)])
def test_r2_fulfilment_regression(size, seed0, n, floor):
    """bench R2 协议（同题序）：96px ≥ 0.99，48px 不低于改进前读数。"""
    assert _rate(size, seed0, n) >= floor


@pytest.mark.parametrize("t", [15, 60, 67, 103, 107, 151, 158])
def test_previously_stacked_cases_now_certified(t):
    """改进前 R2@96_200 叠放失败的题：现经证书摆位全部兑现，且部件实心轮廓两两交 ≤ 下层预算（无交织）。"""
    parts = dict(GD.protocol_cases(98, 200))[t]
    r = H.render(parts, size=96, seed=t, noise=False)
    assert H.verify_parts(parts, r.log)["rate"] == 1.0
    assert all(e["separated"] for e in r.log)
    order = sorted(range(len(parts)), key=lambda i: (r.log[i]["z"], i))
    for x, a in enumerate(order):
        sa = render.shape_mask(r.log[a]["shape"], *r.log[a]["center"], r.log[a]["rad"], 96, 96)
        for b in order[x + 1:]:
            sb = render.shape_mask(r.log[b]["shape"], *r.log[b]["center"], r.log[b]["rad"], 96, 96)
            assert (sa & sb).sum() <= (1 - COVERAGE_MIN) * sa.sum()


def test_interleaved_patterns_rejected():
    """两件同格中等圆（一点纹一条纹）：不得以花纹相位错开、中心几乎重合的方式“兑现”。"""
    parts = [{"shape": "circle", "color": "green", "zone": "r8", "pattern": "dotted", "size": "medium"},
             {"shape": "circle", "color": "blue", "zone": "r8", "pattern": "striped", "size": "medium"}]
    r = H.render(parts, size=96, seed=158, noise=False)
    (x0, y0), (x1, y1) = r.log[0]["center"], r.log[1]["center"]
    assert max(abs(x0 - x1), abs(y0 - y1)) > r.log[0]["rad"]


def test_infeasible_group_falls_back_to_stack():
    """三件大实心同色方块挤角格（48px，r0 两边贴画幅无处越格）：物理放不下 → 叠放且如实判未兑现，不伪造。"""
    parts = [{"shape": "square", "color": "red", "zone": "r0", "pattern": "solid", "size": "large"}] * 3
    r = H.render(parts, size=48, seed=1, noise=False)
    assert not all(e["separated"] for e in r.log)
    assert H.verify_parts(parts, r.log)["rate"] < 1.0


def test_center_cell_triple_certified_within_budget():
    """同三件放中心格 r4：四向可越格，cellpack 求得少量遮挡的证书摆位——兑现须真实（覆盖率达标、实心轮廓交 ≤ 预算）。"""
    parts = [{"shape": "square", "color": "red", "zone": "r4", "pattern": "solid", "size": "large"}] * 3
    r = H.render(parts, size=48, seed=1, noise=False)
    assert all(e["separated"] for e in r.log) and H.verify_parts(parts, r.log)["rate"] == 1.0
    assert all(e["coverage"] >= COVERAGE_MIN and e["spill"] <= SPILL_MAX for e in r.log)
    m = [render.shape_mask(e["shape"], *e["center"], e["rad"], 48, 48) for e in r.log]
    for a in range(3):
        for b in range(a + 1, 3):
            assert (m[a] & m[b]).sum() <= (1 - COVERAGE_MIN) * m[a].sum()


@pytest.mark.parametrize("k", [4, 5])
def test_more_than_three_same_cell_stacks_without_crash(k):
    """同格 ≥4 件超出证书搜索范围：不得崩溃（曾因只赋值前三件中心而 TypeError），叠放并如实判未兑现。"""
    parts = [{"shape": "square", "color": "red", "zone": "r4", "pattern": "solid", "size": "large"}] * k
    r = H.render(parts, size=48, seed=1, noise=False)
    assert len(r.log) == k and not all(e["separated"] for e in r.log)
    assert H.verify_parts(parts, r.log)["rate"] < 1.0


@pytest.mark.parametrize("seed", range(40))
def test_vectorized_box_search_matches_reference(seed):
    g = np.random.default_rng(seed)
    size = [48, 96][seed % 2]
    k = int(g.integers(2, 4))
    zones = [f"r{g.integers(9)}" for _ in range(k)]
    if seed % 3 == 0:
        zones = [zones[0]] * k
    rads = [size // [14, 10, 7][g.integers(3)] for _ in range(k)]
    wins = [LY.legal_window(z, size, r, LY.overhang(size)) for z, r in zip(zones, rads)]
    cands = [w.lattice_points()[::-1] for w in wins]
    for budget in (50, 2000, 200000):
        ref = LY._search_ref(cands, rads, 0, [], [budget])
        got = LY._search([np.asarray(c).reshape(-1, 2) for c in cands], rads, 0, [], [budget])
        assert ref == got


@pytest.mark.parametrize("seed", range(20))
def test_group_box_feasible_is_exact(seed):
    g = np.random.default_rng(100 + seed)
    size = [48, 96][seed % 2]
    k = int(g.integers(2, 4))
    z = f"r{g.integers(9)}"
    rads = [size // [14, 10, 7][g.integers(3)] for _ in range(k)]
    cands = [LY.legal_window(z, size, r, LY.overhang(size)).lattice_points() for r in rads]
    ref = LY._search_ref(cands, rads, 0, [], [10 ** 9]) is not None
    assert LY.group_box_feasible([np.asarray(c).reshape(-1, 2) for c in cands], rads) == ref


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("pattern", render.PATTERNS)
def test_part_mask_equals_full_frame_formula(shape, pattern):
    for cx, cy, rad in ((3, 4, 7), (90, 2, 9), (50, 50, 13), (0, 95, 6), (-3, 40, 5)):
        ref = render.shape_mask(shape, cx, cy, rad, 96, 96) & render.pattern_mask(pattern, 96, 96, (cx, cy))
        assert np.array_equal(render.part_mask(shape, cx, cy, rad, pattern, 96, 96), ref)


def test_viable_matches_brute_force():
    g = np.random.default_rng(3)
    for _ in range(10):
        ra, rb = int(g.integers(3, 14)), int(g.integers(3, 14))
        sa, sb = CP.silhouette("circle", ra), CP.silhouette("triangle", rb)
        tab = CP.overlap_table(sa, sb)
        bad = tab > int(g.integers(0, 20))
        ca = g.integers(10, 60, (30, 2))
        cb = g.integers(10, 60, (40, 2))
        got = CP._viable(ca, cb, bad, ra + rb, 96)
        ref = [CP._ok_mask(bad, ra + rb, cb - pa).any() for pa in ca]
        assert list(got) == ref


def test_overlap_table_matches_direct():
    a, b = CP.silhouette("circle", 5), CP.silhouette("stripe", 3)
    tab = CP.overlap_table(a, b)
    for dy in range(-8, 9):
        for dx in range(-8, 9):
            A = np.zeros((40, 40), bool)
            B = np.zeros((40, 40), bool)
            A[15:26, 15:26] = a
            B[17 + dy:24 + dy, 17 + dx:24 + dx] = b
            assert tab[dy + 8, dx + 8] == (A & B).sum()


def test_thresholds_unchanged():
    assert COVERAGE_MIN == 0.9 and SPILL_MAX == 0.1
