# -*- coding: utf-8 -*-
"""types · 记忆引擎的值对象（节点 / 边 / 条件空间 / 层 / 角色 / 写入回执）

不变量：
  * 行布局：``Node.to_row()`` 的前 16 列与旧 ``nodes`` 表列序逐位一致，``Edge.to_row()``
    的 11 列与旧 ``edges`` 表一致——旧库可原样读写（ng 追加列只在列尾）。
  * 序列化一律走 :func:`dumps`：严格 JSON（``allow_nan=False``）+ ``ensure_ascii=False``
    （根除 #181 中文标签存成 \\uXXXX 与 #185 Infinity/NaN 混入 JSON）。
    条件空间的开区间终点 ``inf`` 以 JSON ``null`` 表示、读回还原为 ``inf``。
  * ``Edge.relation_type`` 接受字符串并强制转换为 :class:`EdgeType`（根除 #195/#44
    「传字符串即 AttributeError 被吞」）。
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "ConditionSpace", "NodeType", "EdgeType", "MemoryLayer", "Role", "Node", "Edge",
    "CausalChain", "WriteResult", "dumps", "loads", "now",
]


def now() -> float:
    """当前墙钟时间（集中一处，便于测试注入）。"""
    return time.time()


_ENC = json.JSONEncoder(ensure_ascii=False, allow_nan=False)
_STR = json.encoder.encode_basestring        # ensure_ascii=False 时 JSONEncoder 用的同一个字符串编码器
_INF = math.inf


def dumps(obj: Any) -> str:
    """严格 JSON 序列化：非有限浮点抛 ``ValueError``，中文原样落盘。
    （复用一个编码器：与 ``json.dumps(obj, ensure_ascii=False, allow_nan=False)`` 逐字节相同。）"""
    if not obj and type(obj) is dict:
        return "{}"
    return _ENC.encode(obj)


def _reject_constant(name: str) -> Any:
    raise ValueError(f"拒收非标准 JSON 常量: {name}")


def loads(s: Optional[str], default: Any = None) -> Any:
    """严格 JSON 反序列化：空串/None → default；NaN/Infinity 常量拒收。"""
    if s is None or s == "":
        return default
    if not isinstance(s, (str, bytes, bytearray)):
        return s
    return json.loads(s, parse_constant=_reject_constant)


@dataclass
class ConditionSpace:
    """条件空间（协议四栏）：观测位置 / 观测工具 / 时间窗 / 存在约束。"""
    observation_position: str
    observation_tool: str
    time_window: Tuple[float, float]
    existence_constraint: str

    def _plain(self) -> Optional[Tuple[str, str, float, float, str]]:
        """常态四栏（三栏为 str、时间窗为非 NaN 浮点且下界有限、上界有限或 +inf）→ (op, ot, lo, hi, ec)，否则 None。"""
        lo, hi = self.time_window
        op, ot, ec = self.observation_position, self.observation_tool, self.existence_constraint
        if (lo.__class__ is float and hi.__class__ is float and op.__class__ is str
                and ot.__class__ is str and ec.__class__ is str and lo == lo and hi == hi and lo != _INF
                and lo != -_INF and hi != -_INF):
            return op, ot, lo, hi, ec
        return None

    def to_json(self) -> str:
        """四栏严格 JSON；时间窗终点为 +inf 时写 null。NaN 拒收。"""
        p = self._plain()
        if p is not None:
            # 快路径（常态：四栏为 str、时间窗为有限浮点或 +inf）：与通用路径逐字节相同
            op, ot, lo, hi, ec = p
            return (f'{{"observation_position": {_STR(op)}, "observation_tool": {_STR(ot)}, '
                    f'"time_window": [{lo!r}, {"null" if hi == _INF else repr(hi)}], '
                    f'"existence_constraint": {_STR(ec)}}}')
        lo, hi = self.time_window
        if isinstance(lo, float) and math.isnan(lo) or isinstance(hi, float) and math.isnan(hi):
            raise ValueError("time_window 不得含 NaN")
        enc = [None if (isinstance(v, float) and math.isinf(v)) else v for v in (lo, hi)]
        return dumps({"observation_position": self.observation_position,
                      "observation_tool": self.observation_tool, "time_window": enc,
                      "existence_constraint": self.existence_constraint})

    @classmethod
    def from_json(cls, s: Any) -> "ConditionSpace":
        """反序列化；缺字段补默认（与旧版兼容），兼容旧库里的 Infinity 字面量。"""
        if s.__class__ is str and s:
            try:
                d = json.loads(s)
            except ValueError:                          # 上游 #267：坏行回落默认条件
                d = {}
            if d.__class__ is dict and len(d) == 4:   # 快路径：ng 落库的标准四栏（与下方通用路径结果相同）
                tw = d.get("time_window")
                op, ot, ec = d.get("observation_position"), d.get("observation_tool"), d.get("existence_constraint")
                if tw.__class__ is list and len(tw) == 2 and op is not None and ot is not None and ec is not None:
                    a, b = tw
                    return cls(op, ot, (math.inf if a is None else a, math.inf if b is None else b), ec)
        elif isinstance(s, str):
            try:                                        # 上游 #267：坏 JSON / "null" / 非对象 → 全部字段补默认
                d = json.loads(s) if s else {}
            except ValueError:
                d = {}
        else:
            d = s
        d = dict(d) if isinstance(d, dict) else {}
        d.setdefault("observation_position", "外部观测位")
        d.setdefault("observation_tool", "文本语义分析")
        d.setdefault("existence_constraint", "（未声明）")
        tw = d.get("time_window", (0.0, 0.0))
        if not isinstance(tw, (list, tuple)):
            tw = (tw, tw)
        tw = tuple(math.inf if v is None else v for v in tw[:2])
        d["time_window"] = tw if len(tw) == 2 else (0.0, 0.0)
        keep = ("observation_position", "observation_tool", "time_window", "existence_constraint")
        return cls(**{k: d[k] for k in keep})

    @classmethod
    def default(cls, position: str, tool: str, constraint: str = "协议实例运行中",
                window: float = 3600.0, start: Optional[float] = None) -> "ConditionSpace":
        """便捷构造：从 ``start``（默认现在）起 ``window`` 秒的时间窗。"""
        t0 = now() if start is None else start
        return cls(position, tool, (t0, t0 + window), constraint)


class NodeType(Enum):
    """节点类型：实体/感知/概念/动作/状态/自我。"""
    ENTITY = "entity"
    PERCEPTION = "perception"
    CONCEPT = "concept"
    ACTION = "action"
    STATE = "state"
    SELF = "self"


class EdgeType(Enum):
    """边类型（与旧版取值一致）。OPPOSITE 在激活中是抑制通路（见 activation.py）。"""
    CAUSAL = "causal"
    SEQUENTIAL = "sequential"
    CORRELATIONAL = "correlational"
    CYCLIC = "cyclic"
    HIERARCHICAL = "hierarchical"
    SPATIAL_ADJACENT = "spatial_adjacent"
    SPATIAL_CONTAINS = "spatial_contains"
    SPATIAL_CONNECTED = "spatial_connected"
    SIMILAR = "similar"
    OPPOSITE = "opposite"
    APPLIES_TO = "applies_to"

    @classmethod
    def coerce(cls, v: Any) -> "EdgeType":
        """字符串/枚举统一成枚举；未知取值抛 ``ValueError``（不静默吞掉）。"""
        if isinstance(v, cls):
            return v
        return cls(str(getattr(v, "value", v)).lower())


class MemoryLayer(Enum):
    """记忆层。各层的可写/可衰减/可检索/可删除不变量集中在 layers.py 声明。"""
    ANCHOR = "anchor"
    STRUCTURE = "structure"
    KNOWLEDGE = "knowledge"
    CONTEXT = "context"
    SELF = "self"

    @classmethod
    def coerce(cls, v: Any) -> "MemoryLayer":
        """字符串/枚举统一成枚举。"""
        if isinstance(v, cls):
            return v
        return cls(str(getattr(v, "value", v)).lower())


#: 层取值 → 枚举（from_row 热路径免 Enum.__call__）
_LAYER_OF = {m.value: m for m in MemoryLayer}


class Role(Enum):
    """实例角色：PRIMARY 可写共享层（anchor/structure）；SUB 只写本地层。"""
    PRIMARY = "primary"
    SUB = "sub"


_EMPTY = {"{}": dict, "[]": list}


def _json_field(raw: Any, default: Any) -> Any:
    """JSON 列反序列化（上游 #267：单条坏行不得毒化整层）——非 JSON / 空串 / null / 标量一律回落默认值。"""
    if raw.__class__ is str and raw in _EMPTY:
        return _EMPTY[raw]()
    if raw is None or raw == "":
        return default
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return default
    return v if isinstance(v, (dict, list)) else default


