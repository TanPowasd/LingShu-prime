# -*- coding: utf-8 -*-
"""insight · 洞察条件层（洞见事件记录 / 验证 / CER 报告）

旧实现的缺陷类别：验证状态在 tags 与 state_attributes 两处各写一份且重验证时标签叠加、
REFUTED 残留(core-py-10)；报告对分类条件做真值判断（pressure 恒真，#core-py-07）、
pending 混入 refuted；V2 零证据自报即 verified 且 importance 直升 0.9(#38)。

不变量：
  I1 验证状态的**唯一事实源**是 ``state_attributes.insight.verification``；tags 只是它的
     投影，每次验证由 :func:`_status_tags` 整体重算（恰好一个状态标签 + 一个级别标签）。
  I2 V2/V3 需 ≥1 条证据、V1 需 ≥3 条，否则保持 pending；REFUTED/X ⇒ refuted。
  I3 报告：total = verified + refuted + pending；分类条件按「正向取值」分组。
"""
from __future__ import annotations

import math
import uuid
from typing import Callable, Dict, List, Optional

from .store import Store
from .types import ConditionSpace, MemoryLayer, Node, now

__all__ = ["Insights", "DEFAULT_CONDITIONS"]

DEFAULT_CONDITIONS = {
    "memory_retrievability": 0.5, "outside_observer": "none", "cross_domain": [],
    "premise_questioned": False, "pressure": "medium", "continuity_turns": 1,
    "externalized": False, "tone": "calm",
}
LEVELS = ("V1", "V2", "V3", "REFUTED", "X")
_STATUS = ("pending", "verified", "refuted")
#: 分类条件的正向取值谓词（其余条件按真值）
POSITIVE: Dict[str, Callable[[object], bool]] = {
    "pressure": lambda v: v == "low",
    "tone": lambda v: v in ("calm", "curious"),
}


def _status(level: str, n_evidence: int) -> str:
    if level in ("REFUTED", "X"):
        return "refuted"
    if level in ("V2", "V3"):
        return "verified" if n_evidence >= 1 else "pending"
    if level == "V1":
        return "verified" if n_evidence >= 3 else "pending"
    return "pending"


def _status_tags(tags: List[str], status: str, level: Optional[str]) -> List[str]:
    stale = set(_STATUS) | set(LEVELS) | {"insight_event"}
    kept = [t for t in tags if t not in stale]
    return kept + ["insight_event", status] + ([level] if level else [])


