import numpy as np
import pytest

from lingshu_ng.world import geometry as G
from lingshu_ng.world.camera import Camera, project_point
from lingshu_ng.world.raster import clip_near, rasterize

from .oracle import boundary_mask, raycast


def random_scene(rng, n=6):
    kinds = ["box", "box", "pyramid", "sphere"]
    meshes = []
    for i in range(n):
        meshes.append(G.primitive_mesh(kinds[rng.integers(len(kinds))], rng.uniform(-2.5, 2.5, 3),
                                       rng.uniform(0.4, 2.5, 3), tuple(rng.integers(30, 255, 3)), i))
    return G.merge_meshes(meshes)


def random_cam(rng, w=80, h=60):
    eye = rng.normal(size=3)
    eye = eye / np.linalg.norm(eye) * rng.uniform(5, 14)
    return Camera.look_at(eye, rng.uniform(-1, 1, 3), fov_deg=rng.uniform(35, 90), width=w, height=h)


@pytest.mark.parametrize("seed", range(30))
def test_occlusion_matches_per_pixel_ray_oracle(seed):
    """性质：任意相机 × 多物体互相穿插遮挡，z-buffer 的 id/深度与逐像素射线求交一致。"""
    rng = np.random.default_rng(seed)
    mesh, cam = random_scene(rng), random_cam(rng)
    fr = rasterize(mesh, cam)
    gt_ids, gt_z = raycast(mesh, cam)
    interior = ~boundary_mask(gt_ids)
    assert np.array_equal(fr.ids[interior], gt_ids[interior])
    wrong = np.mean(fr.ids != gt_ids)
    assert wrong <= 0.002, wrong
    both = (fr.ids == gt_ids) & (gt_ids >= 0)
    assert np.allclose(fr.depth[both], gt_z[both], rtol=1e-9, atol=1e-9)


def test_order_independent():
    """z-buffer 与面提交顺序无关（画家算法的根本缺陷不存在）。"""
    rng = np.random.default_rng(5)
    mesh, cam = random_scene(rng, 8), random_cam(rng, 120, 90)
    a = rasterize(mesh, cam)
    perm = rng.permutation(mesh.n_faces)
    shuffled = G.Mesh(mesh.vertices, mesh.faces[perm], mesh.face_colors[perm], mesh.face_ids[perm])
    b = rasterize(shuffled, cam)
    assert (a.ids != b.ids).mean() < 1e-3 and np.array_equal(a.depth, b.depth)


def test_near_box_occludes_far_box_reversed_camera():
    """world-02 原样场景：相机从 z=20 回看，近处红盒必须挡住远处大蓝盒。"""
    cam = Camera.look_at((0, 1.2, 20), (0, 1.2, 0), width=400, height=300)
    m = G.merge_meshes([G.primitive_mesh("box", (0, 1.2, 10), (2, 2, 2), (255, 0, 0), 0),
                        G.primitive_mesh("box", (0, 1.2, 2), (6, 6, 2), (0, 0, 255), 1)])
    fr = rasterize(m, cam)
    assert fr.ids[150, 200] == 0 and np.isclose(fr.depth[150, 200], 9.0)


def test_interpenetrating_objects_resolved_per_pixel():
    """互相穿插的两块板：任何物体级全序都错，逐像素深度对。"""
    cam = Camera.look_at((0, 0, -10), (0, 0, 0), width=101, height=61)
    a = G.primitive_mesh("box", (0, 0, 0), (4, 1, 0.2), (255, 0, 0), 0)
    v = a.vertices.copy()
    v[:, 2] += v[:, 0] * 0.5                       # 倾斜板：左近右远
    a = G.Mesh(v, a.faces, a.face_colors, a.face_ids)
    b = G.primitive_mesh("box", (0, 0, 0), (4, 0.8, 0.2), (0, 0, 255), 1)
    fr = rasterize(G.merge_meshes([a, b]), cam)
    row = fr.ids[30]
    assert 0 in row[:45] and 1 in row[56:]
    assert row[38] == 0 and row[62] == 1


def test_sphere_projected_radius_uses_camera_depth():
    cam = Camera.look_at((0, 1.2, 20), (0, 1.2, 0), width=400, height=300)
    fr = rasterize(G.primitive_mesh("sphere", (0, 1.2, 15), (1, 1, 1), (0, 255, 0), 0), cam)
    xs = np.nonzero(fr.ids[150] == 0)[0]
    expect = 2 * cam.focal * 0.5 / 5.0
    assert abs((xs.max() - xs.min() + 1) - expect) <= 2


def test_pyramid_apex_row():
    for h in (0.5, 2.0, 3.0):
        cam = Camera(width=400, height=300)
        fr = rasterize(G.primitive_mesh("pyramid", (0, h / 2, 8), (2, h, 2), (255, 0, 0), 0), cam)
        rows = np.nonzero((fr.ids == 0).any(axis=1))[0]
        apex = project_point(cam, (0, h, 8))
        assert abs(rows.min() + 0.5 - apex[1]) <= 1.5


def test_clip_near_cases():
    near = 0.1
    t = np.array([[0, 0, 1.0], [1, 0, 1.0], [0, 1, 1.0]])
    assert len(clip_near(t, near)) == 1
    assert clip_near(t - [0, 0, 5], near) == []
    one_in = np.array([[0, 0, 1.0], [1, 0, -1.0], [0, 1, -1.0]])
    r = clip_near(one_in, near)
    assert len(r) == 1 and np.all(r[0][:, 2] >= near - 1e-12)
    two_in = np.array([[0, 0, 1.0], [1, 0, 1.0], [0, 1, -1.0]])
    r = clip_near(two_in, near)
    assert len(r) == 2 and all(np.all(x[:, 2] >= near - 1e-12) for x in r)


def test_ground_plane_crossing_camera_is_clipped_not_dropped():
    cam = Camera.look_at((0, 1, 0), (0, 1, 10), width=64, height=48)
    ground = G.primitive_mesh("box", (0, -0.05, 0), (200, 0.1, 200), (0, 200, 0), 0)
    fr = rasterize(ground, cam)
    assert (fr.ids[30:] == 0).all() and (fr.ids[:23] == -1).all()
    assert np.isfinite(fr.depth[30:]).all() and (fr.depth[30:] > 0).all()


def test_empty_and_offscreen():
    cam = Camera(width=32, height=24)
    fr = rasterize(G.merge_meshes([]), cam)
    assert (fr.ids == -1).all()
    fr = rasterize(G.primitive_mesh("box", (500, 0, 5), (1, 1, 1), (1, 1, 1), 0), cam)
    assert (fr.ids == -1).all()
