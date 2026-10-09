import numpy as np
import pytest

from lingshu_ng.world import geometry as G
from lingshu_ng.world.camera import Camera
from lingshu_ng.world.raster import rasterize


PRIMS = [("box", G.box_mesh), ("pyramid", G.pyramid_mesh), ("sphere", G.ellipsoid_mesh)]


@pytest.mark.parametrize("name,fn", PRIMS)
def test_normals_point_outward(name, fn):
    rng = np.random.default_rng(0)
    for _ in range(20):
        c, s = rng.uniform(-5, 5, 3), rng.uniform(0.1, 4, 3)
        v, f = fn(c, s)
        n = G.face_normals(v, f)
        assert np.allclose(np.linalg.norm(n, axis=1), 1.0)
        cen = v[f].mean(axis=1)
        inside = c if name != "pyramid" else c - [0, s[1] / 4, 0]
        assert np.all(np.einsum("ij,ij->i", n, cen - inside) > 0)


@pytest.mark.parametrize("name,fn", PRIMS)
def test_meshes_are_closed(name, fn):
    """每条有向边恰好出现一次且其反向边也出现一次（闭合、绕序一致的流形）。"""
    v, f = fn((0, 0, 0), (1, 2, 3))
    edges = [(a, b) for t in f for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))]
    es = set(edges)
    assert len(es) == len(edges)
    assert all((b, a) in es for a, b in edges)


def test_box_extent_and_pyramid_apex():
    v, _ = G.box_mesh((1, 2, 3), (2, 4, 6))
    assert np.allclose(v.min(0), [0, 0, 0]) and np.allclose(v.max(0), [2, 4, 6])
    v, _ = G.pyramid_mesh((0, 1, 0), (2, 2, 2))
    assert np.allclose(v[4], [0, 2, 0]) and np.allclose(v[:4, 1], 0)


def test_backface_mask_box_axis_views():
    m = G.primitive_mesh("box", (0, 0, 5), (1, 1, 1), (100, 100, 100))
    cam = Camera.look_at((0, 0, 0), (0, 0, 5))
    n = G.face_normals(m.vertices, m.faces)
    keep = G.backface_mask(m, cam)
    assert np.allclose(n[keep], [0, 0, -1])                       # 正对：只剩前面 2 个三角
    cam2 = Camera.look_at((3, 3, 0), (0, 0, 5))                    # 右上前方：前/右/顶 3 面
    k2 = G.backface_mask(m, cam2)
    assert {tuple(np.round(x).astype(int)) for x in n[k2]} == {(0, 0, -1), (1, 0, 0), (0, 1, 0)}


@pytest.mark.parametrize("seed", range(15))
def test_culling_never_changes_zbuffer_result(seed):
    """性质：闭合凸体集合上，背面剔除只是加速——剔除/不剔除的 id 与深度缓冲逐像素相同。"""
    rng = np.random.default_rng(seed)
    kinds = ["box", "pyramid", "sphere"]
    mesh = G.merge_meshes(G.primitive_mesh(kinds[i % 3], rng.uniform(-2, 2, 3),
                                           rng.uniform(0.3, 2, 3), (200, 50, 50), i)
                          for i in range(5))
    eye = rng.normal(size=3)
    eye = eye / np.linalg.norm(eye) * rng.uniform(6, 12)
    cam = Camera.look_at(eye, (0, 0, 0), width=96, height=72)
    a = rasterize(mesh, cam, cull_backfaces=True)
    b = rasterize(mesh, cam, cull_backfaces=False)
    assert np.array_equal(a.ids, b.ids)
    assert np.array_equal(a.depth, b.depth)


def test_shade_factors_match_legacy_table():
    m = G.primitive_mesh("box", (0, 0, 0), (1, 1, 1), (200, 100, 50))
    n = G.face_normals(m.vertices, m.faces)
    expect = {(0, 1, 0): 1.15, (0, -1, 0): 0.6, (1, 0, 0): 0.85, (-1, 0, 0): 0.85,
              (0, 0, 1): 0.95, (0, 0, -1): 0.95}
    for nn, col in zip(n, m.face_colors):
        k = expect[tuple(np.round(nn).astype(int))]
        assert tuple(col) == tuple(min(255, int(c * k)) for c in (200, 100, 50))
    s = G.primitive_mesh("sphere", (0, 0, 0), (1, 1, 1), (10, 20, 30))
    assert (s.face_colors == [10, 20, 30]).all()


def test_merge_offsets_ids():
    a = G.primitive_mesh("box", (0, 0, 0), (1, 1, 1), (1, 1, 1), 3)
    b = G.primitive_mesh("pyramid", (5, 0, 0), (1, 1, 1), (1, 1, 1), 7)
    m = G.merge_meshes([a, b])
    assert m.n_faces == a.n_faces + b.n_faces
    assert m.faces.max() == len(m.vertices) - 1
    assert set(m.face_ids) == {3, 7}
    assert G.merge_meshes([]).n_faces == 0
