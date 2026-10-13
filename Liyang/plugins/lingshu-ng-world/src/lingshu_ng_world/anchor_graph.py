# -*- coding: utf-8 -*-
"""anchor_graph · 3D 语义锚点图（旧 ``lingshu.world.semantic_anchor_graph`` 的 ng 实现，同名 API）。

节点 = 语义锚点（类别 + 世界坐标中心 + 尺寸 + 置信 + 来源），边 = 关系三元组（事物是其
关系的总和）。``infer_relations`` 从几何推「支撑」「相邻」；``verify`` / ``verify_conflict``
委托 :class:`anchor_verify.AnchorVerification`。

与旧版相比修正的缺陷类别：

- **支撑判据写反**：旧版「水平近 且 高度差 < 0.2」判支撑——那是并排放在同一高度（相邻），
  真正叠放的物体（高度差 ≈ 两者半高之和）反而只判相邻或无边。这里支撑 ⇔ 水平足迹重叠 且
  下者顶面与上者底面接触（|间隙| ≤ contact_tol）；其余近距对判相邻。
- **关系类型表是模块全局可变量**：旧 ``relate`` 遇到新关系名就写进模块级 RELATION_TYPES，
  一张图的自定义关系泄漏到所有图；这里每张图持有自己的注册表副本（模块级默认表只读使用，
  显式 :func:`register_relation_type` 仍可全局注册）。
- 锚点中心 / 尺寸 / 置信度与关系权重拒收 NaN/inf。
"""
from __future__ import annotations

import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from .anchor_verify import AnchorVerification
from .validate import finite_scalar, finite_vec3

__all__ = ["RELATION_TYPES", "register_relation_type", "SemanticAnchor", "RelationEdge",
           "SemanticAnchorGraph", "supports", "CONTACT_TOL"]

Vec3 = Tuple[float, float, float]
CONTACT_TOL = 0.1

RELATION_TYPES: Dict[str, Dict] = {
    "位于": {"dim": "spatial", "desc": "A 位于 B 之内/之上（如杯子在桌上）"},
    "相邻": {"dim": "spatial", "desc": "A 与 B 空间相邻（如椅子邻桌）"},
    "支撑": {"dim": "spatial", "desc": "A 支撑 B（如桌子支撑杯子）"},
    "朝向": {"dim": "spatial", "desc": "A 面向 B（如椅子朝向桌子）"},
    "包含": {"dim": "spatial", "desc": "A 包含 B（如房间包含桌子）"},
    "属于": {"dim": "semantic", "desc": "A 属于类别/集合 B"},
    "类似": {"dim": "semantic", "desc": "A 与 B 语义类似"},
    "部分是": {"dim": "semantic", "desc": "A 是 B 的组成部分"},
    "先于": {"dim": "temporal", "desc": "A 在时间上先于 B"},
    "伴随": {"dim": "temporal", "desc": "A 与 B 同时出现/运动"},
}


def register_relation_type(name: str, dim: str = "custom", desc: str = "") -> None:
    """全局注册关系类型（之后新建的图都可见）。"""
    RELATION_TYPES[name] = {"dim": dim, "desc": desc}


def _vec(v: object, name: str) -> Vec3:
    a = finite_vec3(v, name)
    return (float(a[0]), float(a[1]), float(a[2]))


@dataclass
class SemanticAnchor:
    """3D 语义锚点：类别 + 世界坐标中心 + 尺寸 (w,h,d) + 置信 + 来源。"""
    category: str
    center: Vec3 = (0.0, 0.0, 0.0)
    size: Vec3 = (1.0, 1.0, 1.0)
    confidence: float = 0.5
    provenance: str = "world3d"
    ts: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: "anchor_" + uuid.uuid4().hex[:10])
    attrs: Dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.center = _vec(self.center, "center")
        self.size = _vec(self.size, "size")
        self.confidence = finite_scalar(self.confidence, "confidence")

    def to_dict(self) -> Dict:
        return asdict(self)

    def __repr__(self) -> str:
        c = tuple(round(v, 2) for v in self.center)
        return f"<Anchor {self.category}@{c} conf={self.confidence:.2f}>"


@dataclass
class RelationEdge:
    """关系边：source -relation-> target。"""
    source: str
    target: str
    relation: str = "相邻"
    weight: float = 0.5
    attrs: Dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return asdict(self)


def supports(lower: SemanticAnchor, upper: SemanticAnchor, tol: float = CONTACT_TOL) -> bool:
    """lower 支撑 upper ⇔ 水平足迹重叠（x、z 两轴）且 lower 顶面与 upper 底面接触。"""
    (lx, ly, lz), (lw, lh, ld) = lower.center, lower.size
    (ux, uy, uz), (uw, uh, ud) = upper.center, upper.size
    overlap = abs(lx - ux) < (lw + uw) / 2 and abs(lz - uz) < (ld + ud) / 2
    gap = (uy - uh / 2) - (ly + lh / 2)
    return overlap and uy > ly and abs(gap) <= tol


