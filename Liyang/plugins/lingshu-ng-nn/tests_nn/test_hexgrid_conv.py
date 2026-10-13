# -*- coding: utf-8 -*-
"""hexgrid / conv 性质测试（随机化，多种子）。"""
import math

import numpy as np
import pytest

from lingshu_ng.nn import conv, hexgrid

SEEDS = range(12)


def _rand_frame(seed):
    g = np.random.default_rng(seed)
    return int(g.integers(8, 400)), int(g.integers(8, 400)), int(g.integers(1, 64))


@pytest.mark.parametrize("seed", SEEDS)
def test_lattice_strictly_inside_frame(seed):
    w, h, n = _rand_frame(seed)
    lat = hexgrid.fit_lattice(w, h, n)
    x0, y0, x1, y1 = lat.extent()
    assert x0 >= -1e-9 and y0 >= -1e-9 and x1 <= w + 1e-9 and y1 <= h + 1e-9
    assert lat.cols == n and lat.rows >= 1


@pytest.mark.parametrize("seed", SEEDS)
def test_lattice_rows_are_maximal(seed):
    w, h, n = _rand_frame(seed)
    lat = hexgrid.fit_lattice(w, h, n)
    if 2 * lat.size <= h:      # 正常画幅：再加一行必越界
        bigger = hexgrid.HexLattice(lat.rows + 1, lat.cols, lat.size, lat.x0, lat.y0)
        assert bigger.extent()[3] > h + 1e-9


def test_legacy_overflow_regression():
    """旧 image_to_grid：48px × 16 列 → 40.6% cell 中心在画外；ng 必须为 0。"""
    lat = hexgrid.fit_lattice(48, 48, 16)
    xs, ys = lat.centers()
    assert ((xs < 0) | (xs >= 48) | (ys < 0) | (ys >= 48)).sum() == 0


@pytest.mark.parametrize("seed", SEEDS)
def test_neighbors_equidistant_and_symmetric(seed):
    g = np.random.default_rng(seed)
    lat = hexgrid.fit_lattice(200, 200, 20)
    c, r = int(g.integers(1, lat.cols - 1)), int(g.integers(1, lat.rows - 1))
    cx, cy = lat.center(c, r)
    d = [math.hypot(*(np.subtract(lat.center(*nb), (cx, cy)))) for nb in lat.neighbors(c, r)]
    assert max(d) - min(d) < 1e-9 and abs(d[0] - lat.spacing) < 1e-9
    for nb in lat.neighbors(c, r):
        assert (c, r) in lat.neighbors(*nb)


@pytest.mark.parametrize("seed", SEEDS)
def test_pixel_cell_roundtrip_and_axial(seed):
    g = np.random.default_rng(seed)
    lat = hexgrid.fit_lattice(300, 250, int(g.integers(2, 40)))
    for _ in range(20):
        c, r = int(g.integers(lat.cols)), int(g.integers(lat.rows))
        assert lat.pixel_to_cell(*lat.center(c, r)) == (c, r)
        assert hexgrid.axial_to_offset(*hexgrid.offset_to_axial(c, r)) == (c, r)


def test_axial_dirs_match_offsets():
    for r in (2, 3):
        for k, (dc, dr) in enumerate(hexgrid.ODD_OFFSETS if r & 1 else hexgrid.EVEN_OFFSETS):
            q0, r0 = hexgrid.offset_to_axial(5, r)
            q1, r1 = hexgrid.offset_to_axial(5 + dc, r + dr)
            assert (q1 - q0, r1 - r0) == hexgrid.AXIAL_DIRS[k]


@pytest.mark.parametrize("seed", SEEDS)
def test_sampling_constant_and_every_cell_filled(seed):
    w, h, n = _rand_frame(seed)
    lat = hexgrid.fit_lattice(w, h, n)
    f = hexgrid.sample_image(np.full((h, w, 3), 77.0), lat)
    assert f.shape == (lat.rows, lat.cols, 3) and np.allclose(f, 77.0)


def test_sampling_localizes_block():
    img = np.zeros((120, 160, 3))
    img[40:80, 60:100] = 255
    f, lat = hexgrid.image_to_lattice(img, 32)
    c, r = lat.pixel_to_cell(80, 60)
    assert f[r, c].mean() == 255 and f[1, 1].mean() == 0


@pytest.mark.parametrize("seed", SEEDS)
def test_gemm_equals_naive(seed):
    g = np.random.default_rng(seed)
    b, r, c = int(g.integers(1, 3)), int(g.integers(1, 7)), int(g.integers(1, 7))
    cin, cout = int(g.integers(1, 4)), int(g.integers(1, 4))
    x, w = g.normal(size=(b, r, c, cin)), g.normal(size=(cout, cin, 7))
    a, ref = conv.hex_conv(x, w), conv.hex_conv_naive(x, w)
    assert np.max(np.abs(a - ref)) <= 1e-12 * max(1.0, np.max(np.abs(ref)))


@pytest.mark.parametrize("seed", SEEDS[:4])
def test_depthwise_equals_full_per_channel(seed):
    g = np.random.default_rng(seed)
    x, k = g.normal(size=(2, 5, 6, 3)), g.normal(size=(3, 7))
    dw = conv.hex_conv_depthwise(x, k)
    for ch in range(3):
        full = conv.hex_conv(x[..., ch:ch + 1], k[ch][None, None, :])[..., 0]
        assert np.max(np.abs(dw[..., ch] - full)) < 1e-12


@pytest.mark.parametrize("seed", SEEDS[:4])
def test_backward_matches_finite_difference(seed):
    g = np.random.default_rng(seed)
    x, w, go = g.normal(size=(2, 5, 4, 2)), g.normal(size=(3, 2, 7)), g.normal(size=(2, 5, 4, 3))
    gx, gw = conv.hex_conv_backward(x, w, go)
    f = lambda xx, ww: float((conv.hex_conv(xx, ww) * go).sum())
    e = 1e-6
    for idx in [tuple(g.integers(0, s) for s in w.shape) for _ in range(6)]:
        wp = w.copy(); wp[idx] += e
        assert abs((f(x, wp) - f(x, w)) / e - gw[idx]) < 1e-5
    for idx in [tuple(g.integers(0, s) for s in x.shape) for _ in range(6)]:
        xp = x.copy(); xp[idx] += e
        assert abs((f(xp, w) - f(x, w)) / e - gx[idx]) < 1e-5


def test_kernel_properties_on_constant_field():
    x = np.full((6, 7, 3), 100.0)
    assert np.allclose(conv.hex_conv_depthwise(x, conv.kernel_smooth()), 100.0)
    assert np.allclose(conv.hex_conv_depthwise(x, conv.kernel_laplacian()), 0.0)
    assert np.allclose(conv.hex_conv_depthwise(x, conv.kernel_center_surround()), 0.0)


def test_neighbor_table_read_only_and_clamped():
    t = conv.neighbor_index(4, 5)
    assert t.shape == (20, 7) and t.min() >= 0 and t.max() < 20
    with pytest.raises(ValueError):
        t[0, 0] = 3
