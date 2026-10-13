import math

import numpy as np
import pytest

from lingshu_ng.world import validate as V


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), "x", None, True])
def test_finite_scalar_rejects(bad):
    with pytest.raises(V.NonFiniteError):
        V.finite_scalar(bad)


def test_finite_scalar_accepts():
    assert V.finite_scalar(3) == 3.0 and V.finite_scalar(np.float32(1.5)) == 1.5


def test_unit_interval_rejects_not_clamps():
    for bad in (-0.01, 1.01, math.nan):
        with pytest.raises(V.NonFiniteError):
            V.unit_interval(bad)
    assert V.unit_interval(0.0) == 0.0 and V.unit_interval(1.0) == 1.0


def test_array_shape_and_nan():
    with pytest.raises(V.NonFiniteError):
        V.finite_array([1, 2, float("nan")])
    with pytest.raises(V.NonFiniteError):
        V.finite_vec3([1, 2])
    assert V.finite_array([[1, 2, 3]], shape=(-1, 3)).shape == (1, 3)


def test_rotation_matrix():
    V.rotation_matrix(np.eye(3))
    with pytest.raises(V.NonFiniteError):
        V.rotation_matrix(np.diag([1, 1, -1]))
    with pytest.raises(V.NonFiniteError):
        V.rotation_matrix(np.eye(3) * 2)


def test_every_public_entry_rejects_nan():
    """统一判据入口：各模块对 NaN 输入一律抛 NonFiniteError（而不是静默通过阈值）。"""
    from lingshu_ng.world import camera, geometry, scene, sim, skeleton
    nan = float("nan")
    calls = [
        lambda: camera.Camera(position=(0, nan, 0)),
        lambda: camera.Camera.look_at((0, 0, 0), (nan, 0, 1)),
        lambda: camera.project(camera.Camera(), (0, 0, nan)),
        lambda: camera.unproject(camera.Camera(), [(1, 1)], [nan]),
        lambda: camera.bbox_to_world(camera.Camera(), (0, 0, 10, 10), nan),
        lambda: geometry.box_mesh((0, 0, 0), (1, nan, 1)),
        lambda: scene.Entity("a", (0, nan, 0)),
        lambda: scene.bbox_relation((0, 0, nan, 1), (0, 0, 1, 1)),
        lambda: scene.EdgeStore().observe("a", "seek", "b", nan, 0),
        lambda: sim.Motion(speed=nan),
        lambda: sim.seek_step((0, 0, 0), (nan, 0, 0), sim.Motion(1.0)),
        lambda: skeleton.Skeleton().add("j", (0, nan, 0)),
    ]
    for c in calls:
        with pytest.raises(V.NonFiniteError):
            c()
