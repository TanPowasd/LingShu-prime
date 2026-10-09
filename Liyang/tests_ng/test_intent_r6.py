# -*- coding: utf-8 -*-
"""意图守卫 r6 分诊中「偏离旧意图、必须修」各项的 ng 侧回归（旧测试见 tests_ng/intent，旧断言一字不改）。"""
import copy
import math
import os
import subprocess
import sys
import threading

import pytest

from lingshu_ng.compat_engine import SpacetimeMemoryEngine
from lingshu_ng.types import ConditionSpace, MemoryLayer, Node

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_migrate_v17_coordinates_moves_semantic_keys_and_skips_bad_rows(tmp_path):
    import json
    import sqlite3
    p = str(tmp_path / "m.db")
    e = SpacetimeMemoryEngine(p)
    a = e.add_perception("坐标迁移样本甲", spatial_coordinates={"x": 1.0})
    b = e.add_perception("坐标迁移样本乙", spatial_coordinates={"x": 2.0})
    e.close()
    c = sqlite3.connect(p)
    c.execute("UPDATE nodes SET spatial_coordinates=? WHERE id=?",
              (json.dumps({"x": 1, "protocol_a": 0.5, "radical_r": 1, "neural_n": 2}), a.id))
    c.execute("UPDATE nodes SET spatial_coordinates=? WHERE id=?", ("[1, 2, 3]", b.id))   # 非 dict（#279）
    c.commit()
    c.close()
    e = SpacetimeMemoryEngine(p)                                    # 构造期迁移
    n = e._node(a.id)
    assert n.spatial_coordinates == {"x": 1}
    assert n.semantic_coordinates == {"protocol": {"concept": {"a": 0.5}}, "radical": {"r": 1}, "neural": {"n": 2}}
    assert e.migrate_v17_coordinates() == {"migrated_nodes": 0}      # 幂等
    assert any("[migration] v1.7" in (x.content or "") for x in e.store.get_layer_nodes(MemoryLayer.STRUCTURE))


def test_spatiotemporal_created_at_fallback_only_for_null():
    e = SpacetimeMemoryEngine()
    cs = ConditionSpace("测试台", "fixture", (100, 101), "synthetic")
    for nid, ts in (("center", None), ("same-created", None), ("explicit-zero", 0.0)):
        e.store.add_node(Node(id=nid, content="synthetic " + nid, modality="text", temporal_coordinate=ts,
                              spatial_coordinates={"x": 0.0}, condition_space=cs, created_at=100.0))
    assert [(n.id, d) for n, d in e.spatiotemporal_query("center", time_radius=0)] == [("same-created", 0.0)]


def test_world_shadow_seek_capped_by_remaining_distance():
    from lingshu_ng.world.world_learner import WorldLearner
    from lingshu_ng.world.world_model import UnifiedWorldModel
    for m in (UnifiedWorldModel(), WorldLearner()):
        assert m._apply_move((9.5, 1.5, 10.0), 0.8, (1.0, 0.0, 0.0), max_step=0.5) == (10.0, 1.5, 10.0)
        assert m._apply_move((9.5, 1.5, 10.0), 0.8, (1.0, 0.0, 0.0)) == (10.3, 1.5, 10.0)


np = pytest.importorskip("numpy")


def test_compat_apply_delta_legacy_whole_vector_form_is_atomic():
    from lingshu_ng.nn.compat.hex_hier import HexHierNet
    from lingshu_ng.nn.compat.hex_train import HexNet
    for net in (HexNet(seed=7), HexHierNet()):
        v0 = net.get_vec().copy()
        d = np.zeros_like(v0)
        d[-1] = 0.001
        ts = [threading.Thread(target=lambda: [net.apply_delta(d) for _ in range(50)]) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert abs(float(net.get_vec()[-1] - v0[-1]) - 0.4) < 1e-9
        net.apply_delta([0], 1.0)                                   # ng 形 (idx, delta) 仍可用
        c = copy.deepcopy(net)                                      # 锁不参与复制
        assert np.array_equal(c.get_vec(), net.get_vec())


def test_compat_param_attribute_is_live_view():
    from lingshu_ng.nn.compat.hex_hier import HexHierNet
    net = HexHierNet(n_kernels=1, stacked=False, seed=7)
    net.head[:] = 0
    net.head[1, -1] = 8
    assert net.head[1, -1] == 8 and float(np.abs(net.head).sum()) == 8


def test_compat_selfsup_reports_eval_mask_init_final_and_train_curve():
    from lingshu_ng.nn.compat.hex_train import HexNet, pretrain_selfsup
    rng = np.random.default_rng(3)
    x = rng.random((6, 8, 8, 3))
    r = pretrain_selfsup(HexNet(n_class=2, seed=2), x, steps=5, seed=7)
    assert len(r["curve"]) == 5 and len(r["probe_curve"]) == 6 and r["curve"] == r["batch_curve"]


def test_gen_hex_composite_alias_is_same_module():
    code = ("import sys; sys.path[:0] = [%r]\n"
            "import lingshu.gen, lingshu.nn\n"
            "from lingshu_ng.nn.compat import install_legacy_aliases\n"
            "done = install_legacy_aliases()\n"
            "import lingshu.gen.hex_composite as g, lingshu.nn.hex_composite as n\n"
            "assert g is n and 'lingshu.gen.hex_composite' in done and hasattr(g, 'SCENE_RGB')\n" % REPO)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=REPO)
    assert out.returncode == 0, out.stderr[-800:]


def test_draw_object_legacy_helper():
    from lingshu_ng.nn.compat.hex_text import _draw_object
    img = np.zeros((48, 48, 3), dtype=np.uint8)
    cx, cy = _draw_object(img, "circle", "red", 1, 1, 48, np.random.default_rng(0))
    assert 20 <= cx <= 28 and 20 <= cy <= 28 and int((img[..., 0] > 200).sum()) > 0
