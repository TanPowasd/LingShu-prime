# -*- coding: utf-8 -*-
"""lingshu_ng.gen 研究脚本迁移部分：铺位证书（对拍暴力穷举）、多 seed 统计、跨源对齐探针。"""
import itertools
import math
import os
import subprocess
import sys

import numpy as np
import pytest

from lingshu_ng.gen import align_probe as A
from lingshu_ng.gen import multi_seed as M
from lingshu_ng.gen import pack_certify as P

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _brute(mask, n, shape, r):
    """暴力：所有 n 点组合两两余量 ≥ 0 即可行。"""
    pts = [(int(x), int(y)) for y, x in zip(*np.nonzero(mask))]
    for combo in itertools.combinations(pts, n):
        if all(math.hypot(a[0] - b[0], a[1] - b[1]) - P.need_between(shape, r, a[0] - b[0], a[1] - b[1]) >= -1e-9
               for a, b in itertools.combinations(combo, 2)):
            return True
    return False


@pytest.mark.parametrize("seed", range(12))
def test_certificate_matches_brute_force(seed):
    rng = np.random.default_rng(seed)
    shape = ["square", "rectangle", "diamond", "circle"][seed % 4]
    mask = rng.random((14, 16)) < 0.25
    for n in (2, 3):
        got = P.certify_radius(None, n, shape, 1 + seed % 3, mask=mask)
        assert got["feasible"] == _brute(mask, n, shape, 1 + seed % 3)
        w = P.witness_at(None, n, shape, 1 + seed % 3, mask=mask)
        assert (w is not None) == got["feasible"]
        if w:
            assert all(mask[y, x] for x, y in w)
            assert min(math.hypot(a[0] - b[0], a[1] - b[1]) - P.need_between(shape, 1 + seed % 3, a[0] - b[0],
                                                                               a[1] - b[1])
                       for a, b in itertools.combinations(w, 2)) >= -1e-9


def test_certify_p1_shares_core():
    mask = np.random.default_rng(3).random((12, 12)) < 0.4
    full = P.certify_radius(None, 3, "square", 1, mask=mask)
    for x, y, v in full["per_p1"][:10]:
        assert P.certify_p1(x, y, None, 3, "square", 1, mask=mask)[0] == v


def test_legal_mask_uses_same_cells_as_cell_of_pt():
    m = P.legal_mask(["r4"], "circle", 20, None, size=120)
    ys, xs = np.nonzero(m)
    assert len(xs) and {P.cell_of_pt(x, y, 120) for x, y in zip(xs, ys)} == {"r4"}
    e = P.paint_extent("circle", 20) + 2
    assert xs.min() >= e and ys.max() <= 120 - e


def test_witness_checks_and_radius_monotone():
    cells, size = ["r4"], 150
    w = P.witness_at(cells, 2, "circle", 8, None, size)
    ok, sl = P.check_witness(w, cells, 2, "circle", 8, None, size)
    assert ok and sl >= 0
    rmax = P.max_feasible_radius(cells, 2, "circle", 4, 30, None, size)
    assert P.certify_radius(cells, 2, "circle", rmax, None, size)["feasible"]
    assert not P.certify_radius(cells, 2, "circle", rmax + 1, None, size)["feasible"]


def test_support_is_direction_dependent_for_square():
    diag = P.need_between("square", 30, 1, 1)
    axis = P.need_between("square", 30, 1, 0)
    assert diag > axis and abs(axis - (2 * 31 + P.SEP_GAP + 2)) < 1e-9
    with pytest.raises(ValueError):
        P.certify_radius(["r4"], 4, "circle", 5)


