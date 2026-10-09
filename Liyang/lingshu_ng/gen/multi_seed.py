# -*- coding: utf-8 -*-
"""multi_seed · 「同 prompt 多次渲染」量测的无语料部分（迁自 ``lingshu.gen.hexgen_multi_seed``）。

迁移范围：受控 prompt 模板解析、确定性 prompt 子集选择、稳定件 id、渲染件清单、以及三件事的统计
（①同 prompt 多张读出稳定性 ②真值兑现率 ③件内方差 vs 类间差 + 空读率）。
不迁：黑箱生成（本地扩散管线）与冻结读者（``hexgen_c1_real`` 的抠图/特征，依赖黑箱语料标定）——
``summarize`` 接收任意读者给出的读数行 ``{sid, seed, n_read, shapes, colors, patterns, cells, feats}``。

有意差异：件 id 由 :func:`lingshu_ng.gen.ids.stable_int` 给出（旧实现 ``hash((sid, seed)) % 1e9`` 随
``PYTHONHASHSEED`` 变化，#198）；统计口径与旧 ``summarize`` 逐项相同。
"""
from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

from .ids import stable_int

PROMPT_RE = re.compile(r"^flat vector illustration,\s+(one|two|three|four|five)\s+"
                       r"([a-z]+)\s+(?:([a-z]+)\s+)?([a-z]+)\(s\)\s+in the\s+(.*)$")
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
SHAPES = ("circle", "triangle", "square", "rectangle", "diamond", "hexagon", "star", "heart")
COLORS = ("red", "green", "blue", "yellow", "orange", "purple", "pink", "black", "brown", "gray", "white")
FEATS = ("extent", "log_aspect", "solidity", "compactness", "n_peaks", "peak_prom", "peak_flat",
         "harm1", "harm2", "harm3", "harm4", "harm5", "harm6", "harm7", "harm8")
SEEDS = (11, 22, 33, 44, 55)
_L, _R = {"r0", "r3", "r6"}, {"r2", "r5", "r8"}
ZONE_CELLS = {
    "upper left": {"r0"}, "upper le": {"r0"}, "upper l": {"r0"}, "top left": {"r0"},
    "top center": {"r1"}, "top cente": {"r1"}, "top cent": {"r1"}, "top cen": {"r1"},
    "upper right": {"r2"}, "upper right ar": {"r2"}, "upper ri": {"r2"}, "top right": {"r2"},
    "left side": _L, "left s": _L, "left": _L, "center": {"r4"}, "centre": {"r4"},
    "right side": _R, "right si": _R, "right s": _R, "right": _R,
    "lower left": {"r6"}, "lower le": {"r6"}, "bottom left": {"r6"},
    "bottom center": {"r7"}, "bottom cent": {"r7"}, "bottom c": {"r7"},
    "lower right": {"r8"}, "lower ri": {"r8"}, "bottom right": {"r8"},
    "top": {"r0", "r1", "r2"}, "bott": {"r6", "r7", "r8"}, "bottom": {"r6", "r7", "r8"},
}


def parse_prompt(p: Optional[str]) -> Optional[Dict]:
    """``flat vector illustration, {n} {color}[ {pattern}] {shape}(s) in the {zone}…`` → 五列真值；否则 None。

    方位短语按最长前缀匹配（prompt 被截断到 64 字符）；匹配不到时 ``cells`` 为 None。"""
    m = PROMPT_RE.match(p or "")
    if not m:
        return None
    num, color, pat, shape, rest = m.groups()
    if color not in COLORS or shape not in SHAPES or (pat and pat not in ("striped", "dotted")):
        return None
    zone_text = re.sub(r"\s*(area)?\s*,?\s*(plain)?\s*$", "", rest.strip()).strip()
    cells = next((set(ZONE_CELLS[ph]) for ph in sorted(ZONE_CELLS, key=len, reverse=True)
                  if zone_text.startswith(ph)), None)
    return {"n": NUM_WORDS[num], "color": color, "pattern": pat or "plain", "shape": shape,
            "zone_text": zone_text, "cells": cells}


def pick_prompts(lib: Iterable[Dict], n: int) -> List[Dict]:
    """确定性子集：``vs_s*`` 记录中 prompt 可被受控模板解析者，按 name 升序、prompt 去重取前 n 条。

    判据是“能通过受控模板解析”而非“名字排序靠前”（旧 R293 首跑选中风景域 ``ls_*`` 的事故）。"""
    seen, out = set(), []
    for r in sorted(lib, key=lambda x: x["name"]):
        p = (r.get("tags") or {}).get("prompt")
        if not str(r.get("name", "")).startswith("vs_s") or not p or p in seen or parse_prompt(p) is None:
            continue
        seen.add(p)
        out.append({"sid": r["name"], "prompt": p})
        if len(out) >= n:
            break
    return out


def item_id(sid: str, seed: int) -> int:
    """多 seed 件的稳定整数 id（跨进程一致）。"""
    return stable_int(sid, int(seed))


