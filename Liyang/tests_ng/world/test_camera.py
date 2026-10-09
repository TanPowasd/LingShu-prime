import math

import numpy as np
import pytest

from lingshu_ng.world import camera as C
from lingshu_ng.world.validate import NonFiniteError


def random_camera(rng, w=640, h=480):
    eye = rng.uniform(-20, 20, 3)
    target = eye + rng.normal(size=3) * rng.uniform(1, 10)
    return C.Camera.look_at(eye, target, fov_deg=rng.uniform(20, 120), width=w, height=h)


@pytest.mark.parametrize("seed", range(50))
def test_unproject_project_round_trip(seed):
    """性质：任意相机，相机前方点 P：unproject(project(P), depth(P)) == P。"""
    rng = np.random.default_rng(seed)
    cam = random_camera(rng)
    pc = np.column_stack([rng.uniform(-30, 30, 200), rng.uniform(-30, 30, 200),
                          rng.uniform(0.2, 80, 200)])
    P = C.camera_to_world(cam, pc)
    uv, z = C.project(cam, P)
    assert np.all(z > cam.near)
    back = C.unproject(cam, uv, z)
    assert np.max(np.abs(back - P)) < 1e-9 * max(1.0, np.max(np.abs(P)))


@pytest.mark.parametrize("seed", range(20))
def test_screen_round_trip(seed):
    """反向往返：像素 + 深度 → 世界 → 像素。"""
    rng = np.random.default_rng(100 + seed)
    cam = random_camera(rng)
    uv = np.column_stack([rng.uniform(0, cam.width, 100), rng.uniform(0, cam.height, 100)])
    z = rng.uniform(0.5, 50, 100)
    uv2, z2 = C.project(cam, C.unproject(cam, uv, z))
    assert np.max(np.abs(uv2 - uv)) < 1e-8 and np.max(np.abs(z2 - z)) < 1e-9


def test_world_camera_inverse_and_orthonormal():
    rng = np.random.default_rng(7)
    for _ in range(30):
        cam = random_camera(rng)
        R = cam.rotation
        assert np.allclose(R @ R.T, np.eye(3)) and np.isclose(np.linalg.det(R), 1.0)
        P = rng.normal(size=(10, 3)) * 10
        assert np.allclose(C.camera_to_world(cam, C.world_to_camera(cam, P)), P)


def test_look_at_target_on_optical_axis():
    rng = np.random.default_rng(3)
    for _ in range(50):
        eye, tgt = rng.uniform(-10, 10, 3), rng.uniform(-10, 10, 3)
        cam = C.Camera.look_at(eye, tgt, width=400, height=300)
        u, v = C.project_point(cam, tgt)
        assert abs(u - 200) < 1e-8 and abs(v - 150) < 1e-8
        assert np.isclose(C.depth(cam, tgt), np.linalg.norm(tgt - eye))


def test_look_at_basis_no_roll():
    """look_at 的相机右轴水平（无滚转），右=up×fwd，上=fwd×右。"""
    cam = C.Camera.look_at((1, 2, 3), (4, 0, 9))
    r, u, f = cam.rotation
    assert abs(r[1]) < 1e-12
    assert np.allclose(r, np.cross([0, 1, 0], f) / np.linalg.norm(np.cross([0, 1, 0], f)))
    assert np.allclose(u, np.cross(f, r))


def test_depth_is_camera_z_not_world_z():
    cam = C.Camera.look_at((0, 1.2, 20), (0, 1.2, 0))
    assert np.isclose(C.depth(cam, (0, 1.2, 10)), 10) and np.isclose(C.depth(cam, (0, 1.2, 2)), 18)


def test_matches_legacy_camera3d_numerics():
    """与旧 Camera3D（修复版）逐点一致：保证 compat 位姿语义不漂移。"""
    old = pytest.importorskip("lingshu.world.world3d")
    if getattr(old, "__ng_compat__", False):
        pytest.skip("legacy aliases installed")
    rng = np.random.default_rng(11)
    for _ in range(40):
        eye, tgt = tuple(rng.uniform(-10, 10, 3)), tuple(rng.uniform(-10, 10, 3))
        oc = old.Camera3D.look_at(eye, tgt, fov_deg=55)
        nc = C.Camera.look_at(eye, tgt, fov_deg=55, width=800, height=600)
        for p in rng.uniform(-15, 15, (20, 3)):
            a = oc.to_camera(tuple(p))
            assert np.allclose(a, C.world_to_camera(nc, p), atol=1e-9)
            op = oc.project(tuple(p), 800, 600)
            np_ = C.project_point(nc, p)
            assert (op is None) == (np_ is None)
            if op:
                assert np.allclose(op, np_, atol=1e-7)


def test_behind_camera_not_projected():
    cam = C.Camera()
    assert C.project_point(cam, (0, 1.2, -5)) is None
    uv, z = C.project(cam, [(0, 1.2, -5), (0, 1.2, 5)])
    assert np.isnan(uv[0]).all() and np.isfinite(uv[1]).all() and z[0] < 0


@pytest.mark.parametrize("seed", range(10))
def test_bbox_to_world_reprojects_to_bbox_center(seed):
    rng = np.random.default_rng(seed)
    cam = random_camera(rng, 800, 600)
    cx, cy, w = rng.uniform(100, 700), rng.uniform(100, 500), rng.uniform(5, 200)
    P = C.bbox_to_world(cam, (cx - w / 2, cy - 10, cx + w / 2, cy + 10), 1.5)
    u, v = C.project_point(cam, P)
    assert abs(u - cx) < 1e-7 and abs(v - cy) < 1e-7
    assert np.isclose(C.depth(cam, P), cam.focal * 1.5 / w)


def test_pixel_rays_hit_unprojected_points():
    cam = C.Camera.look_at((2, 3, -4), (0, 0, 5), width=320, height=240)
    uv = np.array([[10.5, 20.5], [160, 120], [300, 230]])
    o, d = C.pixel_rays(cam, uv)
    P = C.unproject(cam, uv, [3, 4, 5])
    t = np.einsum("ij,ij->i", P - o, d)
    assert np.allclose(o + d * t[:, None], P)


def test_invalid_intrinsics():
    with pytest.raises(NonFiniteError):
        C.Camera(fov_deg=180)
    with pytest.raises(NonFiniteError):
        C.Camera(width=0)
    with pytest.raises(NonFiniteError):
        C.Camera.look_at((1, 1, 1), (1, 1, 1))
    with pytest.raises(NonFiniteError):
        C.bbox_to_world(C.Camera(), (10, 0, 10, 5), 1.0)
