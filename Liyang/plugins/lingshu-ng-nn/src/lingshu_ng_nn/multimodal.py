# -*- coding: utf-8 -*-
"""multimodal · 图文共同识别：象限级子物体检测 + 文字子句对齐 → 一致性四态。

- ``spatial_detect``：L1 能量按 3×3 象限求份额；最强象限必选，其余份额 > (1/9)·exist_mult 追加；
  入选象限裁剪后**一次批量前向**（旧实现逐样本逐象限各跑一次前向）。
- ``fuse_consistency``：每子句取最佳匹配。同位时得分全由属性证据给出：每个属性相符 0.5 /
  冲突 0 / 子句未陈述 0.25（旧实现同位即给 0.5 底分，形状颜色全错的子句也得 0.5，永远到不了
  REJECT 线）；异位但形状颜色全同 0.4。均值 >0.9 ACCEPT / <0.3 REJECT / 其余 DEFER。
  子句缺字段不抛错（旧实现 ``None in str`` TypeError）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from .net import softmax
from .scenes import OBJ, POS
from .text import parse


def quadrant_shares(energy: np.ndarray) -> np.ndarray:
    """(B,R,C,K) 能量 → (B,9) 象限份额（象限按 R//3、C//3 整块切分）。"""
    w = np.abs(energy).sum(axis=-1)
    b, r, c = w.shape
    r3, c3 = r // 3, c // 3
    sh = np.stack([w[:, qy * r3:(qy + 1) * r3, qx * c3:(qx + 1) * c3].sum(axis=(1, 2))
                   for qy in range(3) for qx in range(3)], axis=1)
    return sh / (sh.sum(axis=1, keepdims=True) + 1e-9)


def spatial_detect(model, lat: np.ndarray, exist_mult: float = 1.15) -> List[List[Dict]]:
    """每样本子物体清单 [{pos, obj, conf, share}]（按份额降序）。"""
    energy, _ = model.l1(lat)
    shares = quadrant_shares(energy)
    b, r, c, _ = lat.shape
    r3, c3 = r // 3, c // 3
    keep = []
    for i in range(b):
        qs = {int(shares[i].argmax())} | {q for q in range(9) if shares[i, q] > exist_mult / 9.0}
        keep += [(i, q) for q in sorted(qs)]
    crops = np.stack([lat[i, (q // 3) * r3:(q // 3 + 1) * r3, (q % 3) * c3:(q % 3 + 1) * c3] for i, q in keep])
    logits = model.forward_cache(crops)["logits"]
    probs = softmax(logits)
    out: List[List[Dict]] = [[] for _ in range(b)]
    for (i, q), lg, p in zip(keep, logits, probs):
        out[i].append({"pos": POS[q], "obj": OBJ[int(lg.argmax())], "conf": round(float(p.max()), 3),
                       "share": round(float(shares[i, q]), 3)})
    for lst in out:
        lst.sort(key=lambda d: -d["share"])
    return out


def _attr_support(said: Optional[str], seen: str) -> float:
    return 0.25 if said is None else (0.5 if said == seen else 0.0)


def _clause_score(cl: Dict, det: Dict) -> float:
    shape, color = det["obj"].split("|")
    if cl.get("pos") == det["pos"]:
        return _attr_support(cl.get("shape"), shape) + _attr_support(cl.get("color"), color)
    if cl.get("shape") and cl.get("shape") == shape and cl.get("color") == color:
        return 0.4
    return 0.0


def fuse_consistency(clauses: Sequence[Dict], detections: Sequence[Dict]) -> Dict:
    """文字子句 vs 图像检测 → 一致性四态。"""
    if not clauses and not detections:
        return {"verdict": "BLINDSPOT", "score": 0.0, "note": "双路无证据"}
    scores = [max([_clause_score(cl, d) for d in detections] or [0.0]) for cl in clauses]
    score = float(np.mean(scores)) if scores else 0.0
    if score > 0.9:
        v, note = "ACCEPT", f"图文一致({score:.2f}):全部子句获图像证据支持"
    elif score < 0.3:
        v, note = "REJECT", f"图文冲突({score:.2f}):子句无图像证据支持"
    else:
        v, note = "DEFER", f"部分一致({score:.2f}):证据不足以裁决"
    return {"verdict": v, "score": round(score, 3), "note": note}


def multimodal_check(model, lat: np.ndarray, text: str, n_expected: Optional[int] = None) -> Dict:
    """描述解析（基础词表）→ 空间拆分 → 融合四态 + 拆分对齐率。"""
    clauses = [c.as_dict() for c in parse(text, vocab="basic")]
    dets = spatial_detect(model, lat)[0]
    fused = fuse_consistency(clauses, dets)
    hits = sum(any(_clause_score(cl, d) == 1.0 for d in dets) for cl in clauses)
    fused.update(align=round(hits / len(clauses), 3) if clauses else 0.0, clauses=len(clauses), detections=len(dets))
    return fused
