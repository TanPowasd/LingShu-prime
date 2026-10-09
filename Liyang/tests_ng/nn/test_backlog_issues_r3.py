# -*- coding: utf-8 -*-
"""上游老 issue 逐条复核（r3，#196 起）在 ng 上的回归测试（按 issue 原复现脚本写）。"""
import math
import os
import subprocess
import sys
import threading

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAN, INF = float("nan"), float("inf")


# ---- #196：NaN 绕过阈值判据静默「通过」 ----
@pytest.mark.parametrize("bad", [NAN, INF, -INF])
def test_196_judge_density_nonfinite_defers(bad):
    from lingshu_ng.nn.compat.hex_composite import judge_density
    m = {"score": 1.0, "composite": {"x": 1}}
    assert judge_density(m, bad, 0.5)["state"] == "DEFER"
    assert judge_density(m, 1.0, bad)["state"] == "DEFER"
    # 对照：正常值仍按阈值判
    assert judge_density(m, 0.1, 0.5)["state"] == "DEFER"
    assert judge_density(m, 1.0, 0.5)["state"] == "ACCEPT"


@pytest.mark.parametrize("fg,area", [(NAN, 10000), (100, NAN), (INF, 10000), (100, INF)])
def test_196_verdict_nonfinite_rejected(fg, area):
    from lingshu_ng.perception.verdict import assess
    D = {"clothing": "常服", "occlusion": "无遮挡", "contrast": "清晰"}
    with pytest.raises(ValueError):
        assess({"type": "head"}, D, part_fg_px=fg, part_area=area)


def test_196_verdict_zero_area_not_accept():
    from lingshu_ng.perception.verdict import assess
    D = {"clothing": "常服", "occlusion": "无遮挡", "contrast": "清晰"}
    r = assess({"type": "head"}, D, part_fg_px=1, part_area=0)
    assert r["verdict"] == "REJECT" and r["fg_ratio"] == 0.0
    assert assess({"type": "head"}, D, part_fg_px=5000, part_area=10000)["verdict"] == "ACCEPT"


# ---- #197：get_vec/set_vec 非原子读改写丢更新 → 提供锁内原子接口 ----
def _race(net, n_threads=2, rounds=50):
    v0 = float(net.get_vec()[0])
    barrier = threading.Barrier(n_threads)

    def worker():
        barrier.wait(timeout=10)
        for _ in range(rounds):
            net.apply_delta(0, 1.0)
            net.update_vec(lambda v: v + np.eye(1, v.size, 1).ravel())

    ts = [threading.Thread(target=worker) for _ in range(n_threads)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return v0


@pytest.mark.parametrize("mod,cls", [("hex_train", "HexNet"), ("hex_hier", "HexHierNet")])
def test_197_atomic_update_no_lost_update(mod, cls):
    import importlib
    C = getattr(importlib.import_module(f"lingshu_ng.nn.compat.{mod}"), cls)
    net = C(seed=7)
    before = net.get_vec().copy()
    _race(net, n_threads=4, rounds=50)
    after = net.get_vec()
    assert after[0] - before[0] == pytest.approx(200.0)
    assert after[1] - before[1] == pytest.approx(200.0)
    np.testing.assert_array_equal(after[2:], before[2:])


def test_197_get_vec_is_snapshot_and_set_vec_validates():
    from lingshu_ng.nn.compat.hex_train import HexNet
    net = HexNet(seed=7)
    v = net.get_vec()
    v[0] += 99.0
    assert net.get_vec()[0] != v[0]          # 快照隔离
    with pytest.raises(ValueError):
        net.set_vec(v[:-1])                   # 长度不符
    bad = net.get_vec(); bad[3] = NAN
    with pytest.raises(ValueError):
        net.set_vec(bad)                      # 非有限


# ---- #198：多 seed 件 id 跨进程（PYTHONHASHSEED）稳定 ----
def test_198_item_id_stable_across_processes():
    from lingshu_ng.gen.multi_seed import item_id
    code = "from lingshu_ng.gen.multi_seed import item_id; print(item_id('sid-1', 42))"
    outs = set()
    for hs in ("0", "1", "random"):
        env = dict(os.environ, PYTHONHASHSEED=hs, PYTHONPATH=REPO)
        outs.add(subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                                text=True, check=True).stdout.strip())
    assert outs == {str(item_id("sid-1", 42))}
    assert 0 <= item_id("sid-1", 42) < 10 ** 9


def test_198_render_rows_ids_deterministic(tmp_path):
    from lingshu_ng.gen.multi_seed import render_rows, item_id
    rows = render_rows([{"sid": "a", "prompt": "p"}, {"sid": "b", "prompt": "q"}], [1, 2], str(tmp_path))
    assert [r["id"] for r in rows] == [item_id(r["sid"], r["seed"]) for r in rows]
    assert len({r["id"] for r in rows}) == 4


def test_198_no_builtin_hash_ids_in_gen():
    import ast
    gen = os.path.join(REPO, "lingshu_ng", "gen")
    hits = []
    for fn in os.listdir(gen):
        if fn.endswith(".py"):
            tree = ast.parse(open(os.path.join(gen, fn), encoding="utf-8").read())
            hits += [f"{fn}:{n.lineno}" for n in ast.walk(tree)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "hash"]
    assert hits == []     # 代码里不得用内建 hash() 派生 id（docstring 提及不算）


# ---- #218：合法窗锚点必须落在自己声明的窗内（旧实现按 (x0,y0,x1,y1) 解包 (x0,x1,y0,y1) 窗） ----
@pytest.mark.parametrize("rad", [20, 48, 51, 80])
@pytest.mark.parametrize("size", [256, 512])
def test_218_anchor_inside_legal_window(rad, size):
    from lingshu_ng.gen import layout as LY
    for i in range(9):
        w = LY.legal_window(f"r{i}", size, rad, LY.overhang(size))
        if w.empty:
            continue
        ax, ay = w.anchor()
        assert w.contains(ax, ay) and w.x0 <= ax <= w.x1 and w.y0 <= ay <= w.y1, (i, w, (ax, ay))
        # 非方形格：x/y 轴不得对调——锚点 x 落在该格列区间、y 落在行区间
        xa, xb, ya, yb = LY.cell_rect(f"r{i}", size)
        assert xa - rad <= ax <= xb + rad and ya - rad <= ay <= yb + rad