class Insights:
    """洞见事件仓（节点在知识层，带 insight_event 标签）。"""

    def __init__(self, store: Store) -> None:
        self.store = store

    def record(self, content: str, conditions: Optional[Dict] = None, source: str = "",
               importance: float = 0.7) -> Dict:
        """记录洞见事件（pending）。显式提供的条件置信 0.7，默认值 0.3。"""
        vals = dict(DEFAULT_CONDITIONS)
        given = {k for k in (conditions or {}) if k in vals}
        vals.update({k: conditions[k] for k in given})
        pack = {"values": vals, "confidence": {k: (0.7 if k in given else 0.3) for k in vals}}
        t = now()
        nid = f"insight_{uuid.uuid4().hex[:12]}"
        sa = {"insight": {"conditions": pack, "source": source, "importance_at_record": importance,
                          "verification": {"level": None, "evidence": [], "status": "pending",
                                           "updated_at": t}}}
        self.store.nodes.put(Node(
            id=nid, content=f"【洞见事件】{content}", modality="text", spatial_coordinates={},
            temporal_coordinate=t, condition_space=ConditionSpace("协议实例·认知循环", "洞察条件层记录",
                                                                  (t, t + 3600), "协议实例运行中"),
            importance=importance, confidence=0.5, layer=MemoryLayer.KNOWLEDGE,
            tags=["insight-layer", "insight_event", "pending"], state_attributes=sa,
            last_access=t, created_at=t))
        return {"node_id": nid, "status": "pending", "conditions": vals, "importance": importance}

    def verify(self, insight_id: str, level: str = "V2", evidence: object = None) -> Dict:
        """提交验证（I1/I2）。"""
        n = self.store.nodes.get(insight_id)
        if n is None or "insight_event" not in n.tags:
            return {"error": f"非洞见事件节点: {insight_id}"}
        lv = (level or "").upper()
        if lv not in LEVELS:
            return {"error": f"未知验证级别: {level!r}"}
        sa = dict(n.state_attributes or {})
        ins = dict(sa.get("insight") or {})
        ev = list((ins.get("verification") or {}).get("evidence", []))
        add = evidence if isinstance(evidence, list) else ([evidence] if evidence else [])
        ev += [e for e in add if e not in ev]
        status = _status(lv, len(ev))
        ins["verification"] = {"level": lv, "evidence": ev, "status": status, "updated_at": now()}
        sa["insight"] = ins
        if status == "verified":
            imp = max(n.importance or 0.0, 0.9)
        else:                                   # 上游 #281：证伪/待定回落到记录时的初值（不保留验证期抬升）
            base = ins.get("importance_at_record")
            imp = n.importance if base is None else min(n.importance or 0.0, float(base))
        self.store.nodes.update(insight_id, state_attributes=sa, importance=imp,
                                tags=_status_tags(n.tags, status, lv))
        return {"node_id": insight_id, "level": lv, "status": status,
                "evidence_count": len(ev), "importance": imp}

    def _candidates(self) -> List[Dict]:
        out = []
        for n in self.store.nodes.by_tag("insight_event", limit=None):
            ins = (n.state_attributes or {}).get("insight") or {}
            st = (ins.get("verification") or {}).get("status")
            if st not in _STATUS:
                st = next((s for s in ("refuted", "verified") if s in n.tags), "pending")
            out.append({"id": n.id, "status": st,
                        "conditions": (ins.get("conditions") or {}).get("values", {})})
        out.sort(key=lambda x: x["id"])
        return out

    def report(self, window: Optional[int] = None) -> Dict:
        """CER 报告（I3）；样本 < 20 不判定显著性。"""
        cands = self._candidates()
        if window:
            cands = cands[-int(window):]
        n = len(cands)
        nv = sum(1 for x in cands if x["status"] == "verified")
        nr = sum(1 for x in cands if x["status"] == "refuted")
        cer = nv / n if n else 0.0
        se = math.sqrt(cer * (1 - cer) / n) if n else 0.0
        stats = [s for s in (self._compare(k, cands) for k in
                             ("premise_questioned", "externalized", "pressure", "tone", "cross_domain"))
                 if s]
        return {"total": n, "verified": nv, "refuted": nr, "pending": n - nv - nr,
                "cer": round(cer, 3), "se": round(se, 4),
                "layer_status": "degraded" if n < 20 else ("watch" if n < 40 else "reliable"),
                "note": "样本<20 不判定（与迁移测试同标准）" if n < 20 else "样本达标，可出显著性",
                "conditions": stats, "sample_ids": [x["id"] for x in cands]}

    @staticmethod
    def _compare(key: str, cands: List[Dict]) -> Optional[Dict]:
        pred = POSITIVE.get(key, bool)
        w = [x for x in cands if pred(x["conditions"].get(key))]
        wo = [x for x in cands if not pred(x["conditions"].get(key))]
        if len(w) < 5 or len(wo) < 5:
            return None
        p1 = sum(1 for x in w if x["status"] == "verified") / len(w)
        p0 = sum(1 for x in wo if x["status"] == "verified") / len(wo)
        se1 = math.sqrt(max(p1 * (1 - p1) / len(w), 1e-4))
        se0 = math.sqrt(max(p0 * (1 - p0) / len(wo), 1e-4))
        diff = p1 - p0
        sig = abs(diff) >= 2 * math.sqrt(se1 ** 2 + se0 ** 2)
        return {"condition": key, "n_with": len(w), "n_without": len(wo),
                "cer_with": round(p1, 3), "cer_without": round(p0, 3), "diff": round(diff, 3),
                "significant": sig, "judge": "确认" if (sig and diff > 0) else ("反证" if sig else "不判定")}

    @staticmethod
    def window(conditions: Optional[Dict] = None) -> Dict:
        """当前洞察窗口（默认假设 C1≥0.6 ∧ 跨域 ∧ 低压力，未经统计确认）。"""
        c = conditions or {}
        c1, c3, c5 = c.get("memory_retrievability"), c.get("cross_domain"), c.get("pressure")
        ok = ((c1 is None or c1 >= 0.6) and (c3 is None or (isinstance(c3, list) and len(c3) > 0))
              and (c5 is None or c5 == "low"))
        return {"window_open": ok, "assumption": "默认假设 C1≥0.6 ∧ 跨域 ∧ 低压力（未经统计确认）",
                "conditions": {"memory_retrievability": c1, "cross_domain": c3, "pressure": c5}}
