"""批量光栅（raster.rasterize）对照逐三角形参照版 + 盒快路径 / 帧缓冲复用的等价性。"""
import numpy as np
import pytest

from lingshu_ng.world import geometry as G
from lingshu_ng.world.camera import Camera
from lingshu_ng.world.raster import fill_rgb, new_frame, rasterize, rasterize_reference

from .test_raster import random_cam, random_scene


def _same(a, b):
    return (np.array_equal(a.ids, b.ids) and np.array_equal(a.color, b.color)
            and np.array_equal(np.isinf(a.depth), np.isinf(b.depth)))


@pytest.mark.parametrize("seed", range(60))
@pytest.mark.parametrize("cull", [True, False])
def test_batched_equals_reference(seed, cull):
    """性质：批量版与逐三角形版逐像素同 id / 同色 / 同覆盖，深度在浮点精度内一致。"""
    rng = np.random.default_rng(1000 + seed)
    mesh = random_scene(rng, int(rng.integers(1, 10)))
    cam = random_cam(rng, int(rng.integers(16, 160)), int(rng.integers(16, 120)))
    a = rasterize(mesh, cam, cull_backfaces=cull)
    b = rasterize_reference(mesh, cam, cull_backfaces=cull)
    assert _same(a, b)
    hit = np.isfinite(b.depth)
    assert np.allclose(a.depth[hit], b.depth[hit], rtol=1e-12, atol=0)


def test_batched_near_plane_and_slivers():
    """跨近平面的大地面、极细长条、整屏大三角形：覆盖与参照逐像素一致。"""
    cam = Camera.look_at((0.3, 1.0, -4.0), (0.0, 0.0, 6.0), width=97, height=71)
    meshes = [G.primitive_mesh("box", (0, -0.05, 5), (40, 0.1, 40), (90, 160, 90), 0),
              G.primitive_mesh("box", (0.2, 0.5, 3), (6.0, 0.002, 0.003), (200, 30, 30), 1),
              G.primitive_mesh("box", (-0.4, 0.7, 2.0), (0.0005, 3.0, 0.0005), (30, 30, 200), 2),
              G.primitive_mesh("pyramid", (0, 0.4, 0.4), (3, 2, 3), (220, 200, 40), 3)]
    m = G.merge_meshes(meshes)
    for cull in (True, False):
        a, b = rasterize(m, cam, cull_backfaces=cull), rasterize_reference(m, cam, cull_backfaces=cull)
        assert _same(a, b)


def test_frame_reuse_and_non_contiguous():
    """传入 frame 时就地写；非连续 frame 也正确（回退路径）。"""
    rng = np.random.default_rng(7)
    mesh, cam = random_scene(rng, 5), random_cam(rng, 64, 48)
    ref = rasterize_reference(mesh, cam)
    big = new_frame(cam.with_size(128, 48))
    from lingshu_ng.world.raster import Frame
    view = Frame(big.color[:, ::2], big.depth[:, ::2], big.ids[:, ::2])
    out = rasterize(mesh, cam, frame=view)
    assert out is view and _same(view, ref)


def test_fill_rgb_matches_broadcast():
    img = np.zeros((7, 5, 3), np.uint8)
    fill_rgb(img[3:], (10, 20, 30))
    assert (img[3:] == [10, 20, 30]).all() and (img[:3] == 0).all()
    fill_rgb(img[7:], (1, 2, 3))      # 空区域不报错


@pytest.mark.parametrize("seed", range(20))
def test_box_fast_path_equals_generic(seed):
    """非退化盒快路径（单位盒面表 + 预计算着色）与逐面定向路径逐位一致；退化盒走旧路径。"""
    rng = np.random.default_rng(seed)
    for _ in range(50):
        c = rng.uniform(-50, 50, 3)
        s = rng.uniform(0, 5, 3) * (rng.random(3) > 0.1) * (1e-15 if rng.random() < 0.2 else 1.0)
        v, f = G.box_mesh(c, s)
        raw_v = c + G._BOX_SIGN * (s / 2.0)
        f_ref = G._orient_outward(raw_v, G._BOX_RAW, c)
        assert np.array_equal(v, raw_v) and np.array_equal(f, f_ref)
        m = G.primitive_mesh("box", c, s, (200, 100, 50), 3)
        cols = G._shade((200, 100, 50), G.shade_factors(G.face_normals(raw_v, f_ref), "box"))
        assert np.array_equal(m.faces, f_ref) and np.array_equal(m.face_colors, cols)


