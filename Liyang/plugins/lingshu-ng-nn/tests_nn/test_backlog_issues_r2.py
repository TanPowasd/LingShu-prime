# -*- coding: utf-8 -*-
"""上游老 issue 逐条复核（r2，#186–#194 非 core 段）在 ng 上的回归测试。"""
import numpy as np
import pytest

from lingshu_ng.gen import pack_certify as P
from lingshu_ng.nn import multimodal as MM
from lingshu_ng.nn import scenes as SC


# ---- #188：无标定缺省切点为画幅比例，与 cell_of_pt 同口径 ----
@pytest.mark.parametrize("cells", [("r4",), ("r0",), ("r2", "r6")])
def test_188_default_cuts_consistent(cells):
    size = 512
    rc, cc = P._cuts(None, size)
    assert rc == pytest.approx([1 / 3, 2 / 3]) and cc == pytest.approx([1 / 3, 2 / 3])
    for y in range(0, size, 37):
        for x in range(0, size, 37):
            row = min(2, int(y / size * 3))
            col = min(2, int(x / size * 3))
            assert P.cell_of_pt(x, y, size, None) == f"r{row * 3 + col}"


def test_188_certify_radius_without_r0():
    r = P.certify_radius(("r4",), 2, "circle", 40, None, max_p1=5)
    assert r["feasible"] is True


# ---- #189：缺词子句不抛 TypeError，完整子句计分不变 ----
def test_189_partial_clause_no_crash():
    det = [{"pos": "r0", "obj": "circle|red"}]
    for cl in ({"shape": None, "color": "red", "pos": "r0"}, {"shape": "circle", "color": None, "pos": "r0"},
               {"shape": "circle", "color": None, "pos": "r8"}):
        r = MM.fuse_consistency([cl], det)
        assert r["verdict"] in ("ACCEPT", "DEFER", "REJECT")
    full = {"shape": "circle", "color": "red", "pos": "r0"}
    assert MM.fuse_consistency([full], det)["verdict"] == "ACCEPT"
    assert MM.fuse_consistency([full], [{"pos": "r4", "obj": "circle|red"}])["score"] == 0.4


# ---- #194：n_objects>9 立即报错，不死循环 ----
def test_194_over_capacity_raises():
    for n in (10, 50, -1):
        with pytest.raises(ValueError):
            SC.make_multimodal_scene(np.random.default_rng(7), 16, n)
    _, info = SC.make_multimodal_scene(np.random.default_rng(7), 16, 9)
    assert len({o["pos"] for o in info["labels"]}) == 9