_SEMANTIC_PREFIXES = (("protocol_", "protocol"), ("radical_", "radical"), ("neural_", "neural"))


def split_semantic_keys(spatial: Any, semantic: Any) -> Tuple[Any, Any, bool]:
    """D-003 坐标字段分离（旧 v1.7 迁移的写入期版本）：spatial 中 ``protocol_*/radical_*/neural_*`` 语义键
    移入 semantic_coordinates（protocol → protocol.concept）。非 dict 坐标（向量/标量，#279）原样返回。"""
    if not isinstance(spatial, dict) or not isinstance(semantic, dict):
        return spatial, semantic, False
    keys = [k for k in spatial if isinstance(k, str) and k.startswith(("protocol_", "radical_", "neural_"))]
    if not keys:
        return spatial, semantic, False
    sp, se = dict(spatial), dict(semantic)
    for k in keys:
        pre, group = next(p for p in _SEMANTIC_PREFIXES if k.startswith(p[0]))
        slot = se.setdefault(group, {})
        if group == "protocol":
            slot = slot.setdefault("concept", {})
        slot[k[len(pre):]] = sp.pop(k)
    return sp, se, True


def loads_tags(raw: Any) -> List[str]:
    """tags 列容错（上游 #267）：JSON 数组照常；NULL/空 → []；JSON 字符串 → [s]；
    非 JSON 字符串（旧库常见 ``"dsh,user"``）按逗号拆分——不静默丢掉旧行的来源类标签。"""
    if raw is None or raw == "" or raw == "[]":
        return []
    if not isinstance(raw, (str, bytes, bytearray)):
        return [str(t) for t in raw] if isinstance(raw, (list, tuple)) else []
    try:
        v = json.loads(raw)
    except ValueError:
        return [t.strip() for t in str(raw).split(",") if t.strip()]
    if isinstance(v, list):
        return [str(t) for t in v]
    return [v] if isinstance(v, str) else []


