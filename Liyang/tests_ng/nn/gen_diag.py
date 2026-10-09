# -*- coding: utf-8 -*-
"""gen 兑现率诊断：ng 未兑现部件分类 + 用 ng 严格校验器公平校验旧实现输出。

用法：OPENBLAS_NUM_THREADS=1 PYTHONPATH=<repo> python tests_ng/nn/gen_diag.py [diag|fair|all] [size] [seed0] [n]
协议与 bench_nn._protocol 相同（R2：k∈[1,3] 个部件，随机形状/颜色/格/花纹/尺寸）。

严格校验（ng 口径，阈值不变：coverage ≥ 0.9、spill ≤ 0.1）作用于旧实现时：
- 足迹 = 旧绘制函数每次调用实际改动的像素（猴补丁记录），可见 = 改动且未被后画者再改动；
- 「应画掩码」= 旧绘制函数在空白画布、同中心同半径下按**旧自身几何/花纹相位约定**画出的像素
  （旧三角形只画上半、花纹绝对相位 x≡0——不拿 ng 几何去罚旧实现）；
- 读数（落格/众数色/花纹）全部来自加噪前成图的可见像素，与 ng 完全同一函数。
"""
from __future__ import annotations

import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from lingshu_ng.gen import hexgen as H                     # noqa: E402
from lingshu_ng.gen.attrs import PALETTE                   # noqa: E402
from lingshu_ng.gen.verify import judge, mode_color, read_pattern, zone_of_mask, COVERAGE_MIN, SPILL_MAX  # noqa: E402
from lingshu_ng.nn.render import Footprint                 # noqa: E402

GEN_SHAPES, GEN_COLORS = ["circle", "triangle", "stripe"], ["red", "green", "blue"]
POS9 = [f"r{i}" for i in range(9)]
PATS = ["solid", "striped", "dotted"]


def protocol_cases(seed0, n, attrs=True):
    """与 bench_nn._protocol 逐题相同的题目序列。"""
    rng = np.random.default_rng(seed0)
    out = []
    for t in range(n):
        k = int(rng.integers(1, 4))
        parts = [{"shape": GEN_SHAPES[rng.integers(3)], "color": GEN_COLORS[rng.integers(3)],
                  "zone": POS9[rng.integers(9)],
                  **({"pattern": PATS[rng.integers(3)], "size": ["small", "medium", "large"][rng.integers(3)]}
                     if attrs else {})} for _ in range(k)]
        out.append((t, parts))
    return out


def classify(entry, spec, all_entries):
    """未兑现原因（按先后取第一个）。"""
    rgb = PALETTE[spec["color"]]
    if entry is None or entry.get("painted_px", 0) == 0:
        return "完全被遮挡/未画"
    same = [e for e in all_entries if e is not entry and e["zone_intended"] == spec["zone"]]
    tag = "同格" if same else "单格"
    if not entry.get("separated", True):
        tag += "·叠放(摆位无解)"
    if entry.get("zone_landed") != spec["zone"]:
        return tag + "·落格偏移"
    if entry.get("color_rgb") != tuple(rgb):
        return tag + "·众数色错"
    if entry.get("pattern_read") != spec.get("pattern", "solid"):
        return tag + "·花纹读错"
    if entry.get("coverage", 0) < COVERAGE_MIN:
        return tag + "·覆盖率不足(被遮挡)"
    if entry.get("spill", 1) > SPILL_MAX:
        return tag + "·溢出"
    return tag + "·其他"


def diag(size, seed0, n):
    cnt = collections.Counter()
    ok = tot = 0
    examples = []
    for t, parts in protocol_cases(seed0, n):
        r = H.render(parts, size=size, seed=t)
        v = H.verify_parts(parts, r.log)
        ok, tot = ok + v["matched"], tot + v["total"]
        for m in v["misses"]:
            c = classify(m["log"], m["spec"], r.log)
            cnt[c] += 1
            if len(examples) < 12:
                examples.append({"t": t, "parts": parts, "miss": m["part"], "class": c,
                                 "cov": m["log"].get("coverage"), "sep": m["log"].get("separated")})
    return {"size": size, "seed0": seed0, "n": n, "rate": round(ok / tot, 4), "matched": ok, "total": tot,
            "classes": dict(cnt), "examples": examples}


# ---------------- 旧实现 + ng 严格校验 ----------------

def legacy_strict(size, seed0, n):
    import lingshu.nn.hex_gen as LG
    lenient_ok = strict_ok = tot = 0
    cls = collections.Counter()
    orig_p, orig_poly = LG._paint, LG._paint_polygon
    for t, parts in protocol_cases(seed0, n):
        calls = []

        def rec(fn):
            def wrapped(img, shape, cx, cy, rad, col, pattern):
                before = img.copy()
                fn(img, shape, cx, cy, rad, col, pattern)
                blank = np.zeros_like(img)
                fn(blank, shape, cx, cy, rad, (255, 255, 255), pattern)
                calls.append({"changed": np.any(img != before, axis=-1), "expected": np.any(blank != 0, axis=-1)})
            return wrapped
        LG._paint, LG._paint_polygon = rec(orig_p), rec(orig_poly)
        try:
            clean, log = LG.render_relations(parts, size=size, seed=t, noise=False)
        finally:
            LG._paint, LG._paint_polygon = orig_p, orig_poly
        lenient_ok += LG.verify_constructive(parts, log)["matched"]
        for i, (p, e, c) in enumerate(zip(parts, log, calls)):
            vis = c["changed"].copy()
            for later in calls[i + 1:]:
                vis &= ~later["changed"]
            rgb = PALETTE[p["color"]]
            exp = c["expected"]
            on = np.all(clean == np.asarray(rgb, dtype=clean.dtype), axis=-1)
            ch = c["changed"]
            entry = {"part": i, "shape": e["shape"], "size": e["size"], "zone_intended": p["zone"],
                     "painted_px": int(vis.sum()), "zone_landed": zone_of_mask(vis),
                     "color_rgb": mode_color(clean, vis), "pattern_read": read_pattern(vis),
                     "coverage": round(float((exp & on).sum() / exp.sum()), 4) if exp.any() else 0.0,
                     "spill": round(float((ch & ~exp).sum() / max(1, ch.sum())), 4) if ch.any() else 1.0}
            good = judge(p, entry, rgb)
            strict_ok += int(good)
            tot += 1
            if not good:
                same = sum(q["zone"] == p["zone"] for q in parts) > 1
                cls[classify(dict(entry, separated=True), p, [dict(x, zone_intended=q["zone"])
                                                              for x, q in zip(log, parts)] if same else [])] += 1
    return {"size": size, "seed0": seed0, "n": n, "legacy_lenient": round(lenient_ok / tot, 4),
            "legacy_strict": round(strict_ok / tot, 4), "strict_matched": strict_ok, "total": tot,
            "strict_miss_classes": dict(cls)}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 96
    seed0 = int(sys.argv[3]) if len(sys.argv) > 3 else 98
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    res = {}
    if mode in ("diag", "all"):
        res["ng"] = diag(size, seed0, n)
    if mode in ("fair", "all"):
        res["legacy"] = legacy_strict(size, seed0, n)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
