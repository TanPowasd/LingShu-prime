"""H-WLD 世界 / 生成 / 网络（旧 API 名，经 hadapt.legacy_mod 取实现）：

part=hexgen  白箱文生图：随机 1–4 部件中文描述 → generate_from_text → 独立像素预言机（色块落格 + 颜色占比）
             + 编译正确率（五元组）+ 关系层变换的变形一致性 + 分辨率无关（48/96/192）。
part=scene   场景模拟器不变量：单 tick 位移 ≤ speed、边界内、有限、同 seed 可复现、seek 静止目标收敛不振荡、
             follow 依次到达路径点；规模 2000 实体 × 30 tick 的每实体·tick 耗时。
part=stcnn   时空原语预言机：方向 / 速度 / 周期；亮度仿射与小噪声下的不变性；时空记忆写入自校验与篡改检出。
part=nn      信息差门控训练（HexNet + train_infogap）在合成 4 类纹理上的测试准确率（固定 60 步预算）与耗时。
"""
import math
import random
import time

import numpy as np

from hadapt import legacy_mod, need

ZONES = {"左上": "r0", "上中": "r1", "右上": "r2", "左中": "r3", "中心": "r4", "右中": "r5", "左下": "r6", "下中": "r7", "右下": "r8"}
COLORS = {"红": "red", "绿": "green", "蓝": "blue", "黄": "yellow", "橙": "orange", "紫": "purple", "粉": "pink", "棕": "brown"}
# 颜色规格取自旧项目 hex_gen._OPEN_RGB（INTENT_MAP 记出处）；绿色另有 hex_composite 口径 (40,200,60)
RGB = {"red": [(220, 40, 40)], "green": [(40, 180, 60), (40, 200, 60)], "blue": [(40, 60, 220)], "yellow": [(230, 200, 40)],
       "orange": [(240, 140, 30)], "purple": [(140, 40, 200)], "pink": [(240, 140, 170)], "brown": [(140, 90, 40)]}
SHAPES = {"圆": "circle", "三角": "triangle", "方": "square", "矩形": "rectangle", "星": "star", "心": "heart", "六边": "hexagon", "菱": "diamond"}
PATTERNS = {"": "solid", "条纹": "striped", "点纹": "dotted"}
SIZES = {"": "medium", "大": "large", "小": "small"}
ROT = {"rot90cw": lambda r, c: (c, 2 - r), "rot180": lambda r, c: (2 - r, 2 - c), "fliph": lambda r, c: (r, 2 - c), "flipv": lambda r, c: (2 - r, c)}


def _prompt(rnd):
    k = rnd.randint(1, 4)
    zs = rnd.sample(list(ZONES), k)
    cs = rnd.sample(list(COLORS), k)
    parts, segs = [], []
    for z, c in zip(zs, cs):
        sh = rnd.choice(list(SHAPES)); pa = rnd.choice(list(PATTERNS)); si = rnd.choice(list(SIZES))
        segs.append(f"{z}{si}{c}色{pa}{sh}")
        parts.append({"zone": ZONES[z], "color": COLORS[c], "shape": SHAPES[sh], "pattern": PATTERNS[pa], "size": SIZES[si]})
    return "，".join(segs), parts


