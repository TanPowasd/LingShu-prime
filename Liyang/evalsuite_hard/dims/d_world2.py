"""H-WLD2（hard-rules-v2 新增子项，v1 的 d_world.py 不动）：

part=scene20k     2 万实体场景：wander/seek/avoid/flee/follow 混合（目标为另一实体或巡逻路径，与 v1 同构），
                  逐 tick 检查单 tick 位移 ≤ speed、边界内、有限；至多 30 tick，作业内 60s 截止（截止前完成的 tick 计耗时，
                  一 tick 都没完成时耗时按 60s/实体数 的下界记）。维分 0.5·不变量 + 0.5·对数耗时分。
part=hexgen_open  hex_gen 开放词汇组合泛化——只用旧模块自己声明的词汇面（INTENT_MAP 记出处）：
                  11 色（R15 OPEN_COLORS 含黑/白/灰）、9 形状（含「条」）、方位三种写法（复合词含「中央」、「X方」、
                  R43 单字方位「左/右/上/下/中间」）、花纹同义词（实心/条纹/条形/点纹/斑点）、尺寸词，
                  子句内词序 4 种模板随机、分隔符（，、；）随机，另有 30% 概率附加只含背景词的子句（R46，应不生成部件）。
                  评编译正确率（部件数 + 五元组全对）与像素预言机（同 v1：目标色块落在目标格、占比 ≥70%；
                  黑色与噪声底色同域（底噪 0–43），像素项不判黑色部件，只判编译）。
"""
import math
import random
import time

import numpy as np

from hadapt import legacy_mod, need
from dims.d_world import _pixel_ok, RGB as RGB_V1


def _scene20k(impl, seed, n=20000, ticks=30, deadline=60.0):
    import warnings
    warnings.filterwarnings("ignore")
    ss = legacy_mod(impl, "world", "scene_simulator")
    _Sim = need(ss, "SceneSimulator")
    rnd = random.Random(seed * 41 + 7)
    size = 256
    try:
        s = _Sim(size=size, seed=seed + 11)
    except TypeError:
        s = _Sim(size=size)
    s.add_path("p", [(4, 1.5, 4), (size - 5, 1.5, 4), (size - 5, 1.5, size - 5), (4, 1.5, size - 5)])
    ids, spec = [], []
    for k in range(n):
        x = rnd.random()
        beh = "wander" if x < 0.4 else "seek" if x < 0.6 else "avoid" if x < 0.75 else "flee" if x < 0.85 else "follow"
        sp = round(rnd.uniform(0.1, 1.5), 2)
        pos = (rnd.uniform(1, size - 1), 1.5, rnd.uniform(1, size - 1))
        ids.append(s.add_entity("a", behavior=beh, pos=pos, speed=sp))
        spec.append((beh, sp, pos))
    for k, (beh, sp, pos) in enumerate(spec):
        s.entities[ids[k]].goal = "p" if beh == "follow" else ids[rnd.randrange(n)]
    prev = {i: spec[k][2] for k, i in enumerate(ids)}
    speeds = {i: spec[k][1] for k, i in enumerate(ids)}
    ok_sp = ok_b = ok_f = True
    done, t_step = 0, 0.0
    t_begin = time.perf_counter()
    while done < ticks and time.perf_counter() - t_begin < deadline:
        t0 = time.perf_counter()
        s.step(1)
        t_step += time.perf_counter() - t0
        done += 1
        pos = s.entity_positions()
        for i, p in pos.items():
            if i not in speeds:
                continue
            if not all(math.isfinite(v) for v in p):
                ok_f = False
                continue
            if math.hypot(p[0] - prev[i][0], p[2] - prev[i][2]) > speeds[i] + 0.011:
                ok_sp = False
            if not (0 <= p[0] <= size and 0 <= p[2] <= size):
                ok_b = False
            prev[i] = p
    us = (t_step / (n * done) * 1e6) if done else (deadline / n * 1e6)
    inv = {"speed_bound": float(ok_sp and done > 0), "in_bounds": float(ok_b and done > 0), "finite": float(ok_f and done > 0)}
    return dict(inv, ticks_done=done, us_per_entity_tick=round(us, 3), n=n)


OPEN_COLORS = {"红": "red", "绿": "green", "蓝": "blue", "黄": "yellow", "橙": "orange", "紫": "purple", "粉": "pink",
               "棕": "brown", "黑": "black", "白": "white", "灰": "gray"}
OPEN_RGB = dict({k: v for k, v in RGB_V1.items()}, white=[(245, 245, 245)], gray=[(128, 128, 128)])
OPEN_SHAPES = {"圆": "circle", "三角": "triangle", "条": "stripe", "方": "square", "矩形": "rectangle", "星": "star",
               "心": "heart", "六边": "hexagon", "菱": "diamond"}
SHAPE_SURF = {"圆": ["圆", "圆形"], "三角": ["三角", "三角形"], "条": ["条"], "方": ["方块", "方形"], "矩形": ["矩形"],
              "星": ["星", "星形"], "心": ["心", "心形"], "六边": ["六边形"], "菱": ["菱形"]}
