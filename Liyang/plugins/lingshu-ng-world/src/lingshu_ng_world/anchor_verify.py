# -*- coding: utf-8 -*-
"""anchor_verify · 多感知机锚点验证（旧 ``lingshu.world.anchor_verify`` 的 ng 实现，同名 API）。

单一视觉通道 = 自证陷阱；锚点确认需要独立于视觉的强通道（触觉/行动/听觉）+ 跨时间稳定 +
无多通道矛盾。分层：ACCEPT_stable > ACCEPT_strong > ACCEPT_weak > NOT_ACCEPTED。

与旧版相比修正的缺陷类别：

- **NaN 证据被当成完全支持**：旧版 ``max(0, min(1, nan))`` 得 1.0；这里非有限证据直接拒收。
- **显式 strong 被判定忽略**：旧版 ``strong=True`` 只影响注册表记账，判定仍按通道名查
  STRONG_CHANNELS；这里每条证据记住自身强弱，判定按记录的强弱。
- **反对证据仍判 ACCEPT_weak**：旧版「无矛盾且有任意证据」即 ACCEPT_weak，全部通道
  证据为 0（完全反对）也被接受；这里证据均值 < CONF_THRESHOLD 判 NOT_ACCEPTED。
- **稳定轮数可空转**：旧版每调用一次 verify_anchor 就推进一轮，同一份证据连查 3 次即
  ACCEPT_stable；这里只有自上次判定以来有新证据的判定才计一轮（「跨时间」= 跨证据轮次）。
"""
from __future__ import annotations

import math
import time
from typing import Dict, Optional

__all__ = ["STRONG_CHANNELS", "WEAK_CHANNELS", "CONF_THRESHOLD", "KL_THRESHOLD", "STABLE_ROUNDS",
           "CONFLICT_THRESHOLD", "AnchorVerification", "confirmation_level"]

STRONG_CHANNELS = {"tactile", "action", "audio"}
WEAK_CHANNELS = {"visual", "search", "prediction", "graph"}
CONF_THRESHOLD = 0.5
KL_THRESHOLD = 0.05
STABLE_ROUNDS = 3
CONFLICT_THRESHOLD = 2


def confirmation_level(evidence: Dict[str, float], strong: Dict[str, bool], rounds: int,
                       conflicts: int) -> str:
    """四条件分层：①均值达标 ②有强通道证据 > KL ③稳定轮数 ④冲突通道数 < 阈值。"""
    if not evidence:
        return "ACCEPT_weak"
    ch_ok = sum(evidence.values()) / len(evidence) >= CONF_THRESHOLD
    if not ch_ok:
        return "NOT_ACCEPTED"
    strong_ok = any(v > KL_THRESHOLD for c, v in evidence.items() if strong.get(c))
    if strong_ok and conflicts < CONFLICT_THRESHOLD:
        return "ACCEPT_stable" if rounds >= STABLE_ROUNDS else "ACCEPT_strong"
    return "ACCEPT_weak"


def _new_record() -> Dict:
    return {"channel_evidence": {}, "channel_strong": {}, "channel_conflicts": {},
            "verified_rounds": 0, "confirmation": "ACCEPT_weak", "fresh": False}


class AnchorVerification:
    """多感知机锚点验证器（graph / registry / lease 可选，duck-typed）。"""

    def __init__(self, graph=None, registry=None, lease=None):
        self.graph = graph
        self.registry = registry
        self.lease = lease
        self._anchors: Dict[str, Dict] = {}

    def add_channel_evidence(self, anchor_id: str, channel: str, evidence: float,
                             strong: Optional[bool] = None) -> Dict:
        """记录通道证据 ∈ [0,1]（越界夹取，非有限拒收）；strong 缺省按通道类型。"""
        ev = float(evidence)
        if not math.isfinite(ev):
            raise ValueError(f"evidence must be finite, got {evidence!r}")
        ev = max(0.0, min(1.0, ev))
        is_strong = bool(strong) if strong is not None else channel in STRONG_CHANNELS
        rec = self._anchors.setdefault(anchor_id, _new_record())
        rec["channel_evidence"][channel] = ev
        rec["channel_strong"][channel] = is_strong
        rec["fresh"] = True
        if self.registry is not None:
            (self.registry.record_hit if ev >= 0.5 else self.registry.record_miss)(
                channel, ev, strong=is_strong)
        return self.anchor_state(anchor_id)

    def verify_anchor(self, anchor_id: str) -> Dict:
        """聚合证据 → 确认层级；仅「有新证据」的判定推进/清零稳定轮数。"""
        rec = self._anchors.get(anchor_id)
        if rec is None:
            return {"anchor_id": anchor_id, "confirmation": "unknown", "error": "锚点无验证记录"}
        if not rec["channel_evidence"]:
            return {"anchor_id": anchor_id, "confirmation": "ACCEPT_weak",
                    "verified_rounds": 0, "note": "无任何通道证据"}
        level = confirmation_level(rec["channel_evidence"], rec["channel_strong"],
                                   rec["verified_rounds"], len(rec["channel_conflicts"]))
        rec["confirmation"] = level
        if rec["fresh"]:
            if level in ("ACCEPT_strong", "ACCEPT_stable"):
                rec["verified_rounds"] += 1
            elif level == "NOT_ACCEPTED":
                rec["verified_rounds"] = 0
            rec["fresh"] = False
        return self.anchor_state(anchor_id)

    def channel_conflict_detect(self, anchor_id: str, channel: str, expected: str,
                                actual: str) -> Dict:
        """通道观测与锚点声明不符 → 冲突记录、该通道证据清零。"""
        rec = self._anchors.setdefault(anchor_id, _new_record())
        rec["channel_conflicts"][channel] = {"channel": channel, "expected": expected,
                                             "actual": actual, "ts": time.time()}
        rec["channel_evidence"][channel] = 0.0
        rec["channel_strong"].setdefault(channel, channel in STRONG_CHANNELS)
        rec["fresh"] = True
        out = self.anchor_state(anchor_id)
        out["conflict_detected"] = True
        out["conflict_count"] = len(rec["channel_conflicts"])
        return out

    def anchor_state(self, anchor_id: str) -> Dict:
        rec = self._anchors.get(anchor_id, {})
        return {"anchor_id": anchor_id,
                "channel_evidence": dict(rec.get("channel_evidence", {})),
                "channel_conflicts": {k: {"expected": v["expected"], "actual": v["actual"]}
                                      for k, v in rec.get("channel_conflicts", {}).items()},
                "verified_rounds": rec.get("verified_rounds", 0),
                "confirmation": rec.get("confirmation", "ACCEPT_weak")}

    def verification_summary(self) -> Dict:
        return {aid: {"confirmation": r["confirmation"], "channels": len(r["channel_evidence"]),
                      "conflicts": len(r["channel_conflicts"])}
                for aid, r in self._anchors.items()}