class SemanticAnchorGraph:
    """3D 语义锚点图：节点（锚点）+ 边（关系）。"""

    def __init__(self):
        self.anchors: Dict[str, SemanticAnchor] = {}
        self.edges: List[RelationEdge] = []
        self.relation_types: Dict[str, Dict] = {k: dict(v) for k, v in RELATION_TYPES.items()}
        self._verifier: Optional[AnchorVerification] = None

    # ---- 节点 ----

    def add_anchor(self, anchor: SemanticAnchor) -> str:
        self.anchors[anchor.id] = anchor
        return anchor.id

    def add(self, category: str, center: Vec3, size: Vec3 = (1.0, 1.0, 1.0),
            confidence: float = 0.5, provenance: str = "world3d",
            attrs: Optional[Dict] = None) -> str:
        return self.add_anchor(SemanticAnchor(category, center, size, confidence, provenance,
                                              attrs=attrs or {}))

    def get(self, anchor_id: str) -> Optional[SemanticAnchor]:
        return self.anchors.get(anchor_id)

    # ---- 边 ----

    def relate(self, source: str, target: str, relation: str = "相邻", weight: float = 0.5,
               attrs: Optional[Dict] = None) -> Optional[RelationEdge]:
        """建边；端点缺失 → None；新关系名只注册进本图的类型表。"""
        if source not in self.anchors or target not in self.anchors:
            return None
        if relation not in self.relation_types:
            self.relation_types[relation] = {"dim": "custom", "desc": "自定义关系"}
        e = RelationEdge(source, target, relation, finite_scalar(weight, "weight"), attrs or {})
        self.edges.append(e)
        return e

    # ---- 查询 ----

    def relations_of(self, anchor_id: str) -> List[Dict]:
        out = []
        for e in self.edges:
            if anchor_id in (e.source, e.target):
                out_dir = e.source == anchor_id
                out.append({"direction": "out" if out_dir else "in",
                            "other": e.target if out_dir else e.source,
                            "relation": e.relation, "weight": e.weight, "attrs": e.attrs})
        return out

    def neighbors(self, anchor_id: str, relation: Optional[str] = None) -> List[Dict]:
        return [{"id": r["other"], "relation": r["relation"], "weight": r["weight"]}
                for r in self.relations_of(anchor_id) if not relation or r["relation"] == relation]

    def query(self, category: Optional[str] = None, region: Optional[Tuple] = None) -> List[SemanticAnchor]:
        """按类别 / 区域 (xmin,ymin,zmin,xmax,ymax,zmax) 查询。"""
        out = []
        for a in self.anchors.values():
            if category and a.category != category:
                continue
            if region and not all(region[i] <= a.center[i] <= region[i + 3] for i in range(3)):
                continue
            out.append(a)
        return out

    # ---- 关系推理 ----

    def infer_relations(self, distance_threshold: float = 1.5,
                        contact_tol: float = CONTACT_TOL) -> int:
        """几何推理：叠放接触 → 支撑（下→上）；其余中心距 < 阈值 → 相邻。已有边的对跳过。"""
        linked = {frozenset((e.source, e.target)) for e in self.edges}
        ids, added = list(self.anchors), 0
        for i, ai in enumerate(ids):
            for bi in ids[i + 1:]:
                if frozenset((ai, bi)) in linked:
                    continue
                a, b = self.anchors[ai], self.anchors[bi]
                lower, upper = (a, b) if a.center[1] <= b.center[1] else (b, a)
                if supports(lower, upper, contact_tol):
                    gap = (upper.center[1] - upper.size[1] / 2) - (lower.center[1] + lower.size[1] / 2)
                    self.relate(lower.id, upper.id, "支撑", 0.7, attrs={"v_gap": round(gap, 2)})
                elif math.dist(a.center, b.center) < distance_threshold:
                    self.relate(a.id, b.id, "相邻", 0.5,
                                attrs={"distance": round(math.dist(a.center, b.center), 2)})
                else:
                    continue
                added += 1
        return added

    # ---- 描述 / 导出 ----

    def _cat(self, aid: str) -> str:
        a = self.anchors.get(aid)
        return a.category if a is not None else "?"

    def scene_text(self) -> str:
        parts = ["%s@(%s,%s,%s)" % ((a.category,) + tuple(round(v, 1) for v in a.center))
                 for a in self.anchors.values()]
        rels = [f"{self._cat(e.source)}{e.relation}{self._cat(e.target)}" for e in self.edges]
        return f"锚点: {'；'.join(parts) or '（空）'} | 关系: {'；'.join(rels) or '（无关系）'}"

    def to_dict(self) -> Dict:
        return {"anchors": [a.to_dict() for a in self.anchors.values()],
                "edges": [e.to_dict() for e in self.edges],
                "relation_types": list(self.relation_types)}

    # ---- 多感知机验证 ----

    def _verifier_(self) -> AnchorVerification:
        if self._verifier is None:
            self._verifier = AnchorVerification(graph=self)
        return self._verifier

    def verify(self, anchor_id: str, channel: str, evidence: float,
               strong: Optional[bool] = None) -> Dict:
        v = self._verifier_()
        v.add_channel_evidence(anchor_id, channel, evidence, strong)
        return v.verify_anchor(anchor_id)

    def verify_conflict(self, anchor_id: str, channel: str, expected: str, actual: str) -> Dict:
        return self._verifier_().channel_conflict_detect(anchor_id, channel, expected, actual)
