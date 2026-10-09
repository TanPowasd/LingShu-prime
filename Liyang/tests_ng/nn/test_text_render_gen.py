# -*- coding: utf-8 -*-
"""text / render / layout / verify / ids / recon / stcnn 性质测试。"""
import itertools
import os
import subprocess
import sys

import numpy as np
import pytest

from lingshu_ng.gen import hexgen as H
from lingshu_ng.gen import layout as LY
from lingshu_ng.gen.ids import stable_id
from lingshu_ng.nn import recon, render, stcnn, text

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHAPES = ["circle", "triangle", "stripe", "square", "diamond", "star", "heart", "hexagon", "rectangle"]
COLORS = ["red", "green", "blue", "yellow", "purple"]


# ---------------- text ----------------
@pytest.mark.parametrize("t,want", [
    ("中心有蓝色菱形", ("diamond", "blue", "r4", None)), ("右下方有绿色", (None, "green", "r8", None)),
    ("中间有红色实心心形", ("heart", "red", "r4", "solid")), ("左上有条纹三角", ("triangle", None, "r0", "striped")),
    ("中间有红色条纹", ("stripe", "red", "r4", "striped")), ("灰底右下有白色方块", ("square", "white", "r8", None)),
])
def test_longest_match_resolves_surface_conflicts(t, want):
    c = text.parse(t)[0]
    assert (c.shape, c.color, c.pos, c.pattern) == want


def test_background_word_never_yields_part_color():
    for bg in text.BACKGROUND_WORDS:
        cs = text.parse(f"{bg},中间有圆", keep_empty=True)
        assert cs[0].background == text.BACKGROUND_WORDS[bg] and cs[0].color is None
        assert [c.pos for c in text.parse(f"{bg},中间有圆")] == ["r4"]


def test_same_field_conflict_is_recorded():
    c = text.parse("左上有红色绿色圆")[0]
    assert c.color == "red" and c.conflicts and c.conflicts[0]["dropped"] == "green"


def test_basic_vocab_ignores_open_words():
    c = text.parse("左上有黄色星", vocab="basic")[0]
    assert (c.shape, c.color, c.pos) == (None, None, "r0")


# ---------------- render / z-order ----------------
def test_z_order_explicit_and_stable():
    bg = np.zeros((30, 30, 3), np.uint8)
    a = render.DrawCall("square", 15, 15, 6, (200, 0, 0), "solid", z=1)
    b = render.DrawCall("square", 15, 15, 3, (0, 200, 0), "solid", z=0)
    img, feet = render.compose(bg, [a, b])
    assert tuple(img[15, 15]) == (200, 0, 0) and feet[1].visible.sum() == 0 and feet[0].visible.sum() > 0
    img2, feet2 = render.compose(bg, [render.DrawCall(**{**a.__dict__, "z": 0}), b])
    assert tuple(img2[15, 15]) == (0, 200, 0)


@pytest.mark.parametrize("shape", SHAPES)
def test_shape_masks_inside_bbox(shape):
    m = render.shape_mask(shape, 20, 20, 7, 41, 41)
    ys, xs = np.nonzero(m)
    assert m.sum() > 0 and xs.min() >= 13 and xs.max() <= 27 and ys.min() >= 13 and ys.max() <= 27


def test_unknown_shape_raises():
    with pytest.raises(ValueError):
        render.shape_mask("oval", 5, 5, 3, 10, 10)


# ---------------- layout ----------------
def test_legal_window_named_fields_and_inside_canvas():
    for size in (48, 96, 120):
        for z in [f"r{i}" for i in range(9)]:
            for rad in (2, 5, 9):
                w = LY.legal_window(z, size, rad, LY.overhang(size))
                assert w.x0 - rad >= 0 and w.x1 + rad <= size - 1 and w.y0 - rad >= 0 and w.y1 + rad <= size - 1


def _random_parts(g, k):
    return [{"shape": SHAPES[g.integers(len(SHAPES))], "color": COLORS[g.integers(len(COLORS))],
             "zone": f"r{g.integers(9)}", "pattern": render.PATTERNS[g.integers(3)],
             "size": ["small", "medium", "large"][g.integers(3)]} for _ in range(k)]