@dataclass
class Node:
    """时空节点：内容 + 模态 + 空间坐标 + 时间戳 + 条件空间（字段与旧 STNode 同名同序）。"""
    id: str
    content: str
    modality: str
    spatial_coordinates: Dict[str, float]
    temporal_coordinate: float
    condition_space: ConditionSpace
    importance: float = 0.5
    confidence: float = 0.5
    layer: MemoryLayer = MemoryLayer.KNOWLEDGE
    access_count: int = 0
    last_access: float = field(default_factory=now)
    created_at: float = field(default_factory=now)
    tags: List[str] = field(default_factory=list)
    semantic_coordinates: Dict = field(default_factory=dict)
    state_attributes: Dict = field(default_factory=dict)
    entity_id: Optional[str] = None

    def to_row(self) -> tuple:
        """16 列行元组（列序 = 旧 nodes 表）。"""
        return (self.id, self.content, self.modality, dumps(self.spatial_coordinates or {}),
                self.temporal_coordinate, self.condition_space.to_json(),
                self.importance, self.confidence, MemoryLayer.coerce(self.layer).value,
                self.access_count, self.last_access, self.created_at, dumps(list(self.tags)),
                dumps(self.semantic_coordinates or {}), dumps(self.state_attributes or {}),
                self.entity_id)

    @classmethod
    def from_written(cls, row: Sequence[Any], plain: Optional[tuple]) -> "Node":
        """刚由 :meth:`to_row` 写出的行 + 写出时条件空间的常态四栏（``ConditionSpace._plain()``，不可变元组）
        → 与 ``from_row(row)`` 相同的节点，免 JSON 解析（浮点 repr 往返精确）；非常态/非空 JSON 列回落 :meth:`from_row`。"""
        if plain is None or row[3] != "{}" or row[13] != "{}" or row[14] != "{}":
            return cls.from_row(row)
        c = ConditionSpace(plain[0], plain[1], (plain[2], plain[3]), plain[4])
        return cls(row[0], row[1], row[2], {}, row[4], c, row[6], row[7], _LAYER_OF[row[8]],   # to_row 写的是枚举值
                   row[9] or 0, row[10] if row[10] is not None else row[11], row[11], loads_tags(row[12]),
                   {}, {}, row[15])

    @classmethod
    def from_row(cls, row: Sequence[Any]) -> "Node":
        """从行元组还原；容忍旧库的 NULL last_access / 缺尾列。"""
        n = len(row)
        jf = _json_field
        return cls(                       # 位置参数（字段序 = 列序；比关键字参数快）
            row[0], row[1], row[2], jf(row[3], {}), row[4], ConditionSpace.from_json(row[5]),
            row[6], row[7], _LAYER_OF.get(row[8]) or MemoryLayer(row[8]), row[9] or 0,
            row[10] if row[10] is not None else row[11], row[11], loads_tags(row[12]),
            jf(row[13], {}) if n > 13 else {}, jf(row[14], {}) if n > 14 else {},
            row[15] if n > 15 else None)


