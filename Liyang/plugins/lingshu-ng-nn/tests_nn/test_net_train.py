# -*- coding: utf-8 -*-
"""net / train：解析梯度、增量扰动等价、原子参数接口、确定性 RNG、训练行为。"""
import threading

import numpy as np
import pytest

from lingshu_ng.nn import infogap, train
from lingshu_ng.nn.net import HierHexNet, ParamStore, ShallowHexNet, as_rng, ce_from_logits, softmax

CFGS = [dict(), dict(stacked=False), dict(deep_norm=True), dict(deep_norm=True, amp_sep=True, amp_log=True),
        dict(n_kernels=4, n_kernels2=3, conv2_mode="asym", prior="extended")]


def _data(seed=1, b=5):
    g = np.random.default_rng(seed)
    return g.normal(size=(b, 6, 7, 3)), g.integers(0, 9, b)


@pytest.mark.parametrize("kw", CFGS, ids=str)
def test_analytic_gradient_matches_fd(kw):
    x, y = _data()
    net = HierHexNet(rng=3, **kw)
    # 随机核：避开手写边缘核在钳制边界上产生的精确 0 预激活（lrelu 拐点，差分不可比）
    net.params.set_vec(np.random.default_rng(9).normal(0, 0.5, net.params.size))
    c = net.forward_cache(x)
    dl = softmax(c["logits"]); dl[np.arange(len(y)), y] -= 1; dl /= len(y)
    g = net.backward(c, dl)
    v = net.params.get_vec()
    ok = 0
    for i in range(v.size):
        vals = []
        for e in (1e-6, -1e-6):
            vp = v.copy(); vp[i] += e; net.params.set_vec(vp)
            vals.append(ce_from_logits(net.forward_cache(x)["logits"], y))
        net.params.set_vec(v)
        ok += abs((vals[0] - vals[1]) / 2e-6 - g[i]) < 1e-5
    assert ok == v.size


@pytest.mark.parametrize("kw", CFGS, ids=str)
def test_perturb_equals_full_recompute(kw):
    x, _ = _data(2)
    net = HierHexNet(rng=5, **kw)
    c = net.forward_cache(x)
    v = net.params.get_vec()
    for i in range(v.size):
        vp = v.copy(); vp[i] += 1e-3; net.params.set_vec(vp)
        full = net.forward_cache(x)["logits"]
        net.params.set_vec(v)
        assert np.max(np.abs(net.perturbed_logits(c, i, 1e-3) - full)) < 1e-12


def test_commit_keeps_cache_in_sync():
    x, _ = _data(3)
    for net in (HierHexNet(rng=1), ShallowHexNet(n_class=4, rng=1)):
        c = net.forward_cache(x)
        g = np.random.default_rng(0)
        for i in g.choice(net.params.size, 40):
            net.commit(c, int(i), float(g.normal()) * 0.01)
        assert np.max(np.abs(c["logits"] - net.forward_cache(x)["logits"])) < 1e-12