def render_rows(prompts: Sequence[Dict], seeds: Sequence[int], outdir: str) -> List[Dict]:
    """渲染件清单 ``{sid, prompt, seed, path, id, exists}``（路径约定 ``outdir/sid/s{seed}.png``）。"""
    rows = []
    for it in prompts:
        for s in seeds:
            path = os.path.join(outdir, it["sid"], f"s{s}.png")
            rows.append({"sid": it["sid"], "prompt": it["prompt"], "seed": int(s), "path": path,
                         "id": item_id(it["sid"], s), "exists": os.path.isfile(path)})
    return rows


def _by_sid(reads: Sequence[Dict]) -> Dict[str, List[Dict]]:
    """读数按 sid 分组（保持输入顺序）。"""
    out: Dict[str, List[Dict]] = {}
    for r in reads:
        out.setdefault(r["sid"], []).append(r)
    return out


def _mean_or_none(v: List[float]) -> Optional[float]:
    """均值（4 位）；空列表为 None。"""
    return round(float(np.mean(v)), 4) if v else None


def stability(by_sid: Dict[str, List[Dict]]) -> Dict[str, Optional[float]]:
    """① 同 prompt 相邻两张的多重集/数量一致率（按 prompt 平均）；单张 prompt 不计。"""
    keys = {"shape": "shapes", "color": "colors", "pattern": "patterns", "cell": "cells", "count": "n_read"}
    stab: Dict[str, List[float]] = {k: [] for k in keys}
    for rs in by_sid.values():
        if len(rs) < 2:
            continue
        for k, field in keys.items():
            stab[k].append(sum(a[field] == b[field] for a, b in zip(rs, rs[1:])) / (len(rs) - 1))
    order = ("shape", "color", "pattern", "count", "cell")
    return {k: _mean_or_none(stab[k]) for k in order}


def honored(by_sid: Dict[str, List[Dict]], truth_of: Dict[str, Optional[Dict]]) -> Dict[str, Optional[float]]:
    """② 真值兑现率：每图读出多重集 == prompt 真值（n 件同形状/同色/同花纹）、读出件数 == n。"""
    hon: Dict[str, List[float]] = {"shape": [], "color": [], "pattern": [], "count": []}
    for sid, rs in by_sid.items():
        t = truth_of.get(sid)
        if not t:
            continue
        for r in rs:
            for k in ("shape", "color", "pattern"):
                hon[k].append(float(r[k + "s"] == sorted([t[k]] * t["n"])))
            hon["count"].append(float(r["n_read"] == t["n"]))
    return {k: _mean_or_none(v) for k, v in hon.items()}


def within_between(by_sid: Dict[str, List[Dict]], cls_of: Dict[str, Optional[str]],
                   dims: Sequence[str] = FEATS) -> Dict:
    """③ 件内（同类图均值的 sd，按类取中位）vs 类间（类中心的 sd）逐维比；空读图单独计数。"""
    vecs: Dict[str, List] = {}
    for sid, rs in by_sid.items():
        if cls_of.get(sid):
            vecs.setdefault(cls_of[sid], []).extend(r["feats"] for r in rs)
    nd, within, means, n_empty = len(dims), [], [], 0
    for per_img in vecs.values():
        with_obj = [im for im in per_img if len(im)]
        n_empty += len(per_img) - len(with_obj)
        if len(with_obj) < 2:
            continue
        img_means = np.stack([np.stack(im).mean(axis=0) for im in with_obj])
        means.append(img_means.mean(axis=0))
        within.append(img_means.std(axis=0, ddof=1))
    between = np.stack(means).std(axis=0, ddof=1) if len(means) > 1 else np.zeros(nd)
    within_m = np.median(np.stack(within), axis=0) if within else np.zeros(nd)
    ratio = np.where(between > 1e-9, within_m / np.maximum(between, 1e-9), 0.0)
    return {"dims": list(dims), "within_prompt_sd": [round(float(x), 5) for x in within_m],
            "between_class_sd": [round(float(x), 5) for x in between],
            "ratio_within_over_between": [round(float(x), 3) for x in ratio],
            "median_ratio": round(float(np.median(ratio)), 3),
            "worst_dims": [dims[i] for i in np.argsort(-ratio)[:5]], "n_empty": n_empty}


def summarize(reads: Sequence[Dict], items: Sequence[Dict], dims: Sequence[str] = FEATS) -> Dict:
    """三件事的数字（键与旧 ``hexgen_multi_seed.summarize`` 相同）。``items`` 每项含 sid/truth/shape。"""
    by_sid = _by_sid(reads)
    wb = within_between(by_sid, {it["sid"]: it.get("shape") for it in items}, dims)
    n_empty = wb.pop("n_empty")
    return {"n_prompt": len(by_sid), "n_img": len(reads), "n_img_empty": n_empty,
            "empty_rate": round(n_empty / max(1, len(reads)), 4), "stability": stability(by_sid),
            "honored": honored(by_sid, {it["sid"]: it.get("truth") for it in items}),
            "within_vs_between": wb}
