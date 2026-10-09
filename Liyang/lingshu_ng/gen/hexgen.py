# -*- coding: utf-8 -*-
"""hexgen · 白箱文生图主干：文字 → 关系 → 合法窗摆位 → 层序渲染 → 读像素验证。

- ``compile_text``：:mod:`lingshu_ng.nn.text` 开放词表解析；缺项按 DEFAULTS 补并逐项落账；
  背景词只决定背景，不产出部件颜色、不产生部件。
- ``render``：背景 → 摆位（:mod:`layout`，同格不相交，否则叠放）→ ``compose``（z 显式：
  部件 ``z`` 字段，缺省按描述顺序后画在上）→ 每部件像素读数（:mod:`verify`）→ 饱和加噪。
- 标识：场景与部件 id 均为 sha256（:mod:`ids`），跨进程稳定。
- 变换：9 宫格映射表作用于关系层；平移出界部件丢弃并落账。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from ..nn import text as T
from ..nn.render import POLY_SHAPES, RENDERABLE, DrawCall, Footprint, compose, paint
from . import layout
from .attrs import BASE_COLORS, PALETTE, extract_attributes
from .ids import stable_id
from .verify import read_part, verify

DEFAULTS = {"shape": "circle", "color": "red", "zone": "r4", "pattern": "solid", "size": "medium"}
RADIUS_DIV = {"small": 14, "medium": 10, "large": 7}
ATTR_CALIB_96 = {"tx_solid": 2.78, "vert_striped": 0.665, "area_cut": 397.0}
ZONE_TRANSFORMS: Dict[str, Callable[[int, int], Tuple[int, int]]] = {
    "rot90cw": lambda r, c: (c, 2 - r), "rot90ccw": lambda r, c: (2 - c, r),
    "rot180": lambda r, c: (2 - r, 2 - c), "fliph": lambda r, c: (r, 2 - c), "flipv": lambda r, c: (2 - r, c)}


def zone_rc(zone: str) -> Tuple[int, int]:
    """r{row*3+col} → (row, col)。"""
    q = int(zone[1:])
    return q // 3, q % 3


def rc_zone(r: int, c: int) -> str:
    """(row, col) → r{row*3+col}。"""
    return f"r{r * 3 + c}"


def radius(size: int, size_attr: str) -> int:
    """尺寸档 → 像素半径（旧口径：size//14 / //10 / //7）。"""
    return size // RADIUS_DIV.get(size_attr, 10)


def compile_text(text: str) -> Dict:
    """中文描述 → {parts, defaults_applied, background, conflicts, source, id}。"""
    parts, defaults, conflicts, background = [], [], [], None
    for cl in T.parse(text, vocab="open", keep_empty=True):
        background = background or cl.background
        conflicts += [dict(c, text=cl.text) for c in cl.conflicts]
        if not (cl.shape or cl.color or cl.pos):
            continue
        part = {}
        for key, val in (("shape", cl.shape), ("color", cl.color), ("zone", cl.pos),
                         ("pattern", cl.pattern), ("size", cl.size)):
            part[key] = val if val is not None else DEFAULTS[key]
            if val is None:
                defaults.append({"text": cl.text, "field": key, "applied": DEFAULTS[key]})
        parts.append(part)
    return {"parts": parts, "defaults_applied": defaults, "background": background, "conflicts": conflicts,
            "source": text, "id": stable_id("compile", text)}