@dataclass
class Edge:
    """有向边：源→目标 + 关系 + 条件空间 + 置信度（字段与旧 STEdge 同名同序）。"""
    id: str
    source_id: str
    target_id: str
    relation_type: EdgeType
    condition_space: ConditionSpace
    confidence: float = 0.5
    weight: float = 1.0
    verified: bool = False
    created_at: float = field(default_factory=now)
    last_verified: Optional[float] = None
    source_evidence: str = "extracted"

    def __post_init__(self) -> None:
        self.relation_type = EdgeType.coerce(self.relation_type)

    def to_row(self) -> tuple:
        """11 列行元组（列序 = 旧 edges 表）。"""
        return (self.id, self.source_id, self.target_id, self.relation_type.value,
                self.condition_space.to_json(), self.confidence, self.weight,
                int(bool(self.verified)), self.created_at, self.last_verified or 0.0,
                self.source_evidence)

    @classmethod
    def from_row(cls, row: Sequence[Any]) -> "Edge":
        """从行元组还原（last_verified=0 视为未验证时间）。"""
        lv = row[9]
        return cls(id=row[0], source_id=row[1], target_id=row[2],
                   relation_type=EdgeType(row[3]),
                   condition_space=ConditionSpace.from_json(row[4]),
                   confidence=row[5], weight=row[6], verified=bool(row[7]),
                   created_at=row[8], last_verified=lv if lv else None,
                   source_evidence=row[10] if len(row) > 10 else "extracted")


class CausalChain(list):
    """因果链（list 子类）：``truncated`` = 深度预算用尽仍有出边；``cyclic`` = 链尾为回边。

    两个标记互斥（同一条链只有一种终点），空列表专指「无因果后果」。
    """
    __slots__ = ("truncated", "cyclic")

    def __init__(self, edges: Sequence[Any] = (), truncated: bool = False,
                 cyclic: bool = False) -> None:
        super().__init__(edges)
        self.truncated = bool(truncated)
        self.cyclic = bool(cyclic)


@dataclass(frozen=True)
class WriteResult:
    """写入回执：``action`` ∈ {created, merged, updated, unchanged, rejected}；
    ``layer`` 永远是**读回的实际落库层**（根除 #224 回执与落库不一致）。"""
    node_id: Optional[str]
    action: str
    layer: Optional[str]
    reason: str = ""

    @property
    def created(self) -> bool:
        """是否新建了节点。"""
        return self.action == "created"
