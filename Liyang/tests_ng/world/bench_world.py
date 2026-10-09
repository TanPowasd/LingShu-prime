# -*- coding: utf-8 -*-
"""世界渲染正确性/反投影/耗时对比实验：旧 world3d（上游 2bb8291 / 本仓 lingshu / integrated-v2）vs ng。

- 场景 A「多盒遮挡」：N_CAM 个随机相机位姿 × 6 个可互相穿插的轴对齐盒；
- 场景 A'「不相交多盒」：N_CAM 个随机位姿 × 6 个两两不相交的盒（排除「穿插无全序」因素）；
- 场景 B「组合形状」：N_CAM 个随机位姿 × 2 张桌子 + 1 把椅子（部件组合，桌面/腿分色）；
- 真值：逐像素中心射线–三角形求交（tests_ng/world/oracle.py，与任何光栅器无共享代码）；
- 各实现一律「渲染 RGB → 最近调色板色 → 标签」，同一口径；
- 反投影：每个位姿 10 个天空物体（balloon）由真值 3D 点合成 bbox，add_vprim 回 3D，
  量 3D 误差与重投影像素误差。

用法：python tests_ng/world/bench_world.py  → lingshu_ng/world/BENCH_WORLD.json
（"sim" 段由 bench_world_sim.py 给出：模拟 / 世界模型 / 多视角 / 锚点，本仓旧实现 vs ng）
子进程模式（内部）：bench_world.py --child <impl> <scenes.json> <out.npz>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Dict, List

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LS = os.path.dirname(REPO)
IMPLS = {"upstream_2bb8291": os.path.join(LS, "upstream"), "repo_lingshu": REPO,
         "integrated_v2": os.path.join(LS, "integrated"), "ng": REPO}
W, H, N_CAM, SEED, REPEAT = 320, 240, 24, 20261009, 3
SETS = ("boxes", "boxes_disjoint", "composite")
HUES = [(220, 50, 50), (50, 200, 50), (50, 80, 230), (210, 200, 40), (200, 50, 200), (40, 200, 210)]
SHADES = (0.42, 0.595, 0.6, 0.665, 0.7, 0.805, 0.85, 0.95, 1.0, 1.15)   # 含描边 ×0.7
TABLE = [("A", (1.2, 0.08, 0.8), (0, 0.1, 0))] + [
    ("B", (0.08, 0.6, 0.08), (sx * 0.5, -0.2, sz * 0.3)) for sx in (-1, 1) for sz in (1, -1)]
CHAIR = [("A", (0.5, 0.06, 0.5), (0, 0.1, 0))] + [
    ("B", (0.05, 0.4, 0.05), (sx * 0.2, -0.15, sz * 0.2)) for sx in (-1, 1) for sz in (1, -1)] + [
    ("A", (0.5, 0.5, 0.05), (0, 0.35, -0.25))]


# ---------------------------------------------------------------- 场景生成

def _cam(rng: np.random.Generator, rmin: float, rmax: float, elev: tuple) -> Dict:
    az = rng.uniform(0, 2 * np.pi)
    el = rng.uniform(*elev)
    r = rng.uniform(rmin, rmax)
    eye = [r * np.cos(el) * np.sin(az), r * np.sin(el), r * np.cos(el) * np.cos(az)]
    return {"eye": eye, "target": list(rng.uniform(-0.3, 0.3, 3)), "fov": float(rng.uniform(45, 75))}


def make_scenes() -> Dict:
    rng = np.random.default_rng(SEED)
    boxes = []
    for _ in range(N_CAM):
        objs = [{"cat": f"bx{i}", "center": list(rng.uniform(-1.6, 1.6, 3)),
                 "size": list(rng.uniform(0.6, 2.4, 3)), "color": HUES[i], "parts": None}
                for i in range(6)]
        boxes.append({"cam": _cam(rng, 8, 14, (-0.6, 0.9)), "objects": objs})
    disjoint = []
    for _ in range(N_CAM):
        objs: List[Dict] = []
        while len(objs) < 6:
            c, sz = rng.uniform(-2.6, 2.6, 3), rng.uniform(0.4, 2.0, 3)
            if all(np.any(np.abs(c - np.array(o["center"])) * 2 > sz + np.array(o["size"]) + 0.05)
                   for o in objs):
                objs.append({"cat": f"dj{len(objs)}", "center": list(c), "size": list(sz),
                             "color": HUES[len(objs)], "parts": None})
        disjoint.append({"cam": _cam(rng, 9, 15, (-0.6, 0.9)), "objects": objs})
    comp = []
    for _ in range(N_CAM):
        objs = []
        for i, tmpl in enumerate([TABLE, TABLE, CHAIR]):
            ca, cb = HUES[2 * i], HUES[2 * i + 1]
            parts = [{"kind": "box", "pos": list(p), "size": list(s), "color": ca if g == "A" else cb}
                     for g, s, p in tmpl]
            objs.append({"cat": f"cp{i}", "center": [float(rng.uniform(-1.2, 1.2)), 0.5,
                                                     float(rng.uniform(-1.2, 1.2))],
                         "size": [1.2, 0.8, 0.8], "color": ca, "parts": parts})
        comp.append({"cam": _cam(rng, 3.5, 6.5, (0.05, 0.9)), "objects": objs})
    bp = [{"cam": s["cam"], "uvz": [[float(rng.uniform(5, W - 5)), float(rng.uniform(5, H - 5)),
                                     float(rng.uniform(3, 30))] for _ in range(10)]} for s in boxes]
    return {"boxes": boxes, "boxes_disjoint": disjoint, "composite": comp, "backproj": bp}


# ---------------------------------------------------------------- 子进程：调用某一实现

def _child(impl: str, scenes_path: str, out_path: str) -> None:
    root = IMPLS[impl]
    sys.path.insert(0, root)
    if impl == "ng":
        from lingshu_ng.world import catalog as shapes
        from lingshu_ng.world.compat import Camera3D, Object3D, VPrim, World3D
    else:
        from lingshu.world import shapes
        from lingshu.world.vprim import VPrim
        from lingshu.world.world3d import Camera3D, Object3D, World3D
    sc = json.load(open(scenes_path))
    out: Dict[str, np.ndarray] = {}
    for key in SETS:
        imgs, times = [], []
        for s in sc[key]:
            cam = Camera3D.look_at(tuple(s["cam"]["eye"]), tuple(s["cam"]["target"]), fov_deg=s["cam"]["fov"])
            w = World3D(camera=cam)
            for o in s["objects"]:
                if o["parts"]:
                    shapes.register_shape(o["cat"], [dict(p, pos=tuple(p["pos"]), size=tuple(p["size"]),
                                                          color=tuple(p["color"])) for p in o["parts"]])
                w.objects.append(Object3D(o["cat"], tuple(o["center"]), tuple(o["size"]), tuple(o["color"])))
            ts = []
            for _ in range(REPEAT):
                t0 = time.perf_counter()
                img = w.render(W, H, background=(0, 0, 0), ground_color=(0, 0, 0))
                ts.append(time.perf_counter() - t0)
            imgs.append(np.asarray(img, np.uint8))
            times.append(float(np.median(ts)))
        out[key] = np.stack(imgs)
        out[key + "_time"] = np.array(times)
    out["backproj"] = _child_backproj(sc["backproj"], Camera3D, World3D, VPrim)
    np.savez_compressed(out_path, **out)


def _child_backproj(items: List[Dict], Camera3D, World3D, VPrim) -> np.ndarray:
    res = []
    for it in items:
        cam = Camera3D.look_at(tuple(it["cam"]["eye"]), tuple(it["cam"]["target"]), fov_deg=it["cam"]["fov"])
        f = cam.focal(W)
        for u, v, z in it["uvz"]:
            wpx = f * 0.5 / z                       # balloon 真实宽 0.5 m
            o = World3D(camera=cam).add_vprim(VPrim("balloon", (u - wpx / 2, v - wpx / 2,
                                                                u + wpx / 2, v + wpx / 2)), W, H)
            res.append(list(o.center))
    return np.array(res)


# ---------------------------------------------------------------- 父进程：真值与指标

def _palette(objs: List[Dict]) -> tuple:
    cols, labs = [(0, 0, 0)], [-1]
    for oi, o in enumerate(objs):
        groups = sorted({tuple(p["color"]) for p in o["parts"]}) if o["parts"] else [tuple(o["color"])]
        for g in groups:
            lab = oi * 10 + groups.index(g)
            for k in SHADES:
                cols.append(tuple(min(255, int(c * k)) for c in g))
                labs.append(lab)
    return np.array(cols, float), np.array(labs)


def classify(img: np.ndarray, objs: List[Dict]) -> np.ndarray:
    cols, labs = _palette(objs)
    d = ((img.reshape(-1, 1, 3).astype(float) - cols[None]) ** 2).sum(-1)
    return labs[np.argmin(d, axis=1)].reshape(img.shape[:2])


def ground_truth(scene: Dict) -> tuple:
    sys.path.insert(0, REPO)
    sys.path.insert(0, HERE)
    from lingshu_ng.world.camera import Camera
    from lingshu_ng.world.geometry import merge_meshes, primitive_mesh
    from oracle import raycast
    ms = []
    for oi, o in enumerate(scene["objects"]):
        if not o["parts"]:
            ms.append(primitive_mesh("box", o["center"], o["size"], (0, 0, 0), oi * 10))
            continue
        groups = sorted({tuple(p["color"]) for p in o["parts"]})
        for p in o["parts"]:
            c = np.add(o["center"], p["pos"])
            ms.append(primitive_mesh("box", c, p["size"], (0, 0, 0), oi * 10 + groups.index(tuple(p["color"]))))
    c = scene["cam"]
    cam = Camera.look_at(c["eye"], c["target"], fov_deg=c["fov"], width=W, height=H)
    ids, _, amb = raycast(merge_meshes(ms), cam, with_ambiguous=True)
    return ids, amb


def occlusion_metrics(pred: np.ndarray, gt_amb: tuple) -> Dict[str, float]:
    """统计口径剔除真值不唯一的共面 z-fighting 像素（各实现一视同仁）。"""
    from oracle import boundary_mask
    gt, amb = gt_amb
    pred = np.where(amb, gt, pred)
    interior = ~boundary_mask(gt)
    both = (pred >= 0) & (gt >= 0)
    wrong_obj = both & (pred != gt)
    return {"err_all": float(np.mean(pred != gt)),
            "err_interior": float(np.mean((pred != gt)[interior])),
            "wrong_object_all": float(np.mean(wrong_obj)),
            "wrong_object_interior": float(np.mean(wrong_obj[interior])),
            "wrong_object_of_overlap_px": float(wrong_obj.sum() / max(1, both.sum())),
            "ambiguous_px_excluded": float(amb.sum())}


def backproj_metrics(centers: np.ndarray, items: List[Dict]) -> Dict[str, float]:
    from lingshu_ng.world.camera import Camera, project, unproject
    e3, epx, above = [], [], []
    k = 0
    for it in items:
        c = it["cam"]
        cam = Camera.look_at(c["eye"], c["target"], fov_deg=c["fov"], width=W, height=H)
        for u, v, z in it["uvz"]:
            P = unproject(cam, [(u, v)], [z])[0]
            Q = centers[k]
            k += 1
            e3.append(float(np.linalg.norm(Q - P)))
            uv, zz = project(cam, Q)
            epx.append(float(np.hypot(uv[0, 0] - u, uv[0, 1] - v)) if zz[0] > cam.near else float("inf"))
            above.append(v < H * 0.45)
    e3, epx, above = np.array(e3), np.array(epx), np.array(above)

    def stats(mask: np.ndarray) -> Dict[str, float]:
        p = epx[mask]
        fin = p[np.isfinite(p)]
        return {"n": int(mask.sum()), "err3d_median_m": float(np.median(e3[mask])),
                "err3d_max_m": float(np.max(e3[mask])),
                "reproj_median_px": float(np.median(fin)) if len(fin) else None,
                "reproj_p95_px": float(np.percentile(fin, 95)) if len(fin) else None,
                "behind_camera": int((~np.isfinite(p)).sum()),
                "within_1px_rate": float(np.mean(p <= 1.0))}
    return {"all": stats(np.ones_like(above)), "above_horizon": stats(above),
            "below_horizon": stats(~above)}


def _aggregate(per: List[Dict[str, float]], times: np.ndarray) -> Dict:
    keys = per[0].keys()
    agg = {k: float(np.mean([p[k] for p in per])) for k in keys}
    agg["worst_scene_err_interior"] = float(max(p["err_interior"] for p in per))
    agg["scenes_with_interior_errors"] = int(sum(p["err_interior"] > 0 for p in per))
    agg["render_ms_median"] = float(np.median(times) * 1000)
    agg["render_ms_mean"] = float(np.mean(times) * 1000)
    return agg


def main() -> int:
    tmp = os.path.join(tempfile.gettempdir(), "lingshu_bench_world")
    os.makedirs(tmp, exist_ok=True)
    scenes = make_scenes()
    sp = os.path.join(tmp, "scenes.json")
    json.dump(scenes, open(sp, "w"))
    raw = {}
    for impl in IMPLS:
        out = os.path.join(tmp, impl + ".npz")
        env = dict(os.environ, PYTHONPATH=IMPLS[impl], PYTHONHASHSEED="0")
        r = subprocess.run([sys.executable, __file__, "--child", impl, sp, out], env=env,
                           capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            print(impl, "FAILED", r.stderr[-2000:])
            continue
        raw[impl] = np.load(out)
    sys.path.insert(0, REPO)
    sys.path.insert(0, HERE)
    gts = {k: [ground_truth(s) for s in scenes[k]] for k in SETS}
    result = {"config": {"W": W, "H": H, "n_camera_poses": N_CAM, "seed": SEED, "repeat": REPEAT,
                         "boxes_per_scene": 6, "boxes": "6 boxes, interpenetrating allowed",
                         "boxes_disjoint": "6 pairwise-disjoint AABBs",
                         "composite": "2 tables + 1 chair"}, "impls": {}}
    for impl, d in raw.items():
        r = {}
        for k in SETS:
            per = [occlusion_metrics(classify(d[k][i], s["objects"]), gts[k][i])
                   for i, s in enumerate(scenes[k])]
            r[k] = _aggregate(per, d[k + "_time"])
        r["backproj"] = backproj_metrics(d["backproj"], scenes["backproj"])
        result["impls"][impl] = r
    result["ng_raw_bbox_to_world"] = _ng_raw_backproj(scenes["backproj"])
    from bench_world_sim import sim_metrics          # 模拟/世界模型/多视角/锚点（同进程两边）
    result["sim"] = sim_metrics()
    out = os.path.join(REPO, "lingshu_ng", "world", "BENCH_WORLD.json")
    json.dump(result, open(out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


def _ng_raw_backproj(items: List[Dict]) -> Dict:
    """ng 原生 camera.bbox_to_world（不做旧接口的 0.01 m 取整）。"""
    from lingshu_ng.world.camera import Camera, bbox_to_world
    cs = []
    for it in items:
        c = it["cam"]
        cam = Camera.look_at(c["eye"], c["target"], fov_deg=c["fov"], width=W, height=H)
        for u, v, z in it["uvz"]:
            w = cam.focal * 0.5 / z
            cs.append(bbox_to_world(cam, (u - w / 2, v - w / 2, u + w / 2, v + w / 2), 0.5))
    return backproj_metrics(np.array(cs), items)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        _child(sys.argv[2], sys.argv[3], sys.argv[4])
        sys.exit(0)
    sys.exit(main())
