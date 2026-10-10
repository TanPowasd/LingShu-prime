# -*- coding: utf-8 -*-
"""neural · 可选的读路径第三阶段：混合候选池 + 交叉编码重排 + 写入流多样化（纯标准库；模型件注入）

背景：作者基准 hive-memory-bench（HMB）零 LLM 检索轨上，纯词面 c2 只与朴素 BM25 持平（cid 0.680 对 0.668），
语义第二路（LDD 交错）把 cid 拉到 0.73。交错只看名次，丢掉了两路分数里的置信度；而问句是「这条线索由哪些
情节节点串起来」这类叙事题，需要能读懂（查询, 原文）对的打分器。本模块在不动写入路径的前提下补上读路径的三件事：

  N1 混合候选池：词面相关度前 P 名 ∪ 语义前 S 名（去重，过 exclude / 退役 / 可检索层，与 Q4 同规则）。
  N2 融合打分：池内三路分数各自按池内 z 分数标准化后加权
        fused = A·z(交叉编码 logit) + (1−A)·[½·z(语义余弦) + ½·z(池内 BM25)]
     缺哪一路就去掉哪一路并把权重归给其余路（无交叉编码 ⇒ 语义与词面各半；只有词面 ⇒ 等价于 c2 的 idf 重排）。
     z 分数而非名次：保留每路的置信度差距；三路量纲不同，z 分数是池内唯一无参的公共尺度。
  N3 写入流多样化：长文本块（≥ LONG_GRAMS 个正文二元组）在贪心选取时，与已选长块写入序相差 ≤ SPAN 的，
     选取值乘 (1−PEN)（可叠加）。同一段落流里相邻写入的块往往在讲同一件事；多样化把覆盖面拉到别的情节
     （叙事题平均需要 3.7 个不同章节）。短节点（原子事实）不参与，理由同 :mod:`lingshu_ng.rerank` R2。

所有模型件都是 duck-typed 注入（核心零外部 import，test_quality 零依赖门禁）：
  * cross：``score(query, texts) -> List[float]``（如 :class:`lingshu_ng.embed.cross.OnnxCrossEncoder`）
  * 语义：:class:`lingshu_ng.semindex.SemanticIndex`（``similarity(query, ids)``；可选）
确定性：同分按写入序、再按 id；模型件逐对/逐条推理（与批组成无关）。
参数取值见 ``evalsuite_hmb_x/ITER_NEURAL.md``（只在 HMB 开发半集上选，留出半集与干预轮题只读）。
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = ["NeuralStage", "zscores", "fuse", "stream_diversify", "POOL_LEX", "POOL_SEM", "A_CROSS", "SPAN", "PEN", "WS", "blend_sentence"]

#: 词面候选数
POOL_LEX = 30
#: 语义候选数
POOL_SEM = 20
#: 交叉编码权重
A_CROSS = 0.6
#: 写入流多样化：写入序相差 ≤ SPAN 视为同一段落流的近邻
SPAN = 2
#: 每有一个已选近邻，选取值乘 (1 − PEN)
PEN = 0.3
#: 句级证据分在语义路里的占比（语义 = (1−WS)·z(整块余弦) + WS·z(最贴题一句余弦)）；只在有交叉编码时用：
#: 离线 HMB 92 题 dev/test 两半同向小幅提升；生产实测为取舍（干扰↓、要点↑，cid/原句略降），故提供者默认不建句级索引
WS = 0.7
#: 参与多样化的长文本块下限（正文二元组个数；与 rerank.LONG_GRAMS 同口径）
LONG_GRAMS = 100


def zscores(vals: Dict[str, float]) -> Dict[str, float]:
    """池内 z 分数；方差为 0 时全 0。"""
    if not vals:
        return {}
    xs = list(vals.values())
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
    if sd <= 1e-12:
        return dict.fromkeys(vals, 0.0)
    return {k: (v - m) / sd for k, v in vals.items()}


def fuse(ids: Sequence[str], lex: Dict[str, float], sem: Optional[Dict[str, float]],
         cross: Optional[Dict[str, float]], a_cross: float = A_CROSS) -> Dict[str, float]:
    """N2：三路 z 分数加权（缺路自动归权）。缺值的候选在该路取池内最小值。"""
    parts: List[Tuple[float, Dict[str, float]]] = []
    base = [d for d in (sem, lex) if d is not None]
    w_base = (1.0 - a_cross) if cross is not None else 1.0
    if cross is not None:
        parts.append((a_cross, cross))
    for d in base:
        parts.append((w_base / len(base), d))
    out = dict.fromkeys(ids, 0.0)
    for w, d in parts:
        lo = min((d[i] for i in ids if i in d), default=0.0)
        z = zscores({i: d.get(i, lo) for i in ids})
        for i in ids:
            out[i] += w * z[i]
    return out


def blend_sentence(chunk: Dict[str, float], sent: Dict[str, float], ws: float = WS) -> Dict[str, float]:
    """语义路 = (1−ws)·z(整块) + ws·z(句级)；句级缺值取池内最小。sent 为空 ⇒ 原样返回 chunk。"""
    if not sent or ws <= 0 or not chunk:
        return chunk
    ids = list(chunk)
    lo = min((sent[i] for i in ids if i in sent), default=0.0)
    zc = zscores(chunk)
    zs = zscores({i: sent.get(i, lo) for i in ids})
    return {i: (1.0 - ws) * zc[i] + ws * zs[i] for i in ids}


def stream_diversify(order: Sequence[str], score: Dict[str, float], seq: Dict[str, Optional[int]],
                     long_ids: set, limit: int, span: int = SPAN, pen: float = PEN) -> List[str]:
    """N3：按 score 贪心选 limit 个；长块与已选长块写入序相差 ≤ span 的，选取值（平移到非负）乘 (1−pen)^n。
    其余候选按原序接在后面。"""
    if not order:
        return []
    lo = min(score[i] for i in order)
    val = {i: score[i] - lo + 1e-9 for i in order}
    cnt = dict.fromkeys(order, 0)
    rank = {i: k for k, i in enumerate(order)}
    left = list(order)
    out: List[str] = []
    while left and len(out) < limit:
        best = max(left, key=lambda i: (val[i] * (1.0 - pen) ** cnt[i], -rank[i]))
        left.remove(best)
        out.append(best)
        if best in long_ids and seq.get(best) is not None:
            k = seq[best]
            for o in left:
                if o in long_ids and seq.get(o) is not None and abs(seq[o] - k) <= span:
                    cnt[o] += 1
    return out + left


class NeuralStage:
    """把 N1–N3 绑到一个交叉编码提供者上（可为 None：只做混合池 + 融合 + 多样化）。"""

    def __init__(self, cross=None, pool_lex: int = POOL_LEX, pool_sem: int = POOL_SEM,
                 a_cross: float = A_CROSS, span: int = SPAN, pen: float = PEN, ws: float = WS,
                 cross_top: int = 0) -> None:
        self.cross = cross
        self.pool_lex, self.pool_sem = int(pool_lex), int(pool_sem)
        self.a_cross, self.span, self.pen, self.ws = float(a_cross), int(span), float(pen), float(ws)
        #: >0 时只对「词面＋语义预融合」前 cross_top 名做交叉编码（其余在交叉编码路取池内最小）：延迟约按比例降，
        #: HMB 离线 20 名：cid −0.010、原句 +0.013、干扰 +0.10（见 REPORT_neural.md「中档」）；0 = 全池
        self.cross_top = int(cross_top)
        self.error: Optional[str] = None
        self.last: Dict = {}

    def cross_scores(self, q: str, texts: Dict[str, str]) -> Optional[Dict[str, float]]:
        """交叉编码分；提供者缺失或出错 ⇒ None（退回无交叉编码的融合，并记 error）。"""
        if self.cross is None or self.error is not None or not texts:
            return None
        ids = sorted(texts)
        try:
            vals = list(self.cross.score(q, [texts[i] for i in ids]))
        except Exception as e:  # 外部注入件：失败不影响召回
            self.error = f"{type(e).__name__}: {e}"
            return None
        return {i: float(v) for i, v in zip(ids, vals)}
