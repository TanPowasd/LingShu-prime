# -*- coding: utf-8 -*-
"""上游老 issue 逐条复核（r3，#196 起）world 段在 ng 上的回归测试。"""
import pytest

from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.world.compat import Camera3D, VPrim, World3D

TREES = ["tree@(380,250,420,350)", "tree@(381,250,421,350)", "tree@(382,250,422,350)"]
W, H = 800, 600


def _engine():
    e = SpacetimeMemoryEngine(":memory:")
    for i, t in enumerate(TREES):
        e.add_perception(content=f"帧{i} 视觉锚点 {t}", tags=["vprim"], skip_dedup=True)
    return e


# ---- #211：build(multiview) 不编造相机位姿；objects 为世界物体数 ----
def test_211_multiview_without_pose_falls_back():
    e = _engine()
    r = e.world3d("build", {"multiview": True})
    assert r["mode"] == "single_view" and r.get("reason") == "no_camera_pose", r
    assert r["objects"] == len(r["detail"]["objects"]) == 1 and r["observations"] == 3


def test_211_single_view_objects_is_world_count():
    r = _engine().world3d("build", {"multiview": False})
    assert r["objects"] == r["detail"]["count"] == 1 and r["observations"] == 3
    assert "reason" not in r


def test_211_multiview_uses_real_poses():
    P = (0.0, 1.0, 6.0)
    poses = [dict(cx=-1.0, cy=1.2, cz=0.0, yaw=0.0, pitch=0.0), dict(cx=1.0, cy=1.2, cz=0.0, yaw=0.0, pitch=0.0)]
    e = SpacetimeMemoryEngine(":memory:")
    for i, pose in enumerate(poses):
        u, v = Camera3D(**pose).project(P, W, H)
        bb = (int(round(u)) - 20, int(round(v)) - 20, int(round(u)) + 20, int(round(v)) + 20)
        n = e.add_perception(content="帧%d 视觉锚点 ball@(%d,%d,%d,%d)" % ((i,) + bb), tags=["vprim"],
                             skip_dedup=True)
        n.state_attributes["camera_pose"] = pose
        e.store.add_node(n)
    r = e.world3d("build", {"multiview": True, "screen_w": W, "screen_h": H})
    assert r["mode"] == "multiview" and "reason" not in r, r
    objs = r["detail"]["objects"]
    assert r["objects"] == len(objs) == 1
    assert all(abs(a - b) < 0.3 for a, b in zip(objs[0]["center"], P)), objs[0]["center"]


# ---- #221：add_vprim 反投影用相机位姿，正反投影往返 ----
@pytest.mark.parametrize("cam", [Camera3D(), Camera3D(cx=5.0), Camera3D(yaw=0.5), Camera3D(pitch=0.3)],
                         ids=["default", "cx5", "yaw", "pitch"])
@pytest.mark.parametrize("cy_px", [120, 200, 300])
def test_221_add_vprim_round_trip(cam, cy_px):
    o = World3D(camera=cam).add_vprim(VPrim("apple", (390, cy_px - 10, 410, cy_px + 10), 0.9), W, H)
    p = cam.project(o.center, W, H)
    assert p is not None and abs(p[0] - 400) < 1.0 and abs(p[1] - cy_px) < 1.0, (p, o.center)


def test_221_pose_changes_world_position():
    a = World3D(camera=Camera3D()).add_vprim(VPrim("apple", (390, 190, 410, 210), 0.9), W, H).center
    b = World3D(camera=Camera3D(cx=5.0)).add_vprim(VPrim("apple", (390, 190, 410, 210), 0.9), W, H).center
    assert abs((b[0] - a[0]) - 5.0) < 1e-6