@pytest.mark.parametrize("seed", range(30))
def test_separated_layout_is_fully_fulfilled(seed):
    """性质：摆位判为不相交时，读像素验证必须 100% 兑现（任意形状/颜色/花纹/尺寸）。"""
    g = np.random.default_rng(seed)
    size = [48, 96][seed % 2]
    parts = _random_parts(g, int(g.integers(1, 4)))
    r = H.render(parts, size=size, seed=seed, noise=True)
    if all(e["separated"] for e in r.log):
        assert H.verify_parts(parts, r.log)["rate"] == 1.0, r.log


@pytest.mark.parametrize("bad", ["noop", "mirror", "pattern", "color", "shape", "size"])
def test_verify_reads_pixels_against_faulty_painters(bad):
    parts = [{"shape": "triangle", "color": "green", "zone": "r0", "pattern": "dotted", "size": "medium"}]

    def faulty(img, shape, cx, cy, rad, col, pat):
        if bad == "noop":
            return
        if bad == "mirror":
            return render.paint(img, shape, img.shape[1] - 1 - cx, cy, rad, col, pat)
        if bad == "pattern":
            return render.paint(img, shape, cx, cy, rad, col, "striped")
        if bad == "color":
            return render.paint(img, shape, cx, cy, rad, (40, 60, 220), pat)
        if bad == "shape":
            return render.paint(img, "square", cx, cy, rad, col, pat)
        return render.paint(img, shape, cx, cy, max(1, rad - 2), col, pat)

    r = H.render(parts, size=96, seed=1, noise=False, painter=faulty)
    assert H.verify_parts(parts, r.log)["rate"] == 0.0


def test_ids_stable_across_processes():
    code = "from lingshu_ng.gen.ids import stable_id; print(stable_id('sid-1', 42))"
    outs = {subprocess.run([sys.executable, "-c", code], env=dict(os.environ, PYTHONHASHSEED=s, PYTHONPATH=REPO),
                           capture_output=True, text=True).stdout.strip() for s in ("0", "1", "12345")}
    assert outs == {stable_id("sid-1", 42)}


# ---------------- recon ----------------
@pytest.mark.parametrize("seed", range(6))
def test_reconstruct_order_invariant_random_rects(seed):
    g = np.random.default_rng(seed)
    img = np.full((24, 24, 3), 200, np.uint8)
    for _ in range(3):
        y, x, h, w = (int(v) for v in g.integers(0, 16, 4))
        img[y:y + h // 2 + 3, x:x + w // 2 + 3] = g.integers(0, 3) * 90
    regs, _ = recon.extract_regions(img)
    conns = recon.regions_to_connections(regs, img.shape)
    ref = recon.reconstruct(conns)
    for perm in itertools.islice(itertools.permutations(conns["connections"]), 24):
        assert np.array_equal(recon.reconstruct({**conns, "connections": list(perm)}), ref)


def test_containment_depth():
    assert recon.containment_depth([[0, 0, 9, 9], [2, 2, 5, 5], [3, 3, 4, 4], [7, 7, 8, 8]]) == [0, 1, 2, 1]


# ---------------- stcnn ----------------
def test_conv3d_matches_naive():
    g = np.random.default_rng(0)
    v, k = g.random((5, 7, 6)), g.random((2, 3, 3))
    out = stcnn.conv3d(v, k)
    ref = np.array([[[(v[t:t + 2, i:i + 3, j:j + 3] * k).sum() for j in range(4)] for i in range(5)] for t in range(4)])
    assert np.allclose(out, ref, atol=1e-12)


@pytest.mark.parametrize("scale,offset", [(0.01, 0.0), (300.0, 7.0), (1.0, -3.0)])
def test_primitives_affine_invariant(scale, offset):
    f = stcnn.synth_ball_rolling(12, speed_px=2)
    base = stcnn.extract_spatiotemporal_primitives(f)[0]
    got = stcnn.extract_spatiotemporal_primitives([x * scale + offset for x in f])[0]
    for k in ("direction", "speed", "period", "moving", "t_first", "t_last"):
        assert got[k] == base[k]


def test_memory_digest_detects_tamper():
    m = stcnn.SpatiotemporalMemory()
    p, _ = stcnn.extract_spatiotemporal_primitives(stcnn.synth_ball_rolling(10))
    m.remember(p, "球", t_start=5)
    assert m.verify_consistency()
    m.events[0]["t_end"] += 1
    assert not m.verify_consistency()
