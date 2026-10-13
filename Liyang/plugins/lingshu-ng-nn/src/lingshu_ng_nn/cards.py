# -*- coding: utf-8 -*-
"""cards · 条件卡（零阶校准）与四态判定、层级报告。

- 类别卡：p_threshold / margin_threshold 取类内 25% 分位；四态 ACCEPT / DEFER / BLINDSPOT
  （类别归属域不用 REJECT）。
- 层级卡：形状/颜色原型 + 余弦分位、物体卡概率分位；``hier_report`` 给出各层正确率。
所有函数只依赖模型的 ``forward_cache`` / ``l1`` / ``l4_position``，不读写参数。
"""
from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

from .net import softmax
from .scenes import COLORS, OBJ, POS, SHAPES


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """余弦相似度（零向量 → 0）。"""
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return 0.0 if na < 1e-12 or nb < 1e-12 else float(a @ b / (na * nb))


def calibrate_class_cards(logits: np.ndarray, y: np.ndarray, n_class: int) -> List[Dict]:
    """每类一张卡：类内 softmax 概率与 top1−top2 logit 差的 25% 分位（无样本的类给 1.0/inf 不可达阈值）。"""
    probs = softmax(logits)
    cards = []
    for c in range(n_class):
        sel = y == c
        if not sel.any():
            cards.append({"class": c, "p_threshold": 1.0, "margin_threshold": float("inf"),
                          "missing": True})                       # #254：缺类保守卡并标注
            continue
        top2 = np.sort(logits[sel], axis=1)[:, -2:]
        cards.append({"class": c, "p_threshold": round(float(np.quantile(probs[sel, c], 0.25)), 4),
                      "margin_threshold": round(float(np.quantile(top2[:, 1] - top2[:, 0], 0.25)), 4)})
    return cards


def four_state_classify(logits: np.ndarray, cards: Sequence[Dict]) -> List[Dict]:
    """四态判定：BLINDSPOT（p≈1/C）/ ACCEPT（p≥阈值且 margin≥阈值）/ DEFER（其余）。"""
    n_class = logits.shape[1]
    probs = softmax(logits)
    order = np.argsort(-logits, axis=1)
    margin = {c["class"]: float(c["margin_threshold"]) for c in cards}
    pthr = {c["class"]: float(c["p_threshold"]) for c in cards}
    out = []
    for i in range(len(logits)):
        best = int(order[i, 0])
        p = float(probs[i, best])
        m = float(logits[i, best] - logits[i, order[i, 1]]) if n_class > 1 else 9.9
        if not np.isfinite(p) or p <= 1.05 / n_class:
            v, note = "BLINDSPOT", f"p={p:.3f}≈1/{n_class},无证据带,无法归属"
        elif p >= pthr[best] and m >= margin[best]:
            v, note = "ACCEPT", f"p={p:.3f}≥{pthr[best]:.3f},logit差 {m:.2f}≥{margin[best]:.2f}"
        elif p >= pthr[best]:
            v, note = "DEFER", f"概率够但区分不足(logit差 {m:.2f}<{margin[best]:.2f})"
        else:
            v, note = "DEFER", f"p={p:.3f}<类阈值 {pthr[best]:.3f},证据弱"
        out.append({"verdict": v, "class": best, "ratio": round(p, 3), "note": note})
    return out


def four_state_report(verdicts: Sequence[Dict], y: np.ndarray) -> Dict:
    """ACCEPT 精确率 + 覆盖率 + 各态计数。"""
    acc = [v for v, t in zip(verdicts, y) if v["verdict"] == "ACCEPT"]
    hits = sum(int(v["class"] == t) for v, t in zip(verdicts, y) if v["verdict"] == "ACCEPT")
    n = max(1, len(verdicts))
    return {"accept_precision": round(hits / max(1, len(acc)), 4), "accept_coverage": round(len(acc) / n, 4),
            "defer": sum(v["verdict"] == "DEFER" for v in verdicts),
            "blindspot": sum(v["verdict"] == "BLINDSPOT" for v in verdicts), "n": len(verdicts)}


def calibrate_hier_cards(feat: np.ndarray, color: np.ndarray, logits: np.ndarray, labels: Dict) -> Dict:
    """层级卡：形状/颜色原型与类内余弦 25% 分位、物体卡概率 25% 分位。"""
    probs = softmax(logits)
    cards: Dict[str, list] = {"shape": [], "color": [], "obj": []}
    for s in SHAPES:
        sel = labels["shape"] == s
        if not sel.any():      # #254：缺类不给零原型 + 0 阈值（那会让任意特征都算 inlier）
            cards["shape"].append({"semantic": s, "proto": None, "inlier_q25": None, "missing": True})
            continue
        proto = feat[sel].mean(axis=0) if sel.any() else np.zeros(feat.shape[1])
        sims = np.array([cosine(proto, f) for f in feat[sel]]) if sel.any() else np.zeros(1)
        cards["shape"].append({"semantic": s, "proto": proto.tolist(),
                               "inlier_q25": round(float(np.quantile(sims, 0.25)), 4)})
    for c in COLORS:
        sel = labels["color"] == c
        if not sel.any():
            cards["color"].append({"semantic": c, "proto": None, "inlier_q25": None, "missing": True})
            continue
        proto = color[sel].mean(axis=0) if sel.any() else np.zeros(color.shape[1])
        sims = np.array([cosine(proto, p) for p in color[sel]]) if sel.any() else np.zeros(1)
        cards["color"].append({"semantic": c, "proto": proto.tolist(),
                               "inlier_q25": round(float(np.quantile(sims, 0.25)), 4)})
    for i, o in enumerate(OBJ):
        sel = labels["obj"] == o
        if not sel.any():      # #254：缺类不给 0.0（任意概率都过阈）
            cards["obj"].append({"obj": o, "p_q25": None, "missing": True})
            continue
        cards["obj"].append({"obj": o, "p_q25": round(float(np.quantile(probs[sel, i], 0.25)), 4)})
    return cards


def hier_report(model, lat: np.ndarray, labels: Dict) -> Dict:
    """各层正确率（形状/颜色/物体/位置）+ 物体 margin/置信均值。"""
    c = model.forward_cache(lat)
    logits = c["logits"]
    pred = np.array([OBJ[i] for i in logits.argmax(axis=1)])
    acc_shape = float((np.array([o.split("|")[0] for o in pred]) == labels["shape"]).mean())
    acc_color = float((np.array([o.split("|")[1] for o in pred]) == labels["color"]).mean())
    energy, _ = model.l1(lat)
    pos = np.array([POS[i] for i in model.l4_position(energy).argmax(axis=1)])
    srt = np.sort(logits, axis=1)
    return {"acc_shape": round(acc_shape, 4), "acc_color": round(acc_color, 4),
            "acc_obj": round(float((pred == labels["obj"]).mean()), 4),
            "acc_pos": round(float((pos == labels["pos"]).mean()), 4),
            "obj_margin_mean": round(float((srt[:, -1] - srt[:, -2]).mean()), 3),
            "obj_conf_mean": round(float(softmax(logits).max(axis=1).mean()), 4)}