def test_parse_prompt_and_pick():
    t = M.parse_prompt("flat vector illustration, two red striped circle(s) in the upper left area, plain")
    assert t == {"n": 2, "color": "red", "pattern": "striped", "shape": "circle", "zone_text": "upper left",
                 "cells": {"r0"}}
    assert M.parse_prompt("flat vector illustration, one teal circle(s) in the center") is None
    assert M.parse_prompt("a meadow") is None
    assert M.parse_prompt("flat vector illustration, one red circle(s) in the right si")["cells"] == {"r2", "r5", "r8"}
    lib = [{"name": "ls_a", "tags": {"prompt": "flat vector illustration, one red circle(s) in the center"}},
           {"name": "vs_s2", "tags": {"prompt": "flat vector illustration, one red circle(s) in the center"}},
           {"name": "vs_s1", "tags": {"prompt": "flat vector illustration, one red circle(s) in the center"}},
           {"name": "vs_s3", "tags": {"prompt": "waterfall"}},
           {"name": "vs_s4", "tags": {"prompt": "flat vector illustration, three blue square(s) in the top"}}]
    assert [p["sid"] for p in M.pick_prompts(lib, 5)] == ["vs_s1", "vs_s4"]


def test_item_id_stable_across_hashseed():
    code = "from lingshu_ng.gen.multi_seed import item_id; print(item_id('vs_s1', 11))"
    outs = {subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True,
                           env=dict(os.environ, PYTHONHASHSEED=h, PYTHONPATH=REPO)).stdout for h in ("0", "7")}
    assert len(outs) == 1 and int(outs.pop()) == M.item_id("vs_s1", 11)
    rows = M.render_rows([{"sid": "vs_s1", "prompt": "p"}], (11, 22), "/nonexistent")
    assert [r["seed"] for r in rows] == [11, 22] and not any(r["exists"] for r in rows)


def _read(sid, seed, shapes, feats):
    return {"sid": sid, "seed": seed, "n_read": len(shapes), "shapes": sorted(shapes),
            "colors": ["red"] * len(shapes), "patterns": ["plain"] * len(shapes),
            "cells": ["r4"] * len(shapes), "feats": feats}


def test_summarize_three_numbers():
    f = lambda *v: [np.array(v, float)]
    reads = [_read("a", 1, ["circle"], f(1, 0)), _read("a", 2, ["circle"], f(1.2, 0)),
             _read("a", 3, ["square"], f(1.1, 0)), _read("b", 1, ["square", "square"], f(5, 1) * 2),
             _read("b", 2, [], []), _read("b", 3, ["square", "square"], f(5.4, 1) * 2)]
    items = [{"sid": "a", "shape": "circle", "truth": {"n": 1, "shape": "circle", "color": "red", "pattern": "plain"}},
             {"sid": "b", "shape": "square", "truth": {"n": 2, "shape": "square", "color": "red", "pattern": "plain"}}]
    s = M.summarize(reads, items, dims=("x", "y"))
    assert s["n_prompt"] == 2 and s["n_img"] == 6 and s["n_img_empty"] == 1
    assert s["stability"]["shape"] == 0.25 and s["stability"]["count"] == 0.5
    assert s["honored"]["shape"] == round(4 / 6, 4) and s["honored"]["count"] == round(5 / 6, 4)
    wb = s["within_vs_between"]
    assert wb["dims"] == ["x", "y"] and wb["ratio_within_over_between"][1] == 0.0
    assert 0 < wb["ratio_within_over_between"][0] < 0.2 and wb["worst_dims"][0] == "x"


def test_align_probe_distance_and_hits():
    tot, contrib = A.distance_contrib([1, 2, 3], [1, 0, 0], [1, 1, 2], [1, 2, 1], dims=("a", "b", "c"))
    assert tot == 7.0 and contrib[0] == ("c", 6.0) and contrib[-1] == ("a", 0.0)
    rk = A.rank_protos([0, 0], {"t": [1, 1], "d": [0, 1], "c": [5, 5], "s": [9, 9]}, [1, 1], [1, 1], ("x", "y"))
    assert rk["ranked"] == ["d", "t", "c"]
    od = A.own_distribution([[0, 0], [2, 0], [1, 0]], [0, 0], [1, 1], [1, 1])
    assert od["n"] == 3 and od["median"] == 1.0 and od["all"] == [0.0, 1.0, 2.0]
    assert A.own_distribution([], [0], [1], [1]) is None
    pairs = [("stripe", "square"), ("triangle", "diamond"), ("circle", "circle")]
    assert A.cross_source_hits(pairs)["hit"] == 2 and A.cross_source_hits(pairs, False)["hit"] == 1
