import os
import subprocess
import sys

import numpy as np
import pytest

from lingshu_ng.world import compat as K

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_camera3d_round_trip_and_depth():
    cam = K.Camera3D.look_at((3, 2, -4), (-2, 0.5, 6))
    p = (0.3, 1.1, 2.0)
    assert np.allclose(cam.camera_to_world(cam.to_camera(p)), p)
    assert np.isclose(cam.view_depth(p), cam.to_camera(p)[2])
    assert K.Camera3D().view_depth((1, 3, 7.5)) == pytest.approx(7.5)


@pytest.mark.parametrize("pose", [dict(cx=5.0), dict(yaw=3.14159), dict(cx=3, cy=2, cz=-4, yaw=0.7, pitch=-0.3)])
def test_add_vprim_sky_round_trip(pose):
    cam = K.Camera3D(**pose)
    obj = K.World3D(camera=cam).add_vprim(K.VPrim("balloon", (390, 40, 410, 60)), 800, 600)
    u, v = cam.project(obj.center, 800, 600)
    assert abs(u - 400) < 1 and abs(v - 50) < 1


def test_add_vprim_merges_same_category_nearby():
    w = K.World3D()
    w.add_vprim(K.VPrim("dog", (360, 280, 440, 360)), 800, 600)
    w.add_vprim(K.VPrim("dog", (362, 280, 442, 360)), 800, 600)
    assert len(w.objects) == 1


def test_render_returns_pil_with_ground_band():
    w = K.World3D()
    img = w.render(40, 30, background=(1, 2, 3), ground_color=(4, 5, 6))
    assert img.size == (40, 30) and img.getpixel((0, 0)) == (1, 2, 3)
    assert img.getpixel((0, 29)) == (4, 5, 6)


def test_render_frame_ids_follow_object_order():
    w = K.World3D(camera=K.Camera3D.look_at((0, 1.2, 20), (0, 1.2, 0)))
    w.objects = [K.Object3D("a", (0, 1.2, 10), (2, 2, 2), (255, 0, 0)),
                 K.Object3D("b", (0, 1.2, 2), (6, 6, 2), (0, 0, 255))]
    fr = w.render_frame(400, 300)
    assert fr.ids[150, 200] == 0 and (fr.ids == 1).any()


def test_render_reuses_scratch_without_aliasing_returned_images():
    """render 复用帧缓冲，但已返回的 PIL 图不随后续渲染改变；改相机/改物体后结果随之变化。"""
    w = K.World3D(camera=K.Camera3D.look_at((0, 1.2, 20), (0, 1.2, 0)))
    w.objects = [K.Object3D("a", (0, 1.2, 10), (2, 2, 2), (255, 0, 0))]
    a = np.asarray(w.render(80, 60, background=(0, 0, 0), ground_color=(0, 0, 0)))
    w.objects[0] = K.Object3D("a", (3, 1.2, 10), (2, 2, 2), (0, 255, 0))
    b = np.asarray(w.render(80, 60, background=(0, 0, 0), ground_color=(0, 0, 0)))
    assert not np.array_equal(a, b) and a[30, 40].tolist() != [0, 0, 0]
    w.camera.cx = 50.0                    # 可变旧相机：按值缓存的 ng 相机必须跟着变
    c = np.asarray(w.render(80, 60, background=(0, 0, 0), ground_color=(0, 0, 0)))
    assert not np.array_equal(b, c)
    fresh = K.World3D(camera=w.camera)
    fresh.objects = list(w.objects)
    assert np.array_equal(np.asarray(fresh.render(80, 60, background=(0, 0, 0), ground_color=(0, 0, 0))), c)


def test_scene_mesh_equals_per_object_merge():
    from lingshu_ng.world.geometry import merge_meshes
    w = K.World3D()
    w.objects = [K.Object3D("table", (0, 0.4, 3), (1.2, 0.8, 0.8), (150, 100, 60)),
                 K.Object3D("ball", (1, 0.3, 4), (0.6, 0.6, 0.6), (200, 0, 0), "sphere"),
                 K.Object3D("crate", (-1, 0.5, 5), (1, 1, 1), (90, 90, 90))]
    a = K.scene_mesh(w.objects)
    b = merge_meshes(K.object_mesh(o, i) for i, o in enumerate(w.objects))
    for f in ("vertices", "faces", "face_colors", "face_ids"):
        assert np.array_equal(getattr(a, f), getattr(b, f)), f


def test_spatial_relation_dict_shape():
    r = K.spatial_relation((0, 0, 500, 500), (100, 100, 600, 600))
    assert r["relation"] == "overlap" and r["overlap_ratio"] == 0.64
    assert set(r) == {"relation", "distance", "dx", "dy", "a_center", "b_center", "overlap_ratio"}


def test_vprim_helpers():
    v = K.parse_anchor("看到 cat@(1,2,30,40) 了")
    assert v.category == "cat" and v.bbox == (1, 2, 30, 40)
    assert K.count_vprims([v, v], "cat")["total"] == 2
    assert K.bbox_from_xywh(1, 2, 3, 4) == (1, 2, 4, 6)
    assert "cat@(1,2,30,40)" in K.vprims_to_scene_text([v])


def test_skeleton3d_templates_and_pose():
    sk = K.human_skeleton(center=(0, 0.85, 5))
    head0 = sk.world_pos("head")
    sk.joints["neck"].rot = (0.5, 0, 0)
    assert sk.world_pos("head") != head0
    assert len(K.fatfish_bone_skeleton().joints) > 40
    assert len(K.cat_skeleton().bones()) == len(K.cat_skeleton().joints) - 1
    img = sk.render(64, 64)
    assert img.size == (64, 64)


def test_scene_simulator_seek_no_overshoot_and_seed():
    s = K.SceneSimulator()
    r = s.add_entity("rabbit", behavior="wander", pos=(10, 1.5, 10), speed=0.0)
    w = s.add_entity("wolf", behavior="seek", goal=r, pos=(4.3, 1.5, 10), speed=0.8)
    d = []
    for _ in range(20):
        s.step(1)
        d.append(round(abs(s.entities[w].pos[0] - s.entities[r].pos[0]), 6))
    assert d[-10:] == [0.0] * 10
    assert K.SceneSimulator(seed=1)._rng.random() != K.SceneSimulator(seed=2)._rng.random()
    assert K.SceneSimulator()._rng.random() == K.SceneSimulator(seed=42)._rng.random()


def test_install_legacy_aliases_in_subprocess():
    code = ("import sys; sys.path.insert(0, %r)\n"
            "from lingshu_ng.world.compat import install_legacy_aliases\n"
            "print(sorted(install_legacy_aliases()))\n"
            "from lingshu.world.world3d import World3D\n"
            "from lingshu.world.scene_model import WorldModel\n"
            "import lingshu.world.scene_model as sm\n"
            "assert World3D.__module__ == 'lingshu_ng.world.compat'\n"
            "assert sm.World3D is World3D\n" % REPO)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "world3d" in out.stdout and "scene_simulator" in out.stdout