def _pixel_ok(img, part, zone=None):
    img = np.asarray(img)[..., :3].astype(int)
    S = img.shape[0]
    zone = zone or part["zone"]
    q = int(zone[1]); r, c = q // 3, q % 3
    mask = np.zeros(img.shape[:2], bool)
    for rgb in RGB[part["color"]]:
        mask |= np.abs(img - np.array(rgb)).max(axis=-1) <= 45
    cell = np.zeros_like(mask)
    cell[r * S // 3:(r + 1) * S // 3, c * S // 3:(c + 1) * S // 3] = True
    inside, total = int((mask & cell).sum()), int(mask.sum())
    need_px = max(6, int(0.001 * S * S))     # 可见下限：小号点纹部件在 96px 约 20–30 个着色像素
    return inside >= need_px and inside >= 0.7 * total


def _hexgen(impl, seed, n=60):
    hg = legacy_mod(impl, "nn", "hex_gen")
    gen = need(hg, "generate_from_text")
    comp = need(hg, "compile_description")
    rnd = random.Random(seed * 13 + 5)
    c_ok = p_ok = t_ok = r_ok = tot = 0
    errs = 0
    t_lat = []
    for i in range(n):
        text, parts = _prompt(rnd)
        try:
            cp = comp(text)["parts"]
            cpk = [{k: p.get(k) for k in ("zone", "color", "shape", "pattern", "size")} for p in cp]
        except Exception:
            cpk, errs = [], errs + 1
        t0 = time.perf_counter()
        try:
            img = gen(text, size=96, seed=7 + i)["image"]
        except Exception:
            img, errs = None, errs + 1
        t_lat.append(time.perf_counter() - t0)
        op = rnd.choice(list(ROT))
        try:
            img_t = gen(text, size=96, seed=7 + i, transform=op)["image"]
        except Exception:
            img_t = None
        res = rnd.choice([48, 192])
        try:
            img_r = gen(text, size=res, seed=7 + i)["image"]
        except Exception:
            img_r = None
        for j, p in enumerate(parts):
            tot += 1
            c_ok += int(j < len(cpk) and cpk[j] == p)
            p_ok += int(img is not None and _pixel_ok(img, p))
            q = int(p["zone"][1]); nr, nc = ROT[op](q // 3, q % 3)
            t_ok += int(img_t is not None and _pixel_ok(img_t, p, f"r{nr * 3 + nc}"))
            r_ok += int(img_r is not None and _pixel_ok(img_r, p))
    return {"compile_acc": round(c_ok / tot, 4), "pixel_acc": round(p_ok / tot, 4),
            "transform_acc": round(t_ok / tot, 4), "resolution_acc": round(r_ok / tot, 4),
            "parts": tot, "errors": errs, "gen_ms": round(1000 * sum(t_lat) / len(t_lat), 2)}


def _scene(impl, seed):
    ss = legacy_mod(impl, "world", "scene_simulator")
    _Sim = need(ss, "SceneSimulator")

    def Sim(size, seed):
        try:
            return _Sim(size=size, seed=seed)
        except TypeError:          # 早期版本构造器无 seed 参数：用其内部固定种子（仍应可复现）
            return _Sim(size=size)
    rnd = random.Random(seed * 19 + 1)
    chk = {"speed_bound": 0, "in_bounds": 0, "finite": 0, "deterministic": 0, "seek_converge": 0, "follow_visits": 0}
    trials = 15
    for t in range(trials):
        size = rnd.choice([16, 24, 40])
        spec = []
        for _ in range(rnd.randint(4, 20)):
            spec.append((rnd.choice(["wander", "seek", "avoid", "flee", "follow"]), round(rnd.uniform(0.1, 1.5), 2),
                         (rnd.uniform(1, size - 1), 1.5, rnd.uniform(1, size - 1))))

        def build():
            s = Sim(size=size, seed=1000 + t)
            ids = []
            s.add_path("p", [(2, 1.5, 2), (size - 3, 1.5, 2), (size - 3, 1.5, size - 3)])
            for beh, sp, pos in spec:
                ids.append(s.add_entity("a", behavior=beh, pos=pos, speed=sp))
            for k, (beh, sp, pos) in enumerate(spec):
                e = s.entities[ids[k]]
                e.goal = "p" if beh == "follow" else ids[(k + 1) % len(ids)]
            return s, ids

        import warnings
        warnings.filterwarnings("ignore")
        s1, ids = build()
        hist = []
        for _ in range(60):
            s1.step(1)
            hist.append(dict(s1.entity_positions()))
        s2, ids2 = build()
        hist2 = []
        for _ in range(60):
            s2.step(1)
            hist2.append([s2.entity_positions()[i] for i in ids2])
        speeds = {i: spec[k][1] for k, i in enumerate(ids)}
        ok_sp = ok_b = ok_f = True
        prev = {i: spec[k][2] for k, i in enumerate(ids)}
        for h in hist:
            for i, p in h.items():
                if not all(math.isfinite(v) for v in p):
                    ok_f = False
                    continue
                d = math.hypot(p[0] - prev[i][0], p[2] - prev[i][2])
                if d > speeds[i] + 0.011:
                    ok_sp = False
                if not (0 <= p[0] <= size and 0 <= p[2] <= size):
                    ok_b = False
                prev[i] = p
        chk["speed_bound"] += ok_sp; chk["in_bounds"] += ok_b; chk["finite"] += ok_f
        chk["deterministic"] += int([[h[i] for i in ids] for h in hist] == hist2)
        # seek 静止目标
        s3 = Sim(size=size, seed=t)
        tgt = s3.add_entity("t", behavior="wander", pos=(size / 2, 1.5, size / 2), speed=0.0)
        sp = round(rnd.uniform(0.2, 1.3), 2)
        sk = s3.add_entity("s", behavior="seek", pos=(1.0, 1.5, 1.0), speed=sp, goal=tgt)
        dist0 = math.hypot(size / 2 - 1, size / 2 - 1)
        s3.step(int(dist0 / sp) + 3)
        p = s3.entities[sk].pos
        d1 = math.hypot(p[0] - size / 2, p[2] - size / 2)
        s3.step(5)
        p2 = s3.entities[sk].pos
        chk["seek_converge"] += int(d1 <= 0.02 and math.hypot(p2[0] - p[0], p2[2] - p[2]) <= 0.02)
        # follow 依次到达
        s4 = Sim(size=size, seed=t)
        pts = [(2.0, 1.5, 2.0), (size - 3.0, 1.5, 2.0), (size - 3.0, 1.5, size - 3.0), (2.0, 1.5, size - 3.0)]
        s4.add_path("sq", pts)
        sp = 0.5
        fe = s4.add_entity("f", behavior="follow", pos=(2.0, 1.5, 2.0), speed=sp, goal="sq")
        visited = []
        for _ in range(int(4 * (size - 5) / sp) * 2 + 20):
            s4.step(1)
            q = s4.entities[fe].pos
            for k, pt in enumerate(pts):
                if math.hypot(q[0] - pt[0], q[2] - pt[2]) <= sp + 0.02 and (not visited or visited[-1] != k):
                    visited.append(k)
        chk["follow_visits"] += int(all(k in visited for k in range(4)) and visited[:4] in ([0, 1, 2, 3], [1, 2, 3, 0]))
    out = {k: round(v / trials, 4) for k, v in chk.items()}
    s = Sim(size=64, seed=3)
    for k in range(2000):
        s.add_entity("x", behavior="wander", pos=(rnd.uniform(1, 63), 1.5, rnd.uniform(1, 63)), speed=0.5)
    t0 = time.perf_counter()
    s.step(30)
    out["us_per_entity_tick"] = round((time.perf_counter() - t0) / (2000 * 30) * 1e6, 3)
    return out


def _clip(rnd, direction, speed, period, size=40, T=14, scale=1.0, offset=0.0, noise=0.0):
    frames = []
    obj = rnd.randint(3, 5)
    dx, dy = {"向右": (1, 0), "向左": (-1, 0), "向下": (0, 1), "向上": (0, -1)}[direction]
    travel = speed * (T - 1)
    size = max(size, travel + obj + 6)            # 画幅保证全程不贴边（真值速度不被边界截断）
    lo, hi = 2, size - obj - 2 - travel
    x0 = rnd.randint(lo, max(lo, hi)) if dx > 0 else (size - obj - 2 - rnd.randint(0, max(0, hi - lo)) if dx < 0 else rnd.randint(2, size - obj - 2))
    y0 = rnd.randint(lo, max(lo, hi)) if dy > 0 else (size - obj - 2 - rnd.randint(0, max(0, hi - lo)) if dy < 0 else rnd.randint(2, size - obj - 2))
    for t in range(T):
        f = np.zeros((size, size), np.float32)
        x, y = x0 + dx * speed * t, y0 + dy * speed * t
        x, y = max(0, min(size - obj, x)), max(0, min(size - obj, y))
        if period is None or (t % period) < max(1, period // 2):
            f[y:y + obj, x:x + obj] = 1.0
        frames.append(f * scale + offset)
    frames = np.array(frames)
    if noise:
        frames = frames + np.random.default_rng(rnd.randint(0, 10**6)).normal(0, noise, frames.shape).astype(np.float32)
    return frames


def _stcnn(impl, seed):
    st = legacy_mod(impl, "nn", "stcnn")
    ext = need(st, "extract_spatiotemporal_primitives")
    rnd = random.Random(seed * 23 + 9)
    d_ok = s_ok = inv_ok = n = 0
    p_ok = pn = 0
    for k in range(48):
        direction = ["向右", "向左", "向下", "向上"][k % 4]
        speed = 1 + (k // 4) % 3
        fr = _clip(random.Random(k + seed * 1000), direction, speed, None, T=10)
        try:
            pr, _ = ext(list(fr))
        except Exception:
            pr = {}
        n += 1
        d_ok += pr.get("direction") == direction
        s_ok += isinstance(pr.get("speed"), (int, float)) and abs(pr["speed"] - speed) <= 0.2 * speed
        fr2 = _clip(random.Random(k + seed * 1000), direction, speed, None, T=10, scale=rnd.uniform(0.3, 3), offset=rnd.uniform(-2, 2))
        try:
            pr2, _ = ext(list(fr2))
        except Exception:
            pr2 = {}
        inv_ok += all(pr.get(x) == pr2.get(x) for x in ("direction", "period", "moving")) and pr != {}
    for k in range(24):
        period = 2 + k % 5
        fr = _clip(random.Random(k + 77 + seed), "向右", 0, period, T=4 * period + 4)
        try:
            pr, _ = ext(list(fr))
        except Exception:
            pr = {}
        pn += 1
        p_ok += pr.get("period") == period
    out = {"direction_acc": round(d_ok / n, 4), "speed_acc": round(s_ok / n, 4), "period_acc": round(p_ok / pn, 4),
           "affine_invariance": round(inv_ok / n, 4)}
    noisy = 0
    for k in range(20):
        direction = ["向右", "向左", "向下", "向上"][k % 4]
        fr = _clip(random.Random(k + 500 + seed), direction, 2, None, T=10, noise=0.03)
        try:
            pr, _ = ext(list(fr))
        except Exception:
            pr = {}
        noisy += pr.get("direction") == direction
    out["noise_robust_dir"] = round(noisy / 20, 4)
    try:
        Mem = need(st, "SpatiotemporalMemory")
        mm = Mem()
        labels = []
        for k in range(100):
            fr = _clip(random.Random(k), ["向右", "向下"][k % 2], 1 + k % 3, None, T=8)
            pr, _ = ext(list(fr))
            mm.remember(pr, f"事件{k}", t_start=k * 10)
            labels.append(f"事件{k}")
        ok1 = all(len(mm.recall({"label": l})) == 1 for l in labels)
        ok2 = bool(mm.verify_consistency())
        mm.events[5]["direction"] = "向左" if mm.events[5]["direction"] != "向左" else "向右"
        ok3 = not mm.verify_consistency()
        out["memory_selfcheck"] = round((ok1 + ok2 + ok3) / 3, 4)
    except Exception:
        out["memory_selfcheck"] = 0.0
    return out


def _textures(rnd, n, S=32):
    X, Y = [], []
    for i in range(n):
        y = i % 4
        img = np.zeros((S, S), np.float32)
        ph = rnd.randint(0, 3)
        w = rnd.choice([2, 3])
        yy, xx = np.mgrid[0:S, 0:S]
        if y == 0:
            img = ((yy + ph) // w % 2).astype(np.float32)
        elif y == 1:
            img = ((xx + ph) // w % 2).astype(np.float32)
        elif y == 2:
            img = (((xx + ph) // w + (yy + ph) // w) % 2).astype(np.float32)
        else:
            img = (((xx + yy + ph) // w) % 2).astype(np.float32)
        img = img * rnd.uniform(0.6, 1.0) + rnd.uniform(0, 0.3)
        X.append(np.stack([img * 255] * 3, -1).astype(np.uint8))
        Y.append(y)
    return np.array(X), np.array(Y)


def _nn(impl, seed):
    ht = legacy_mod(impl, "nn", "hex_train")
    HexNet, train = need(ht, "HexNet"), need(ht, "train_infogap")
    to_lat, norm = need(ht, "images_to_lattices"), need(ht, "normalize_lattices")
    rnd = random.Random(seed * 29 + 4)
    Xtr, Ytr = _textures(rnd, 192)
    Xte, Yte = _textures(rnd, 96)
    lat = norm(to_lat(np.concatenate([Xtr, Xte]), cells_across=16))
    xtr, xte = lat[:192], lat[192:]
    net = HexNet(n_kernels=4, n_mix=8, n_class=4, seed=7 + seed)
    acc0 = net.accuracy(xte, Yte)
    t0 = time.perf_counter()
    rep = train(net, xtr, Ytr, max_steps=60, batch=96, seed=7 + seed)
    sec = time.perf_counter() - t0
    acc = net.accuracy(xte, Yte)
    return {"test_acc": round(acc, 4), "init_acc": round(acc0, 4), "train_s": round(sec, 2),
            "final_D": rep.get("final_D"), "growths": rep.get("growths")}


RAW = True


def run(impl, seed, part="hexgen"):
    return {"hexgen": _hexgen, "scene": _scene, "stcnn": _stcnn, "nn": _nn}[part](impl, seed)
