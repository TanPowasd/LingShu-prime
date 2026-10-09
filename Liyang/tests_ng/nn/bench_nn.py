# -*- coding: utf-8 -*-
"""旧 lingshu.nn（本仓基线）vs lingshu_ng.nn 对比实验。

用法：OPENBLAS_NUM_THREADS=1 PYTHONPATH=<repo> python tests_ng/nn/bench_nn.py <section> [...]
section ∈ forward | train_step | equiv | accuracy | gen | text_search | determinism
每个 section 把结果并入 lingshu_ng/nn/BENCH_NN.json（键 = section），可分批/并行跑。
口径说明见 BENCH_NN.md。机器为 2 核共享沙箱（其他任务并行），耗时取多次重复的中位数。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
LEGACY_ROOT = os.environ.get("LEGACY_ROOT")          # 例：/workspace/work/ls/upstream（上游 2bb8291 基线）
if LEGACY_ROOT:
    sys.path.insert(0, LEGACY_ROOT)
TAG = "_base" if LEGACY_ROOT else ""
OUT = os.path.join(REPO, "lingshu_ng", "nn", "BENCH_NN.json")

import lingshu.nn.hex_hier as LH          # noqa: E402
import lingshu.nn.hex_train as LT         # noqa: E402
from lingshu_ng.nn import hexgrid, search as NS, train as NT, multimodal as NM, scenes  # noqa: E402
from lingshu_ng.nn.net import HierHexNet  # noqa: E402
from lingshu_ng.nn.compat.hex_hier import label_indices  # noqa: E402


def med_time(fn, reps=5):
    ts = []
    for _ in range(reps):
        t = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t)
    return float(np.median(ts))


PARTS = os.path.join(HERE, "bench_parts")


def save(section, data):
    """分节落盘（可并行跑），merge 时汇总进 BENCH_NN.json。"""
    os.makedirs(PARTS, exist_ok=True)
    json.dump({"data": data, "env": {"OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS")},
               "when": time.strftime("%Y-%m-%d %H:%M:%S")},
              open(os.path.join(PARTS, section + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(section, json.dumps(data, ensure_ascii=False)[:2000], flush=True)


def load(section, default=None):
    p = os.path.join(PARTS, section + ".json")
    return json.load(open(p, encoding="utf-8"))["data"] if os.path.exists(p) else default


def twin(seed=7, **kw):
    """同参数的旧/新网络（新网络参数从旧网络复制，前向逐项可比）。"""
    old = LH.HexHierNet(seed=seed, **kw)
    new = HierHexNet(rng=seed, **{k: v for k, v in kw.items()})
    new.params.set_vec(old.get_vec())
    return old, new


def sec_forward():
    rows = []
    g = np.random.default_rng(0)
    for b, (r, c) in [(16, (18, 16)), (96, (18, 16)), (96, (37, 32)), (32, (74, 64))]:
        x = g.normal(size=(b, r, c, 3))
        old, new = twin()
        lo = old.l3_logits(*old.l2_features(x))
        ln = new.forward_cache(x)["logits"]
        reps = 3 if r > 40 else 7
        t_old = med_time(lambda: old.l3_logits(*old.l2_features(x)), reps)
        t_new = med_time(lambda: new.forward_cache(x), reps)
        h1 = np.abs(new.forward_cache(x)["h1"])
        t_c_old = med_time(lambda: [LT.hex_conv_batch(h1, old.conv2[k]).sum(-1) for k in range(old.K2)], reps)
        from lingshu_ng.nn.conv import hex_conv
        t_c_new = med_time(lambda: hex_conv(h1, new.params.view("conv2")), reps)
        rows.append({"batch": b, "lattice": [r, c], "fwd_legacy_ms": round(t_old * 1e3, 2),
                     "fwd_ng_ms": round(t_new * 1e3, 2), "fwd_speedup": round(t_old / t_new, 2),
                     "conv2_legacy_ms": round(t_c_old * 1e3, 2), "conv2_ng_ms": round(t_c_new * 1e3, 2),
                     "conv2_speedup": round(t_c_old / t_c_new, 2), "max_abs_logit_diff": float(np.abs(lo - ln).max())})
    save("forward", rows)


def scene_lat(n, cells, seed=7, legacy_grid=False):
    xs, labs = scenes.make_scene_dataset(n, 48, seed)
    if legacy_grid:
        from lingshu.nn.hex_cnn import image_to_grid
        f = [image_to_grid(x, cells)[0] / 255.0 for x in xs]
    else:
        f = [hexgrid.image_to_lattice(x, cells)[0] / 255.0 for x in xs]
    return LT.normalize_lattices(np.stack(f)), labs


def sec_train_step():
    rows = []
    for cells, samples in [(16, 20), (32, 20)]:
        lat, labs = scene_lat(96, cells)
        o, s = label_indices(labs)
        old, new = twin()
        t_old = med_time(lambda: LH.train_hier(old, lat, labs, steps=2, samples_per_step=samples, lr=0.1), 2) / 2
        t_seq = med_time(lambda: NT.train_hier(new, lat, o, s, steps=5, samples_per_step=samples, lr=0.1), 2) / 5
        t_par = med_time(lambda: NT.train_hier(new, lat, o, s, steps=5, samples_per_step=samples, lr=0.1,
                                               mode="par"), 2) / 5
        t_an = med_time(lambda: NT.train_sign_grad(new, lat, o, s, steps=5, samples_per_step=samples, lr=0.1), 2) / 5
        t_an_all = med_time(lambda: NT.train_sign_grad(new, lat, o, s, steps=5, samples_per_step=new.params.size,
                                                       lr=0.1), 2) / 5
        rows.append({"lattice": list(lat.shape[1:3]), "batch": 96, "samples_per_step": samples,
                     "legacy_s_per_step": round(t_old, 3), "ng_seq_s_per_step": round(t_seq, 3),
                     "ng_par_s_per_step": round(t_par, 3), "ng_analytic_s_per_step": round(t_an, 4),
                     "ng_analytic_all_params_s_per_step": round(t_an_all, 4),
                     "speedup_seq": round(t_old / t_seq, 1), "speedup_par": round(t_old / t_par, 1)})
    save("train_step", rows)


def sec_equiv():
    """同 plan 轨迹对照：旧 rust_bridge.py_executor（正确分组的顺序坐标下降）vs ng execute_plan(seq)。"""
    from lingshu.nn.rust_bridge import make_plan, py_executor
    lat, labs = scene_lat(48, 16)
    o, s = label_indices(labs)
    old, new = twin()
    v0 = old.get_vec().copy()
    plan = make_plan(len(lat), steps=15, batch=24, samples=40, seed=7, n_params=old.n_params())
    t0 = time.perf_counter()
    c_old = py_executor(lat, o, s, v0.copy(), plan, old)
    t_old = time.perf_counter() - t0
    new.params.set_vec(v0)
    t0 = time.perf_counter()
    c_new = NT.execute_plan(new, lat, o, s, plan, mode="seq")
    t_new = time.perf_counter() - t0
    dv = np.abs(old.get_vec() - new.params.get_vec())
    save("equiv", {"steps": 15, "samples": 40, "curve_max_abs_diff": float(np.abs(c_old - c_new).max()),
                   "final_vec_max_abs_diff": float(dv.max()), "params_differing": int((dv > 1e-9).sum()),
                   "n_params": int(dv.size), "legacy_s": round(t_old, 2), "ng_s": round(t_new, 2)})


def _acc_run(impl, grid, seed, steps):
    lat, labs = scene_lat(288, 16, seed=100 + seed, legacy_grid=(grid == "legacy"))
    tr = {k: v[:192] for k, v in labs.items()}
    te = {k: v[192:] for k, v in labs.items()}
    t0 = time.perf_counter()
    if impl == "legacy":
        net = LH.HexHierNet(seed=seed)
        LH.train_hier(net, lat[:192], tr, steps=steps, samples_per_step=20, lr=0.1, seed=seed)
        rep_tr, rep_te = LH.hier_report(net, lat[:192], tr), LH.hier_report(net, lat[192:], te)
    else:
        from lingshu_ng.nn.cards import hier_report
        net = HierHexNet(rng=seed)
        o, s = label_indices(tr)
        NT.train_hier(net, lat[:192], o, s, steps=steps, samples_per_step=20, lr=0.1, rng=seed)
        rep_tr, rep_te = hier_report(net, lat[:192], tr), hier_report(net, lat[192:], te)
    return {"impl": impl, "lattice": grid, "seed": seed, "steps": steps, "train_s": round(time.perf_counter() - t0, 1),
            "train": rep_tr, "test": rep_te}


def sec_accuracy(which="all"):
    combos = [("legacy", "legacy"), ("ng", "ng"), ("ng", "legacy")]
    if which != "all":
        combos = [c for c in combos if f"{c[0]}-{c[1]}" == which]
    sec = "accuracy" if which == "all" else f"accuracy_{which}"
    cur = load(sec, [])
    for impl, grid in combos:
        for seed in (7, 8, 9):
            cur = [r for r in cur if not (r["impl"] == impl and r["lattice"] == grid and r["seed"] == seed)]
            cur.append(_acc_run(impl, grid, seed, 150))
            save(sec, cur)


GEN_SHAPES, GEN_COLORS = ["circle", "triangle", "stripe"], ["red", "green", "blue"]
POS9 = [f"r{i}" for i in range(9)]
PATS = ["solid", "striped", "dotted"]


def _protocol(mod, seed0, n, attrs, size, op=None):
    rng = np.random.default_rng(seed0)
    ok = tot = 0
    for t in range(n):
        k = int(rng.integers(1, 4))
        parts = [{"shape": GEN_SHAPES[rng.integers(3)], "color": GEN_COLORS[rng.integers(3)], "zone": POS9[rng.integers(9)],
                  **({"pattern": PATS[rng.integers(3)], "size": ["small", "medium", "large"][rng.integers(3)]}
                     if attrs else {})} for _ in range(k)]
        if op:
            parts = mod.transform_relations(parts, op)
        _, log = mod.render_relations(parts, size=size, seed=t)
        v = mod.verify_constructive(parts, log)
        ok, tot = ok + v["matched"], tot + v["total"]
    return round(ok / tot, 4)


def _faulty(mod, kind):
    parts = [{"shape": "circle", "color": "red", "zone": "r0", "pattern": "solid", "size": "medium"},
             {"shape": "triangle", "color": "green", "zone": "r8", "pattern": "dotted", "size": "medium"}]
    orig = mod._paint
    fakes = {"noop": lambda *a, **k: None,
             "mirror": lambda img, sh, cx, cy, *a: orig(img, sh, img.shape[1] - 1 - cx, cy, *a),
             "wrong_color": lambda img, sh, cx, cy, rad, col, pat: orig(img, sh, cx, cy, rad, (40, 60, 220), pat),
             "wrong_pattern": lambda img, sh, cx, cy, rad, col, pat: orig(img, sh, cx, cy, rad, col, "solid"),
             "wrong_shape": lambda img, sh, cx, cy, rad, col, pat: orig(img, "stripe", cx, cy, rad, col, pat),
             "wrong_size": lambda img, sh, cx, cy, rad, col, pat: orig(img, sh, cx, cy, max(1, rad // 2), col, pat)}
    mod._paint = fakes[kind]
    try:
        _, log = mod.render_relations(parts, size=96, seed=3, noise=False)
        return mod.verify_constructive(parts, log)["rate"]
    finally:
        mod._paint = orig


PARSE_GOLD = [("中心有蓝色菱形", "diamond", "blue", "r4"), ("右下方有蓝色菱形", "diamond", "blue", "r8"),
              ("下方有红色星", "star", "red", "r7"), ("中心有红色", "circle", "red", "r4"),
              ("中间有红色实心菱形", "diamond", "red", "r4"), ("中间有蓝色条纹菱形", "diamond", "blue", "r4"),
              ("白底中间有灰色圆形", "circle", "gray", "r4"), ("渐变绿底中间有蓝色圆形", "circle", "blue", "r4"),
              ("渐变蓝底中间有圆形", "circle", "red", "r4"), ("灰底右下有白色方块", "square", "white", "r8"),
              ("左上方有黄色心形", "heart", "yellow", "r0"), ("右方有紫色六边形", "hexagon", "purple", "r5"),
              ("上方有实心方块", "square", "red", "r1"), ("左下有点纹矩形", "rectangle", "red", "r6"),
              ("中心有粉色心", "heart", "pink", "r4"), ("渐变粉底右上有棕色星形", "star", "brown", "r2")]


def _parse_acc(mod):
    hit = 0
    for t, sh, co, z in PARSE_GOLD:
        p = mod.compile_description(t)["parts"]
        hit += int(len(p) == 1 and (p[0]["shape"], p[0]["color"], p[0]["zone"]) == (sh, co, z))
    phantom = len(mod.compile_description("渐变蓝底，左上有红色圆")["parts"]) - 1
    return {"parse_acc": round(hit / len(PARSE_GOLD), 4), "n": len(PARSE_GOLD), "phantom_parts": phantom}


def sec_gen():
    import lingshu.nn.hex_gen as LG
    from lingshu_ng.nn.compat import hex_gen as NG
    out = {}
    for name, mod in (("legacy", LG), ("ng", NG)):
        row = {"P1@48": _protocol(mod, 11, 40, False, 48), "P1@96": _protocol(mod, 12, 40, False, 96),
               "R2@48": _protocol(mod, 23, 30, True, 48), "R2@96": _protocol(mod, 24, 30, True, 96),
               "R2@48_200": _protocol(mod, 99, 200, True, 48), "R2@96_200": _protocol(mod, 98, 200, True, 96)}
        row.update({f"rot/flip {op}": _protocol(mod, 41, 40, False, 48, op) for op in mod.ZONE_TRANSFORMS})
        row["faulty_painter_rate"] = {k: _faulty(mod, k) for k in
                                      ("noop", "mirror", "wrong_color", "wrong_pattern", "wrong_shape", "wrong_size")}
        row.update(_parse_acc(mod))
        row["render_ms@96"] = round(med_time(lambda: mod.render_relations(
            [{"shape": "circle", "color": "red", "zone": "r0"}, {"shape": "triangle", "color": "blue", "zone": "r4"},
             {"shape": "stripe", "color": "green", "zone": "r4"}], size=96, seed=1), 7) * 1e3, 2)
        out[name] = row
    save("gen" + TAG, out)


def _mm_build(grid_fn, n, k, seed, cells):
    rng = np.random.default_rng(seed)
    xs, ms = [], []
    for _ in range(n):
        im, m = scenes.make_multimodal_scene(rng, 48, k)
        xs.append(im)
        ms.append(m)
    return LT.normalize_lattices(np.stack([grid_fn(im, cells) / 255.0 for im in xs])), ms


def _crops(lat, metas):
    r3, c3 = lat.shape[1] // 3, lat.shape[2] // 3
    crops, labs = [], {"shape": [], "color": [], "obj": [], "pos": []}
    for b, m in enumerate(metas):
        lb = m["labels"][0]
        qy, qx = divmod(int(lb["pos"][1]), 3)
        crops.append(lat[b, qy * r3:(qy + 1) * r3, qx * c3:(qx + 1) * c3])
        labs["shape"].append(lb["obj"].split("|")[0])
        labs["color"].append(lb["obj"].split("|")[1])
        labs["obj"].append(lb["obj"])
        labs["pos"].append("r4")
    return np.stack(crops), {k: np.array(v) for k, v in labs.items()}


def _impl(name):
    """(格点函数, 建网+训练函数, 检测/融合/搜索函数表)。"""
    if name == "legacy":
        import lingshu.nn.hex_search as LS
        import lingshu.nn.hex_text as LX
        from lingshu.nn.hex_cnn import image_to_grid

        def fit(crops, labs, steps, samples):
            net = LH.HexHierNet(seed=7)
            LH.train_hier(net, crops, labs, steps=steps, samples_per_step=samples, lr=0.1)
            return net
        return (lambda im, c: image_to_grid(im, c)[0], fit,
                {"detect": LX.spatial_detect, "check": LX.multimodal_check, "corrupt": LX.corrupt_description,
                 "search": LS.recursive_search, "report": LS.search_report})
    from lingshu_ng.nn.compat import hex_text as NX

    def fit_ng(crops, labs, steps, samples):
        net = HierHexNet(rng=7)
        o, s = label_indices(labs)
        NT.train_hier(net, crops, o, s, steps=steps, samples_per_step=samples, lr=0.1)
        return net
    return (lambda im, c: hexgrid.image_to_lattice(im, c)[0], fit_ng,
            {"detect": NM.spatial_detect, "check": NM.multimodal_check, "corrupt": NX.corrupt_description,
             "search": NS.recursive_search, "report": NS.search_report})


def _text_metrics(grid, fit, f):
    lat, metas = _mm_build(grid, 96, 1, 11, 16)
    t0 = time.perf_counter()
    net = fit(*_crops(lat, metas), 150, 20)
    t_train = time.perf_counter() - t0
    lat1, m1 = _mm_build(grid, 16, 1, 5, 16)
    d1 = f["detect"](net, lat1)
    single = sum(any(d["pos"] == m1[i]["labels"][0]["pos"] for d in d1[i]) for i in range(16)) / 16
    lat2, m2 = _mm_build(grid, 12, 2, 13, 16)
    d2 = f["detect"](net, lat2)
    split = sum(len({d["pos"] for d in d2[i]}) >= 2 for i in range(12)) / 12
    lat3, m3 = _mm_build(grid, 12, 1, 17, 16)
    rng = np.random.default_rng(3)
    clean = [f["check"](net, lat3[i:i + 1], m3[i]["description"])["verdict"] for i in range(12)]
    bad = [f["check"](net, lat3[i:i + 1], f["corrupt"](m3[i]["description"], rng, 1.0))["verdict"] for i in range(12)]
    return {"train_s": round(t_train, 1), "single_pos_hit": round(single, 3), "two_obj_split": round(split, 3),
            "clean_not_reject": round((clean.count("ACCEPT") + clean.count("DEFER")) / 12, 3),
            "corrupt_reject": round(bad.count("REJECT") / 12, 3)}


def _search_metrics(grid, fit, f):
    lat, metas = _mm_build(grid, 96, 1, 11, 32)
    t0 = time.perf_counter()
    net = fit(*_crops(lat, metas), 400, 32)
    t_train = time.perf_counter() - t0
    lat1, _ = _mm_build(grid, 12, 1, 5, 32)
    t0 = time.perf_counter()
    res = [f["search"](net, lat1[i:i + 1], max_depth=2) for i in range(12)]
    t_search = (time.perf_counter() - t0) / 12
    depths = [max(x["depth"] for x in fd) for fd, _ in res if fd]
    lat2, _ = _mm_build(grid, 12, 2, 13, 32)
    both = sum(len({x["pos"] for x in f["search"](net, lat2[i:i + 1], max_depth=2)[0]}) >= 2 for i in range(12))
    lat3, m3 = _mm_build(grid, 8, 2, 17, 32)
    return {"train_s": round(t_train, 1), "single_detected": len(depths), "single_mean_depth":
            round(float(np.mean(depths)), 3) if depths else None, "two_obj_both": round(both / 12, 3),
            "search_ms_per_image": round(t_search * 1e3, 1), "report": f["report"](net, lat3, m3, max_depth=2)}


def sec_text_search(name):
    grid, fit, f = _impl(name)
    save(f"text_{name}{TAG}", _text_metrics(grid, fit, f))
    save(f"search_{name}{TAG}", _search_metrics(grid, fit, f))


DET_CODE = r"""
import sys, hashlib, json, numpy as np
sys.path.insert(0, %(repo)r)
impl = %(impl)r
h = hashlib.sha256()
from lingshu_ng.nn import scenes
xs, labs = scenes.make_scene_dataset(32, 48, 7)
if impl == "ng":
    from lingshu_ng.nn import hexgrid, train
    from lingshu_ng.nn.net import HierHexNet
    from lingshu_ng.nn.compat.hex_hier import label_indices
    from lingshu_ng.gen import hexgen
    from lingshu_ng.gen.ids import stable_int
    lat = np.stack([hexgrid.image_to_lattice(x, 16)[0] / 255.0 for x in xs])
    net = HierHexNet(rng=7); o, s = label_indices(labs)
    train.train_hier(net, lat, o, s, steps=8, samples_per_step=20, batch=16)
    vec = net.params.get_vec()
    g = hexgen.generate("左上有红色圆形,右下有绿色三角", size=96, seed=3)
    img, ids = g["image"], [stable_int(("sid-%%d" %% i, 11)) for i in range(5)] + [g["scene_id"]]
