# -*- coding: utf-8 -*-
"""search · 递归四态搜索（大域并行评估 → REJECT 剪枝 → ACCEPT 收敛 → DEFER 细分 → 兜底盲区）。

语义与旧 hex_search 一致：节点能量份额 < (1/9)·share_mult·0.5 → REJECT（不进语义评估）；
置信 ≥ th_conf 且 margin ≥ th_margin → ACCEPT；置信 ≤ th_reject → REJECT；否则 DEFER 细分 3×3。
``adaptive_depth=True`` 时子域占父域能量 < min_share 即停（信息差死区），停因与份额入证据。
差异（均为旧实现缺陷，与 PR #116 评审结论一致）：
- 根域 ACCEPT 不收敛：根域横跨全部 9 个位置，位置信息差未闭合，按 DEFER 继续细分
  （旧实现直接以根域中心 r4 交付，单物体在任何位置都报 r4）；
- 兄弟域粗筛（``sibling_screen``，缺省开）：子域份额 ≤ 兄弟中位份额 × share_mult 视为背景纹理，
  直接 REJECT（旧实现的绝对份额门槛对 9 个子域按全图归一，几乎从不触发）；
- 单个节点的 L1 能量与 L2/L3 只做一次前向（旧实现 l1 与 l2_features 各算一次 conv1）；
  根域前向与全图能量共用，兄弟粗筛已算的子域前向随子域入栈复用（每个访问节点恰一次前向）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from .net import softmax
from .scenes import OBJ


def _energy_sum(model, sub: np.ndarray) -> Tuple[float, Dict]:
    c = model.forward_cache(sub)
    w = np.abs(c["h1"])[0].sum(axis=-1)
    return float(np.minimum(w, np.quantile(w, 0.999)).sum()), c


def judge_node(logits: np.ndarray, share: Optional[float], share_mult: float = 1.3, th_conf: float = 0.35,
               th_margin: float = 0.12, th_reject: float = 0.10) -> Dict:
    """单节点四态（logits 为该节点 L3 输出）。"""
    if share is not None and share < (1.0 / 9.0) * share_mult * 0.5:
        return {"verdict": "REJECT", "obj": None, "conf": 0.0, "margin": 0.0, "alive": 0, "share": float(share)}
    p = softmax(logits[None])[0]
    order = np.argsort(-logits)
    best = int(order[0])
    margin = float(logits[best] - logits[order[1]])
    conf = float(p[best])
    verdict = "ACCEPT" if conf >= th_conf and margin >= th_margin else ("REJECT" if conf <= th_reject else "DEFER")
    return {"verdict": verdict, "obj": OBJ[best], "conf": round(conf, 3), "margin": round(margin, 3),
            "alive": int((p > 0.15).sum()), "share": float(share) if share is not None else None}


def calibrate_thresholds(model, crops: np.ndarray, q: float = 0.30) -> Dict:
    """ACCEPT 阈值 = 训练 crop 上置信/领先幅度的 q 分位。"""
    logits = model.forward_cache(crops)["logits"]
    srt = np.sort(logits, axis=1)
    return {"th_conf": round(float(np.quantile(softmax(logits).max(axis=1), q)), 4),
            "th_margin": round(float(np.quantile(srt[:, -1] - srt[:, -2], q)), 4)}


def _new_stats(stats: Optional[Dict]) -> Dict:
    st = stats if stats is not None else {"visited": 0, "rejected": 0, "deferred": 0, "max_depth": 0}
    for k in ("stopped_dead_zone", "stopped_max_depth"):
        st.setdefault(k, 0)
    st.setdefault("blindspot_evidence", [])
    return st


def recursive_search(model, lat: np.ndarray, max_depth: int = 2, min_share: float = 0.04,
                     th: Optional[Dict] = None, stats: Optional[Dict] = None,
                     adaptive_depth: bool = False, sibling_screen: bool = True) -> Tuple[List[Dict], Dict]:
    """递归四态搜索。返回 (同位去重后的物体清单, 搜索统计)。"""
    st = _new_stats(stats)
    th = th or {}
    root = _energy_sum(model, lat)
    total = root[0] + 1e-9
    found: List[Dict] = []
    stack = [(lat, 0.0, 1.0, 0.0, 1.0, 0, 1.0, None, root)]
    while stack:
        sub, y0, y1, x0, x1, depth, parent, floor, pre = stack.pop()
        st["visited"] += 1
        st["max_depth"] = max(st["max_depth"], depth)
        e, cache = pre if pre is not None else _energy_sum(model, sub)
        share = e / total
        if floor is not None and share <= floor:
            st["rejected"] += 1
            continue
        if adaptive_depth and depth > 0 and share < min_share * parent:
            st["stopped_dead_zone"] += 1
            st["blindspot_evidence"].append({"pos": f"d{depth}", "depth": depth, "stop": "infogap_dead_zone",
                                             "conf": 0.0, "share_ratio": round(share / max(1e-9, parent), 4)})
            continue
        node = judge_node(cache["logits"][0], share, **th)
        if node["verdict"] == "REJECT":
            st["rejected"] += 1
        elif node["verdict"] == "ACCEPT" and depth > 0:
            cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
            found.append({"obj": node["obj"], "pos": f"r{min(2, int(cy * 3)) * 3 + min(2, int(cx * 3))}",
                          "conf": node["conf"], "depth": depth})
        else:
            st["deferred"] += 1
            if depth >= max_depth:
                st["stopped_max_depth"] += 1
                st["blindspot_evidence"].append({"pos": f"d{depth}", "depth": depth, "stop": "max_depth",
                                                 "conf": node["conf"]})
                continue
            stack += _screened_children(model, sub, (y0, y1, x0, x1), depth, share, total,
                                        th.get("share_mult", 1.3) if sibling_screen else None)[::-1]
    best: Dict[str, Dict] = {}
    for f in found:
        if f["pos"] not in best or f["conf"] > best[f["pos"]]["conf"]:
            best[f["pos"]] = f
    return list(best.values()), st


def _screened_children(model, sub: np.ndarray, box: Tuple, depth: int, share: float, total: float,
                       share_mult: Optional[float]) -> List:
    """子域 + (粗筛下限, 预算前向)。粗筛开时 9 个子域各前向一次并随子域入栈，出栈不再重算。"""
    kids = _children(sub, *box, depth, share)
    if share_mult is None or not kids:
        return [k + (None, None) for k in kids]
    pre = [_energy_sum(model, k[0]) for k in kids]
    floor = float(np.median([p[0] / total for p in pre])) * share_mult
    return [k + (floor, p) for k, p in zip(kids, pre)]


def _children(sub: np.ndarray, y0: float, y1: float, x0: float, x1: float, depth: int, share: float) -> List:
    rr, cc = sub.shape[1:3]
    out = []
    for i in range(3):
        for j in range(3):
            s = sub[:, i * rr // 3:(i + 1) * rr // 3, j * cc // 3:(j + 1) * cc // 3]
            if s.shape[1] == 0 or s.shape[2] == 0:
                continue
            dy, dx = (y1 - y0) / 3, (x1 - x0) / 3
            out.append((s, y0 + i * dy, y0 + (i + 1) * dy, x0 + j * dx, x0 + (j + 1) * dx, depth + 1, share))
    return out


def search_report(model, lat: np.ndarray, metas: List[Dict], max_depth: int = 2) -> Dict:
    """批量：位置检出率 / 物体匹配率 / 平均访问节点 / 剪枝率。"""
    pos_hit = obj_hit = nodes = rej = 0
    n_lab = max(1, sum(len(m["labels"]) for m in metas))
    for i in range(len(lat)):
        found, st = recursive_search(model, lat[i:i + 1], max_depth=max_depth)
        pos_hit += len({lb["pos"] for lb in metas[i]["labels"]} & {f["pos"] for f in found})
        obj_hit += len({(lb["pos"], lb["obj"]) for lb in metas[i]["labels"]} & {(f["pos"], f["obj"]) for f in found})
        nodes += st["visited"]
        rej += st["rejected"]
    return {"pos_hit_rate": round(pos_hit / n_lab, 3), "obj_match_rate": round(obj_hit / n_lab, 3),
            "avg_visited": round(nodes / max(1, len(lat)), 1), "prune_rate": round(rej / max(1, nodes), 3)}