def gradient(s: int, c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> np.ndarray:
    """纵向渐变背景。"""
    t = np.linspace(0, 1, s)[:, None]
    arr = np.zeros((s, s, 3), dtype=np.uint8)
    for i in range(3):
        arr[:, :, i] = (c1[i] + (c2[i] - c1[i]) * t).astype(np.uint8)
    return arr


BACKGROUNDS: Dict[str, Callable[[int], np.ndarray]] = {
    "clean_white": lambda s: np.full((s, s, 3), 245, np.uint8), "gray": lambda s: np.full((s, s, 3), 200, np.uint8),
    "dark": lambda s: np.full((s, s, 3), 40, np.uint8),
    "grad_blue": lambda s: gradient(s, (240, 248, 255), (70, 130, 180)),
    "grad_pink": lambda s: gradient(s, (255, 240, 245), (219, 112, 147)),
    "grad_green": lambda s: gradient(s, (240, 255, 240), (60, 179, 113))}


def make_background(name: str, size: int, rng: np.random.Generator) -> np.ndarray:
    """背景：命名背景或缺省低噪声底（旧 'white' 键 = 噪声底，保持回读标定兼容）。"""
    key = T.BACKGROUND_WORDS.get(name, name)
    fn = BACKGROUNDS.get(key)
    return fn(size) if fn is not None else (rng.random((size, size, 3)) * 25).astype(np.uint8)


@dataclass
class RenderResult:
    """渲染产物：成图（含噪）、加噪前成图、落格日志、绘制调用、场景 id。"""

    image: np.ndarray
    clean: np.ndarray
    log: List[Dict]
    calls: List[DrawCall] = field(default_factory=list)
    scene_id: str = ""


def _draw_calls(parts: List[Dict], size: int, rng: np.random.Generator,
                background: Optional[np.ndarray] = None) -> Tuple[List[DrawCall], List[Dict]]:
    rads = [radius(size, p.get("size", "medium")) for p in parts]
    specs = None
    if background is not None and all(p.get("shape", "circle") in RENDERABLE for p in parts):
        specs = [{"shape": p.get("shape", "circle"), "pattern": p.get("pattern", "solid"),
                  "rgb": PALETTE.get(p.get("color", "red"), PALETTE["red"]), "zone": p["zone"],
                  "size": p.get("size", "medium"), "rad": r, "z": int(p.get("z", 0)), "z_explicit": "z" in p}
                 for p, r in zip(parts, rads)]
    plans = layout.plan([p["zone"] for p in parts], rads, size, rng, max(1, size // 24), specs, background)
    calls = []
    for i, (p, pl, rad) in enumerate(zip(parts, plans, rads)):
        calls.append(DrawCall(p.get("shape", "circle"), pl["cx"], pl["cy"], rad,
                              PALETTE.get(p.get("color", "red"), PALETTE["red"]),
                              p.get("pattern", "solid"), int(pl.get("z", p.get("z", 0)))))
    return calls, plans


def render(parts: List[Dict], size: int = 48, seed: int = 7, noise: bool = True, background: str = "white",
           painter: Optional[Callable] = None, supersample: int = 1) -> RenderResult:
    """部件关系 → 成图 + 像素读数日志（读数在加噪前、超采样原分辨率上量）。"""
    rng = np.random.default_rng(seed)
    big = size * max(1, supersample)
    bg = make_background(background, big, rng)
    calls, plans = _draw_calls(parts, big, rng, bg)
    ok = [c.shape in RENDERABLE for c in calls]
    img, feet_ok = compose(bg, [c for c, k in zip(calls, ok) if k], painter or paint)
    it = iter(feet_ok)
    empty = np.zeros(img.shape[:2], dtype=bool)
    feet = [next(it) if k else Footprint(empty, empty) for k in ok]
    log = []
    for i, (p, c, pl, ft) in enumerate(zip(parts, calls, plans, feet)):
        e = {"part": i, "id": stable_id("part", i, p), "shape": c.shape, "color": p.get("color", "red"),
             "zone_intended": p["zone"], "pattern": c.pattern, "size": p.get("size", "medium"),
             "center": (c.cx, c.cy), "rad": c.rad, "z": c.z, "separated": pl["separated"]}
        e.update(read_part(img, ft, {"shape": c.shape, "pattern": c.pattern}, c.cx, c.cy, c.rad, c.rgb))
        log.append(e)
    clean = img.copy()
    if noise:
        img = np.clip(img.astype(np.int16) + (rng.random(img.shape) * 18).astype(np.int16), 0, 255).astype(np.uint8)
    if supersample > 1:
        from PIL import Image
        img = np.asarray(Image.fromarray(img).resize((size, size), Image.LANCZOS))
    return RenderResult(img, clean, log, calls, stable_id("scene", parts, size, seed, background, supersample))


def verify_parts(parts: List[Dict], log: List[Dict]) -> Dict:
    """构造性兑现率（读数 vs 描述，见 :mod:`verify`）。"""
    return verify(parts, log, PALETTE)


def readback(img: np.ndarray, parts: List[Dict], log: List[Dict], calib: Optional[Dict] = None) -> Dict:
    """次级指标：extract_attributes 独立读花纹/尺寸（只计基础三色；不可见部件计未命中）。"""
    c = calib or ATTR_CALIB_96
    pat_ok = pat_n = size_ok = size_n = 0
    misses = []
    for i, p in enumerate(parts):
        e = next((x for x in log if x["part"] == i), None)
        if e is None or p["color"] not in BASE_COLORS:
            continue
        pat_n += 1
        if e.get("zone_landed") is None:
            misses.append({"part": i, "spec_pattern": p.get("pattern"), "read": None, "zone": None})
            continue
        a = extract_attributes(img, e["zone_landed"], p["color"], c, shape_hint=p["shape"])
        hit = a.get("pattern") == p.get("pattern", "solid")
        pat_ok += int(hit)
        if not hit:
            misses.append({"part": i, "spec_pattern": p.get("pattern"), "read": a.get("pattern"),
                           "zone": e["zone_landed"]})
        if p["shape"] == "circle" and p.get("size") in ("small", "large"):
            size_n += 1
            size_ok += int(a.get("size") == p["size"])
    return {"pattern_acc": round(pat_ok / max(1, pat_n), 4), "n_pattern": pat_n,
            "size_acc": round(size_ok / max(1, size_n), 4) if size_n else None, "n_size": size_n, "misses": misses}


def transform(parts: List[Dict], op: str) -> List[Dict]:
    """9 宫格映射作用于关系层；未知变换报错。"""
    if op not in ZONE_TRANSFORMS:
        raise ValueError(f"未知变换 {op}（可用: {sorted(ZONE_TRANSFORMS)}）")
    return [{**p, "zone": rc_zone(*ZONE_TRANSFORMS[op](*zone_rc(p["zone"])))} for p in parts]


def shift(parts: List[Dict], dr: int, dc: int) -> Dict:
    """关系层平移：出界部件丢弃并落账（裁剪视窗语义）。"""
    kept, dropped = [], []
    for i, p in enumerate(parts):
        r, c = zone_rc(p["zone"])
        nr, nc = r + dr, c + dc
        if 0 <= nr <= 2 and 0 <= nc <= 2:
            kept.append({**p, "zone": rc_zone(nr, nc)})
        else:
            dropped.append({"part": i, "from": p["zone"], "to": f"({nr},{nc})"})
    return {"parts": kept, "dropped": dropped}


def generate(text: str, size: int = 48, seed: int = 7, op: Optional[str] = None, supersample: int = 1,
             painter: Optional[Callable] = None) -> Dict:
    """端到端：编译 →（变换）→ 渲染 → 构造性验证 → 回读（≥96px）。"""
    comp = compile_text(text)
    parts = transform(comp["parts"], op) if op else comp["parts"]
    res = render(parts, size=size, seed=seed, background=comp["background"] or "white",
                 supersample=supersample, painter=painter)
    rb = readback(res.image, parts, res.log) if size >= 96 else {"note": "48px 低于提取器面积下限，不计"}
    return {"image": res.image, "parts": parts, "log": res.log, "constructive": verify_parts(parts, res.log),
            "readback": rb, "defaults_applied": comp["defaults_applied"], "transform": op,
            "scene_id": res.scene_id, "conflicts": comp["conflicts"]}
