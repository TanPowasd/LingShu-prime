# -*- coding: utf-8 -*-
"""align_probe · 跨源对齐探针的无语料部分（迁自 ``lingshu.gen.hexgen_align_probe``）。

迁移范围：跨源命名映射（比较口径：自家 ``stripe`` ＝ 真实词表 ``square``）、逐维加权 L1 距离贡献、
原型排名与“对方自家件到原型的距离分布”统计、映射前后的跨源命中/混淆计数。
不迁：黑箱读者标定（``blackbox_reader``）与自家件抠图量测——依赖黑箱语料与 ``hexgen_c1_real``；
这里的函数接收任意读者给出的特征向量/原型/权重/尺度与 (真值, 预测) 对。
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .multi_seed import FEATS

NAME_MAP_SELF2REAL = {"circle": "circle", "triangle": "triangle", "stripe": "square"}


def distance_contrib(q, p, w, sc, dims: Sequence[str] = FEATS) -> Tuple[float, List[Tuple[str, float]]]:
    """加权 L1 ``Σ |q−p|/sc·w`` 与逐维贡献（降序，4 位）。"""
    per = np.abs(np.asarray(q, float) - np.asarray(p, float)) / np.asarray(sc, float) * np.asarray(w, float)
    pairs = sorted(zip(dims, per.tolist()), key=lambda x: -x[1])
    return float(per.sum()), [(k, round(float(v), 4)) for k, v in pairs]


def rank_protos(q, protos: Dict[str, Sequence[float]], w, sc, dims: Sequence[str] = FEATS,
                top: int = 5) -> Dict:
    """到各原型的距离（含 Top-k 贡献维）与按距离升序的前 3 名。"""
    dist = {}
    for cls, p in protos.items():
        tot, contrib = distance_contrib(q, p, w, sc, dims)
        dist[cls] = {"total": round(tot, 4), "top5": contrib[:top]}
    return {"dist": dist, "ranked": sorted(dist, key=lambda k: dist[k]["total"])[:3]}


def own_distribution(feats: Iterable, proto, w, sc) -> Optional[Dict]:
    """一组件（如黑箱自己的真三角）到某原型的距离分布 {n,min,median,max,all}；空为 None。"""
    ds = sorted(distance_contrib(q, proto, w, sc)[0] for q in feats)
    if not ds:
        return None
    return {"n": len(ds), "min": round(ds[0], 4), "median": round(float(np.median(ds)), 4),
            "max": round(ds[-1], 4), "all": [round(x, 4) for x in ds]}


def cross_source_hits(pairs: Iterable[Tuple[str, str]], with_name_map: bool = True) -> Dict:
    """跨源命中：``pairs`` 为 (自家真值形状, 读者预测)；``with_name_map`` 时真值先按比较口径映射。"""
    conf: Dict[str, int] = {}
    hit = tot = 0
    for shape, pred in pairs:
        truth = NAME_MAP_SELF2REAL.get(shape, shape) if with_name_map else shape
        key = f"{shape}→{pred}"
        conf[key] = conf.get(key, 0) + 1
        hit += int(pred == truth)
        tot += 1
    return {"hit": hit, "n": tot, "rate": round(hit / max(1, tot), 4), "with_name_map": with_name_map,
            "confusion": dict(sorted(conf.items()))}