def test_boxes_mesh_equals_merged_primitives():
    rng = np.random.default_rng(3)
    n = 9
    c, s = rng.uniform(-3, 3, (n, 3)), rng.uniform(0.1, 2, (n, 3))
    col, ids = rng.integers(0, 256, (n, 3)), np.arange(n) * 10
    a = G.boxes_mesh(c, s, col, ids)
    b = G.merge_meshes(G.primitive_mesh("box", c[i], s[i], tuple(col[i]), int(ids[i])) for i in range(n))
    for f in ("vertices", "faces", "face_colors", "face_ids"):
        assert np.array_equal(getattr(a, f), getattr(b, f)), f
    s[4, 1] = 0.0                       # 含退化盒 → 逐个回退，结果仍一致
    a = G.boxes_mesh(c, s, col, ids)
    b = G.merge_meshes(G.primitive_mesh("box", c[i], s[i], tuple(col[i]), int(ids[i])) for i in range(n))
    assert np.array_equal(a.faces, b.faces) and np.array_equal(a.face_colors, b.face_colors)


def test_cross3_equals_numpy():
    rng = np.random.default_rng(0)
    a, b = rng.normal(size=(50, 3)), rng.normal(size=(50, 3))
    assert np.array_equal(G.cross3(a, b), np.cross(a, b))


def test_axis_aligned_camera_flat_edges_equal_reference():
    """俯仰 0 的相机下盒的水平棱投影成精确水平边（s=0 分支）：覆盖仍与参照逐像素一致。"""
    for yaw in (0.0, 0.3, -1.1):
        cam = Camera.from_yaw_pitch((0.2, 1.2, -6.0), yaw, 0.0, width=120, height=90)
        m = G.merge_meshes([G.primitive_mesh("box", (0, 1.2, 0), (2, 2, 2), (200, 0, 0), 0),
                            G.primitive_mesh("box", (0.5, 0.5, 2), (4, 1, 1), (0, 200, 0), 1),
                            G.primitive_mesh("pyramid", (-1, 1, 1), (1, 2, 1), (0, 0, 200), 2)])
        for cull in (True, False):
            assert _same(rasterize(m, cam, cull_backfaces=cull), rasterize_reference(m, cam, cull_backfaces=cull))


@pytest.mark.parametrize("ulp", [1e-3, 1.0])
def test_band_path_alone_equals_reference(monkeypatch, ulp):
    """把误差界放大到让「不确定带」吞掉大部分/全部像素：逐像素参照判定路径单独也与参照一致。"""
    from lingshu_ng.world import raster
    monkeypatch.setattr(raster, "_ULP", ulp)
    for seed in range(8):
        rng = np.random.default_rng(500 + seed)
        mesh, cam = random_scene(rng, 6), random_cam(rng, 70, 50)
        assert _same(rasterize(mesh, cam), rasterize_reference(mesh, cam))


def test_pristine_frame_shortcut_and_reset():
    """全空帧捷径（跳过旧深度比较）与常规路径一致；reset 后复用缓冲结果不变；二次叠画走常规路径。"""
    rng = np.random.default_rng(11)
    a_mesh, cam = random_scene(rng, 5), random_cam(rng, 90, 70)
    b_mesh = random_scene(rng, 4)
    fr = new_frame(cam)
    assert fr.pristine
    rasterize(a_mesh, cam, frame=fr)
    assert not fr.pristine
    rasterize(b_mesh, cam, frame=fr)                    # 叠画：必须与旧深度比较
    ref = rasterize_reference(b_mesh, cam, frame=rasterize_reference(a_mesh, cam))
    assert _same(fr, ref)
    fr.reset((0, 0, 0))
    assert fr.pristine and np.isinf(fr.depth).all() and (fr.ids == -1).all()
    assert _same(rasterize(a_mesh, cam, frame=fr), rasterize_reference(a_mesh, cam))
