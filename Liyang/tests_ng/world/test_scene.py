import numpy as np
import pytest

from lingshu_ng.world import scene as SC
from lingshu_ng.world.camera import Camera
from lingshu_ng.world.validate import NonFiniteError


def rand_entity(rng, name):
    return SC.Entity(name, rng.uniform(-5, 5, 3), rng.uniform(0.2, 2, 3))


@pytest.mark.parametrize("seed", range(10))
def test_converse_relations_hold_symmetrically(seed):
    """性质：R(a,b) ⇔ R⁻¹(b,a)（关系方向写反的缺陷类在这里必红）。"""
    rng = np.random.default_rng(seed)
    for _ in range(200):
        a, b = rand_entity(rng, "a"), rand_entity(rng, "b")
        for r, inv in SC.CONVERSE.items():
            if inv is not None:
                assert SC.relation_holds(a, r, b) == SC.relation_holds(b, inv, a), r


def test_relation_directions_explicit():
    a = SC.Entity("a", (0, 0.5, 5), (1, 1, 1))
    b = SC.Entity("b", (2, 0.5, 8), (1, 1, 1))
    assert SC.relation_holds(a, "left_of", b) and not SC.relation_holds(a, "right_of", b)
    assert SC.relation_holds(a, "in_front", b) and SC.relation_holds(b, "behind", a)
    top = SC.Entity("top", (0, 1.5, 5), (1, 1, 1))
    assert SC.relation_holds(top, "above", a) and SC.relation_holds(a, "below", top)
    assert SC.relation_holds(top, "on", a)
    with pytest.raises(KeyError):
        SC.relation_holds(a, "beside", b)


def test_relations_are_mutually_exclusive_pairs():
    rng = np.random.default_rng(1)
    for _ in range(300):
        a, b = rand_entity(rng, "a"), rand_entity(rng, "b")
        rs = set(SC.relations_between(a, b))
        assert not {"left_of", "right_of"} <= rs and not {"in_front", "behind"} <= rs
        assert not {"above", "below"} <= rs


@pytest.mark.parametrize("rel", ["left_of", "right_of", "in_front", "behind", "above", "below", "on"])
def test_enforce_relation_makes_it_hold_and_preserves_valid(rel):
    rng = np.random.default_rng(2)
    for _ in range(100):
        a, b = rand_entity(rng, "a"), rand_entity(rng, "b")
        held = SC.relation_holds(a, rel, b)
        new = SC.enforce_relation(a, rel, b)
        if held:
            assert np.array_equal(new, a.pos)
        a2 = SC.Entity("a", new, a.size)
        assert SC.relation_holds(a2, rel, b)
        assert np.array_equal(SC.enforce_relation(a2, rel, b), new)   # 幂等


def test_view_relation_uses_camera_frame():
    a, b = SC.Entity("a", (-1, 0, 5)), SC.Entity("b", (1, 0, 5))
    front = Camera.look_at((0, 0, 0), (0, 0, 5))
    back = Camera.look_at((0, 0, 10), (0, 0, 5))
    assert SC.view_relation(front, a, b)["left_of"]
    assert SC.view_relation(back, a, b)["right_of"]          # 从背面看左右互换
    c = SC.Entity("c", (0, 0, 2))
    assert SC.view_relation(front, c, a)["in_front"] and SC.view_relation(back, c, a)["behind"]


def test_bbox_overlap_scale_invariant():
    rng = np.random.default_rng(0)
    for _ in range(500):
        def box():
            x, y = rng.uniform(0, 400, 2)
            return (x, y, x + rng.uniform(1, 200), y + rng.uniform(1, 200))
        a, b = box(), box()
        for s in (1e-3, 1 / 640, 7.0):
            sa, sb = tuple(v * s for v in a), tuple(v * s for v in b)
            assert SC.bbox_relation(a, b) == SC.bbox_relation(sa, sb)
            assert abs(SC.bbox_overlap_ratio(a, b) - SC.bbox_overlap_ratio(sa, sb)) < 1e-9
    assert abs(SC.bbox_overlap_ratio((10, 10, 10.8, 10.8), (10.1, 10.1, 10.9, 10.9)) - 0.765625) < 1e-9


def test_bbox_relation_directions():
    assert SC.bbox_relation((0, 0, 10, 10), (0, 50, 10, 60)) == "above"     # 图像 y 向下
    assert SC.bbox_relation((0, 50, 10, 60), (0, 0, 10, 10)) == "below"
    assert SC.bbox_relation((0, 0, 10, 10), (50, 0, 60, 10)) == "left_of"
    assert SC.bbox_relation((50, 0, 60, 10), (0, 0, 10, 10)) == "right_of"
    assert SC.bbox_relation((0, 0, 100, 100), (10, 10, 20, 20)) == "contains"
    assert SC.bbox_relation((10, 10, 20, 20), (0, 0, 100, 100)) == "inside"


def test_rng_injection_deterministic_and_seed_sensitive():
    a = SC.make_rng(7).uniform(size=10)
    assert np.array_equal(a, SC.make_rng(7).uniform(size=10))
    assert not np.array_equal(a, SC.make_rng(8).uniform(size=10))
    assert np.array_equal(SC.make_rng().uniform(size=3), SC.make_rng(SC.DEFAULT_SEED).uniform(size=3))
    for bad in (None, 1.5, "1", True):
        with pytest.raises(NonFiniteError):
            SC.make_rng(bad)


def test_no_module_level_rng_in_world_package():
    """静态守卫：world 包内不得出现 random.Random(常量)/np.random.seed/全局 np.random.* 采样。"""
    import pathlib
    import re
    root = pathlib.Path(SC.__file__).parent
    pat = re.compile(r"np\.random\.(seed|rand|uniform|normal|randint)\(|random\.Random\(\d+\)")
    for f in root.glob("*.py"):
        assert not pat.search(f.read_text(encoding="utf-8")), f.name


def test_edge_store_supersedes_stale_functional_edge():
    """world-01：A 改追 C 后，A 的 seek→B 边须被取代，当前目标只有 C。"""
    es = SC.EdgeStore()
    es.observe("A", "seek", "B", 1.0, tick=1)
    es.observe("A", "seek", "B", 0.9, tick=5)          # 同边刷新，不新增
    assert len(es.edges) == 1 and es.edges[0].confidence == 0.9
    es.observe("A", "seek", "C", 0.7, tick=9)
    assert es.current_target("A") == ("seek", "C")
    assert [e.target for e in es.active("A")] == ["C"]
    assert es.edges[0].superseded_at == 9                # 旧边保留可审计
    es.observe("A", "flee", "D", 0.6, tick=12)          # 同族不同关系也取代
    assert es.current_target("A") == ("flee", "D")
    es.observe("A", "near", "E", 0.5, tick=13)          # 非函数型关系可并存
    assert {e.relation for e in es.active("A")} == {"flee", "near"}