else:
    import lingshu.nn.hex_hier as H, lingshu.nn.hex_gen as G
    from lingshu.nn.hex_cnn import image_to_grid
    lat = np.stack([image_to_grid(x, 16)[0] / 255.0 for x in xs])
    net = H.HexHierNet(seed=7)
    H.train_hier(net, lat, labs, steps=8, samples_per_step=20, batch=16)
    vec = net.get_vec()
    img = G.generate_from_text("左上有红色圆形,右下有绿色三角", size=96, seed=3)["image"]
    ids = [hash(("sid-%%d" %% i, 11)) %% 10 ** 9 for i in range(5)]   # = hexgen_multi_seed.load_multi 的 id 公式
out = {"train_vec": hashlib.sha256(np.ascontiguousarray(vec).tobytes()).hexdigest()[:16],
       "image": hashlib.sha256(np.ascontiguousarray(img).tobytes()).hexdigest()[:16],
       "ids": hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:16]}
print(json.dumps(out))
"""


def sec_determinism():
    out = {}
    for impl in ("legacy", "ng"):
        runs = []
        for hs in ("0", "1", "2024", "random"):
            env = dict(os.environ, PYTHONHASHSEED=hs)
            p = subprocess.run([sys.executable, "-c", DET_CODE % {"repo": REPO, "impl": impl}], env=env,
                               capture_output=True, text=True, timeout=900)
            runs.append(json.loads(p.stdout.strip().splitlines()[-1]))
        out[impl] = {k: len({r[k] for r in runs}) for k in runs[0]}
        out[impl]["runs"] = len(runs)
    save("determinism", out)


def merge():
    """汇总 bench_parts/*.json → lingshu_ng/nn/BENCH_NN.json。"""
    res = {}
    for f in sorted(os.listdir(PARTS)):
        if f.endswith(".json"):
            res[f[:-5]] = json.load(open(os.path.join(PARTS, f), encoding="utf-8"))
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("merged", sorted(res))


if __name__ == "__main__":
    sec = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    fn = {"forward": sec_forward, "train_step": sec_train_step, "equiv": sec_equiv, "gen": sec_gen,
          "determinism": sec_determinism, "merge": merge}.get(sec)
    if fn:
        fn()
    elif sec == "accuracy":
        sec_accuracy(arg or "all")
    elif sec == "text_search":
        sec_text_search(arg)
    else:
        raise SystemExit(f"未知 section {sec}")