def test_param_store_atomic_under_threads():
    ps = ParamStore([("w", np.zeros(4))])

    def work():
        for _ in range(50):
            ps.apply_delta(1, 1.0)
            ps.update_vec(lambda v: v + np.array([1.0, 0, 0, 0]))

    th = [threading.Thread(target=work) for _ in range(8)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    v = ps.get_vec()
    assert v[0] == 400 and v[1] == 400


def test_param_store_rejects_bad_vectors():
    ps = ParamStore([("w", np.zeros(3))])
    with pytest.raises(ValueError):
        ps.set_vec(np.zeros(4))
    with pytest.raises(ValueError):
        ps.set_vec(np.array([0.0, np.nan, 0.0]))
    with pytest.raises(ValueError):
        ps.view("w")[0] = 1.0


def test_rng_must_be_explicit_and_deterministic():
    with pytest.raises(TypeError):
        as_rng(None)
    a = HierHexNet(rng=11).params.get_vec()
    b = HierHexNet(rng=np.random.default_rng(11)).params.get_vec()
    assert np.array_equal(a, b)


def test_train_hier_reduces_loss_and_is_deterministic():
    g = np.random.default_rng(0)
    x = g.normal(size=(32, 5, 5, 3))
    obj = g.integers(0, 9, 32)
    x[np.arange(32), :, :, obj % 3] += 2.0          # 颜色可分
    shape = obj // 3
    r1 = train.train_hier(HierHexNet(rng=7), x, obj, shape, steps=25, samples_per_step=20, lr=0.05, batch=16, rng=3)
    r2 = train.train_hier(HierHexNet(rng=7), x, obj, shape, steps=25, samples_per_step=20, lr=0.05, batch=16, rng=3)
    assert r1["curve"] == r2["curve"]
    assert np.mean(r1["curve"][-5:]) < np.mean(r1["curve"][:5])


def test_seq_and_par_modes_differ_only_in_semantics():
    g = np.random.default_rng(1)
    x, obj = g.normal(size=(12, 5, 5, 3)), g.integers(0, 9, 12)
    plan = train.make_plan(12, 3, 6, 30, 7, HierHexNet(rng=1).params.size)
    for mode in ("seq", "par"):
        curve = train.execute_plan(HierHexNet(rng=1), x, obj, obj // 3, plan, mode=mode)
        assert curve.shape == (3,) and np.all(np.isfinite(curve))


def test_execute_plan_rejects_mismatch():
    net = HierHexNet(n_kernels=4, n_kernels2=4, rng=1)
    plan = train.make_plan(8, 2, 4, 64, 7, 375)
    with pytest.raises(ValueError, match="n_params"):
        train.execute_plan(net, np.zeros((8, 5, 5, 3)), np.zeros(8, int), np.zeros(8, int), plan)


def test_joint_loss_groups_by_shape():
    logits = np.zeros((1, 9))
    logits[0, 0:3] = 5.0                       # 形状 0 的三个物体
    lo = train.joint_hier_loss(logits, np.array([0]), np.array([0]))
    hi = train.joint_hier_loss(logits, np.array([0]), np.array([1]))
    assert lo < hi


def test_joint_dlogits_matches_fd():
    g = np.random.default_rng(4)
    lg, o, s = g.normal(size=(4, 9)), g.integers(0, 9, 4), g.integers(0, 3, 4)
    d = train.joint_dlogits(softmax(lg), o, s)
    for i, j in [(0, 0), (1, 4), (3, 8), (2, 2)]:
        lp = lg.copy(); lp[i, j] += 1e-6
        lm = lg.copy(); lm[i, j] -= 1e-6
        fd = (train.joint_hier_loss(lp, o, s) - train.joint_hier_loss(lm, o, s)) / 2e-6
        assert abs(fd - d[i, j]) < 1e-6


def test_infogap_growth_revert_restores_all_params():
    g = np.random.default_rng(5)
    x = g.normal(size=(16, 6, 6, 1))
    y = g.integers(0, 2, 16)
    net = ShallowHexNet(n_kernels=3, n_class=2, rng=1)
    r = infogap.train_infogap(net, x, y, rng=2, dead_zone_ratio=0.0, stall_patience=1, verify_steps=1,
                              retain_gain=0.0, max_growth=2, max_steps=6, samples_per_step=6, batch=8)
    assert r["reverts"] >= 1 and net.K == 3


def test_selfsup_probe_curve_is_fixed_probe_and_drops():
    """自监督重建：curve 在固定探针（训练前抽定的样本+掩码）上度量，init=训练前损失，逐步不升。
    画幅内晶格上掩码间噪声大于 20 步降幅，换掩码的首末比较不可靠（旧 test_selfsup_recon_loss_drops 根因）。"""
    from lingshu_ng.nn import infogap
    from lingshu_ng.nn.hexgrid import image_to_lattice
    from lingshu_ng.nn.net import ShallowHexNet
    g = np.random.default_rng(3)
    imgs = []
    for i in range(8):
        im = np.zeros((32, 32), dtype=np.float64)
        if i % 2 == 0:
            im[:, ::4] = 255
        else:
            im[::4, :] = 255
        imgs.append(image_to_lattice(im + g.integers(0, 30, im.shape), 16)[0][..., :1] / 255.0)
    lat = np.stack(imgs)
    lat = (lat - lat.mean()) / lat.std()
    for seed in (0, 7):
        net = ShallowHexNet(4, 8, 2, rng=2)
        r = infogap.pretrain_selfsup(net, lat, rng=seed, steps=20)
        assert len(r["curve"]) == 21 and len(r["batch_curve"]) == 20
        assert r["init"] == r["curve"][0] and r["final"] == r["curve"][-1]
        assert all(b <= a + 1e-9 for a, b in zip(r["curve"], r["curve"][1:]))
        assert r["final"] < r["init"]


@pytest.mark.parametrize("screen", [True, False])
def test_search_one_forward_per_visited_node(screen):
    """递归搜索：根域与全图能量共用前向，兄弟粗筛的子域前向随子域复用——前向次数 = 访问节点数。"""
    from lingshu_ng.nn import search
    net = HierHexNet(rng=7)
    calls = {"n": 0}
    orig = net.forward_cache

    def counted(x):
        calls["n"] += 1
        return orig(x)
    net.forward_cache = counted
    lat = np.random.default_rng(1).normal(size=(1, 36, 32, 3))
    th = {"th_conf": 0.99, "th_margin": 9.0, "th_reject": 0.0, "share_mult": 0.0}   # 全部 DEFER 至最深
    _, st = search.recursive_search(net, lat, max_depth=2, th=th, sibling_screen=screen)
    assert st["visited"] == 1 + 9 + 81 if not screen else st["visited"] >= 10
    assert calls["n"] == st["visited"]
