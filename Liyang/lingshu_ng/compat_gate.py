# -*- coding: utf-8 -*-
"""compat_gate · 旧 ``lingshu.core.longterm_gate`` 的兼容门面

``LongTermMemoryGate(engine)``：engine 可以是兼容门面（有 ``.ng``）或 ng 原生
:class:`MemoryEngine`。全部行为委托 :class:`lingshu_ng.gate.LongTermGate`。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .gate import KNOWLEDGE, LONG_TERM, LINK_SIM, NOVEL_BOOST, NOVEL_TRIGGER, WEIGHTS, LongTermGate

__all__ = ["LongTermMemoryGate"]


class LongTermMemoryGate:
    """旧类名/常量名/方法名的薄壳。"""

    DEFAULT_WEIGHTS = dict(WEIGHTS)
    LONG_TERM_THRESHOLD = LONG_TERM
    KNOWLEDGE_THRESHOLD = KNOWLEDGE
    NOVEL_TRIGGER = NOVEL_TRIGGER
    NOVEL_BOOST = NOVEL_BOOST
    NOVEL_EDGE_SIM = LINK_SIM

    def __init__(self, engine: Any, weights: Optional[Dict[str, float]] = None) -> None:
        self.engine = engine
        self._g = LongTermGate(getattr(engine, "ng", engine), weights)
        self.weights = self._g.weights

    def _novelty(self, content: str, existing_id: Optional[str] = None) -> float:
        """新奇度（参照 = 全库可检索层，排除 existing_id）。"""
        return self._g.engine.store.text.novelty(content, existing_id)

    def evaluate(self, content: str, source: str = "snapshot", tags: Any = None,
                 existing_id: Optional[str] = None) -> dict:
        """评估（特征 → 评分 → 层级）。"""
        return self._g.evaluate(content, existing_id)

    def write_snapshot(self, content: str, source: str = "snapshot", tags: Optional[list] = None,
                       entities: Optional[list] = None, importance_hint: Optional[float] = None) -> dict:
        """快照写入。"""
        return self._g.write_snapshot(content, source, tags, entities, importance_hint)

    def prefeed(self, content: str, source: str = "input", tags: Optional[list] = None,
                entities: Optional[list] = None) -> dict:
        """前馈新奇。"""
        return self._g.prefeed(content, source, tags, entities)

    def promote_from_context(self, limit: int = 30) -> List[Dict]:
        """情境层提升。"""
        return self._g.promote_from_context(limit)