POS_COMPOUND = {"左上": "r0", "上中": "r1", "右上": "r2", "左中": "r3", "中心": "r4", "中央": "r4", "右中": "r5",
                "左下": "r6", "下中": "r7", "右下": "r8"}
POS_SINGLE = {"左": "r3", "右": "r5", "上": "r1", "下": "r7", "中间": "r4"}
PATTERN_SURF = {"": "solid", "实心": "solid", "条纹": "striped", "条形": "striped", "点纹": "dotted", "斑点": "dotted"}
SIZE_SURF = {"": "medium", "大": "large", "小": "small"}
BG_CLAUSES = ["白底", "灰底", "渐变蓝底", "渐变粉底", "渐变绿底", "深色底"]


def _open_prompt(rnd):
    k = rnd.randint(1, 4)
    zones_used, segs, parts = set(), [], []
    colors = rnd.sample(list(OPEN_COLORS), k)
    for c in colors:
        while True:
            kind = rnd.random()
            if kind < 0.45:
                pw = rnd.choice(list(POS_COMPOUND)); z = POS_COMPOUND[pw]
            elif kind < 0.7:
                pw = rnd.choice(list(POS_COMPOUND)); z = POS_COMPOUND[pw]
                pw = pw + "方" if pw not in ("中心", "中央") else pw
            else:
                pw = rnd.choice(list(POS_SINGLE)); z = POS_SINGLE[pw]
            if z not in zones_used:
                zones_used.add(z)
                break
        sh = rnd.choice(list(OPEN_SHAPES)); shw = rnd.choice(SHAPE_SURF[sh])
        pa = rnd.choice(list(PATTERN_SURF)); si = rnd.choice(list(SIZE_SURF))
        cw = c + rnd.choice(["色", ""])
        t = rnd.randrange(4)
        if t == 2 and not pa:
            t = 0
        if t == 0:
            seg = f"{pw}有一个{si}{cw}{pa}{shw}"
        elif t == 1:
            seg = f"{si}{cw}{pa}{shw}在{pw}"
        elif t == 2:
            seg = f"{pw}是{pa}的{si}{cw}{shw}"
        else:
            seg = f"一个{cw}{si}{pa}{shw}位于{pw}"
        segs.append(seg)
        parts.append({"zone": z, "color": OPEN_COLORS[c], "shape": OPEN_SHAPES[sh], "pattern": PATTERN_SURF[pa],
                      "size": SIZE_SURF[si]})
    text = segs[0]
    for sg in segs[1:]:
        text += rnd.choice(["，", "、", "；"]) + sg
    if rnd.random() < 0.3:
        text += "，" + rnd.choice(BG_CLAUSES)
    return text, parts


def _pixel_ok_open(img, part):
    if part["color"] == "black":
        return None
    if part["color"] in RGB_V1:
        return _pixel_ok(img, part)
    img = np.asarray(img)[..., :3].astype(int)
    S = img.shape[0]
    q = int(part["zone"][1]); r, c = q // 3, q % 3
    mask = np.zeros(img.shape[:2], bool)
    for rgb in OPEN_RGB[part["color"]]:
        mask |= np.abs(img - np.array(rgb)).max(axis=-1) <= 45
    cell = np.zeros_like(mask)
    cell[r * S // 3:(r + 1) * S // 3, c * S // 3:(c + 1) * S // 3] = True
    inside, total = int((mask & cell).sum()), int(mask.sum())
    return inside >= max(6, int(0.001 * S * S)) and inside >= 0.7 * total


def _hexgen_open(impl, seed, n=80):
    hg = legacy_mod(impl, "nn", "hex_gen")
    gen = need(hg, "generate_from_text")
    comp = need(hg, "compile_description")
    rnd = random.Random(seed * 53 + 17)
    c_ok = p_ok = p_n = tot = prompts_ok = errs = 0
    misses = []
    for i in range(n):
        text, parts = _open_prompt(rnd)
        try:
            cp = comp(text)["parts"]
            cpk = [{k: p.get(k) for k in ("zone", "color", "shape", "pattern", "size")} for p in cp]
        except Exception:
            cpk, errs = [], errs + 1
        try:
            img = gen(text, size=96, seed=11 + i)["image"]
        except Exception:
            img, errs = None, errs + 1
        all_ok = len(cpk) == len(parts)
        for j, p in enumerate(parts):
            tot += 1
            ok = len(cpk) == len(parts) and cpk[j] == p
            c_ok += int(ok)
            all_ok = all_ok and ok
            px = _pixel_ok_open(img, p) if img is not None else False
            if px is not None:
                p_n += 1
                p_ok += int(bool(px))
        prompts_ok += int(all_ok)
        if not all_ok and len(misses) < 8:
            misses.append({"text": text, "want": parts, "got": cpk})
    return {"compile_acc": round(c_ok / tot, 4), "prompt_exact": round(prompts_ok / n, 4),
            "pixel_acc": round(p_ok / max(1, p_n), 4), "parts": tot, "pixel_parts": p_n, "errors": errs,
            "misses": misses}


def run(impl, seed, part="scene20k"):
    if part == "scene20k":
        return _scene20k(impl, seed)
    return _hexgen_open(impl, seed)


RAW = True
