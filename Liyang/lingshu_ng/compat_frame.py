# -*- coding: utf-8 -*-
"""compat_frame · 旧 ``ingest_frame``（v1.7 图像帧摄入）在 ng 门面上的实现

协议与旧 ``SpacetimeMemoryEngine.ingest_frame`` 相同：
  * ``frame_data["visual"]`` → ``spatial_coordinates["visual"]``；``caption`` → content；
  * ``entity_hint``（名词）→ 稳定实体 id（规范化文本的 sha1 前缀，ng 无 entity_registry，同名同 id）
    并打 ``ent:<id>`` 标签；``state_hint``（形容词）→ ``state_attributes``；
  * 同实体上一帧 → 本帧建边：状态变 ⇒ CAUSAL，不变 ⇒ SEQUENTIAL（置信 0.7）；
  * ``frame_ref`` 只进内存 LRU（``_local_visual_buffer``），不落共享层（盲区 60/61）。

与旧版差异（均为旧缺陷）：
  * 上一帧在进程内缓存缺失时回查库（``ent:<id>`` + ``image_frame`` 标签中最新者），重开库后时序链不断；
  * ``frame_data`` 非 dict、importance 非有限 / 越界时抛 ``ValueError``，不写半条记录；
  * 整个摄入（写节点 + 建边）在同一事务内完成。
"""
from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional

from . import dedup
from .numeric import unit
from .types import ConditionSpace, EdgeType, MemoryLayer, Node

__all__ = ["FrameMixin", "frame_entity_id"]

VISUAL_BUFFER_MAX = 64


def frame_entity_id(hint: str) -> str:
    """实体提示 → 稳定实体 id（规范化后 sha1 前 12 位）。"""
    key = dedup.normalize(str(hint)) or str(hint)
    return "ent_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


class FrameMixin:
    """混入 SpacetimeMemoryEngine：图像帧摄入。"""

    def _frame_state(self) -> Dict[str, Any]:
        """进程内状态（上一帧缓存 / 本地视觉缓冲），惰性创建。"""
        st = self.__dict__.get("_frame_rt")
        if st is None:
            st = self.__dict__["_frame_rt"] = {"last": {}, "buffer": []}
        return st

    @property
    def _local_visual_buffer(self) -> List[Dict]:
        """原始帧引用的本地 LRU 缓冲（不进共享层）。"""
        return self._frame_state()["buffer"]

    def _prev_frame(self, entity_id: str) -> Optional[Node]:
        """同实体上一帧：进程内缓存优先，缺失时回查库。"""
        nid = self._frame_state()["last"].get(entity_id)
        if nid:
            return self.ng.store.nodes.get(nid)
        frames = [n for n in self.ng.store.nodes.by_tag(f"ent:{entity_id}", None) if "image_frame" in n.tags]
        return max(frames, key=lambda n: (n.created_at, n.id)) if frames else None

    def ingest_frame(self, frame_data: Dict, entity_hint: Optional[str] = None,
                     state_hint: Optional[Dict] = None, semantic_attention: Optional[Dict] = None,
                     condition_space: Optional[ConditionSpace] = None) -> Node:
        """摄入一帧图像（自下而上）；返回写入的节点。semantic_attention 为预留通道，ng 不记录。"""
        if not isinstance(frame_data, dict):
            raise ValueError("frame_data 必须是 dict")
        imp = unit(frame_data.get("importance", 0.6), "importance")
        t = time.time()
        cs = condition_space or ConditionSpace("视觉感知", "帧摄入", (t, t + 3600), "协议实例运行中")
        sp = {"visual": frame_data["visual"]} if frame_data.get("visual") else {}
        name = str(entity_hint) if entity_hint else None
        entity_id = frame_entity_id(name) if name else None
        state = dict(state_hint or {})
        se = {"protocol": {"entity": [name] if name else [], "attribute": list(state), "relation": [],
                           "logic": []}, "radical": {}, "neural": {}}
        node = Node(id=f"img_{uuid.uuid4().hex[:8]}_{int(t * 1000)}",
                    content=frame_data.get("caption", "") or (name or "图像帧"), modality="image",
                    spatial_coordinates=sp, temporal_coordinate=t, condition_space=cs, importance=imp,
                    confidence=0.5, layer=MemoryLayer.KNOWLEDGE,
                    tags=["image_frame"] + ([f"ent:{entity_id}"] if entity_id else []),
                    semantic_coordinates=se, state_attributes=state, entity_id=entity_id,
                    last_access=t, created_at=t)
        with self.ng.store.db.tx():
            prev = self._prev_frame(entity_id) if entity_id else None
            if prev is not None and prev.id != node.id:
                changed = prev.state_attributes != state
                se["protocol"]["relation"].append("causal" if changed else "sequential")
            self.ng.store.nodes.put(node)
            if prev is not None and prev.id != node.id:
                self.add_edge(prev.id, node.id, EdgeType.CAUSAL if changed else EdgeType.SEQUENTIAL, 0.7)
        st = self._frame_state()
        if entity_id:
            st["last"][entity_id] = node.id
        if "frame_ref" in frame_data:
            st["buffer"].append({"entity_id": entity_id, "frame_ref": frame_data["frame_ref"], "ts": t})
            del st["buffer"][:-VISUAL_BUFFER_MAX]
        return node
