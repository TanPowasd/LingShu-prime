# -*- coding: utf-8 -*-
"""nodes · 节点仓储（参数化 SQL；所有写路径都经过 LayerPolicy）

不变量：
  N1 每个写方法在一个事务里「读旧行 → 层守卫 → 写」，守卫同时看旧行层与新行层(#127)。
  N2 标签查询是**精确匹配**（``json_each``），绝无 ``LIKE '%tag%'``（#183/#181）。
  N3 列表型查询没有隐藏的固定 LIMIT/预筛：调用方显式给 limit，``None`` 即全量(#35/#88/#179)。
  N4 数值字段写入前经 numeric 校验（拒 NaN/inf，钳 [0,1]）。
  N5 删除节点与删除其关联边在同一事务内完成（无孤儿边）。
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from .. import dedup
from ..layers import LayerPolicy
from ..numeric import unit
from ..types import MemoryLayer, Node, dumps, loads, now, split_semantic_keys
from .db import Database, fill_keys
from .schema import KEY_MISSING, PENDING_KEY, chunks, placeholders

__all__ = ["NodeRepo"]

_COLS16 = ("id, content, modality, spatial_coordinates, temporal_coordinate, condition_space, "
           "importance, confidence, layer, access_count, last_access, created_at, tags, "
           "semantic_coordinates, state_attributes, entity_id")
_SELECT = f"SELECT {_COLS16} FROM nodes"
_INSERT = f"INSERT INTO nodes ({_COLS16}, dedup_key) VALUES ({placeholders(17)})"
_REPLACE = f"INSERT OR REPLACE INTO nodes ({_COLS16}, dedup_key) VALUES ({placeholders(17)})"
#: 要按创建时间/时间坐标有序读的 query 排序（走惰性索引 S5）
_LAZY_ORDERS = frozenset({"created", "created_desc", "temporal_desc"})
_UPDATABLE = {"content", "modality", "importance", "confidence", "layer", "tags",
              "state_attributes", "semantic_coordinates", "entity_id", "last_access",
              "access_count", "temporal_coordinate", "spatial_coordinates"}


class NodeRepo:
    """节点仓储。``policy`` 决定当前角色能写什么。"""

    def __init__(self, db: Database, policy: LayerPolicy, text: Optional[Any] = None) -> None:
        self.db = db
        self.policy = policy
        self.text = text
        #: (节点 id, 落库行, 写入时条件空间的常态四栏) —— 最近一次 put 的写入（见 :meth:`fresh`）
        self.last_written: Optional[tuple] = None
        self._backfill_keys()

    # ------------------------------------------------------------ 内部
    def _backfill_keys(self) -> None:
        """旧库/外部裸写入留下的空 dedup_key 补齐（去重索引已建时才查——走索引 O(1)；未建时待补键合法，
        建索引前由 :meth:`Database.need_lazy_indexes` 批量补齐）。无空行时零写入。"""
        if not self.db.lazy_ready or not self.db.scalar(f"SELECT 1 FROM nodes WHERE {KEY_MISSING} LIMIT 1"):
            return
        with self.db.tx() as c:
            fill_keys(c)

    def _layer_of(self, c: Any, node_id: str) -> Optional[MemoryLayer]:
        row = c.execute("SELECT layer FROM nodes WHERE id=?", (node_id,)).fetchone()
        return MemoryLayer(row[0]) if row else None

    @staticmethod
    def _validated(node: Node) -> Node:
        node.importance = unit(node.importance, "importance")
        node.confidence = unit(node.confidence, "confidence")
        node.layer = MemoryLayer.coerce(node.layer)
        node.tags = list(dict.fromkeys(str(t) for t in (node.tags or [])))
        node.spatial_coordinates, node.semantic_coordinates, _ = split_semantic_keys(
            node.spatial_coordinates, node.semantic_coordinates or {})          # D-003（上游 #279 同族）
        return node

    # ------------------------------------------------------------ 写
    def put(self, node: Node, allow_transition: bool = False, index_now: bool = False) -> str:
        """新建或按 id 覆盖节点（覆盖时守卫旧行层，N1）。

        派生文本索引默认惰性（只记脏，首读前批量重建）；``index_now`` = 在同一事务内即时索引本节点
        （逐条写、写后马上要读索引的路径用，如带去重的单条摄入——免得下一次读再单独开事务 flush）。"""
        node = self._validated(node)
        # S5：去重索引未建（灌库期）时内容键写等长占位，建索引前批量补齐；建成后写时即算
        row = node.to_row() + (dedup.content_key(node.content) if self.db.lazy_ready else PENDING_KEY,)
        with self.db.tx() as c:
            # 新 id（常态）：守卫只看新行层，直接 INSERT——主键冲突才回退到「读旧行 → 双层守卫 → 覆盖」
            self.policy.check_node_write(node.layer, None, allow_transition)
            try:
                c.execute(_INSERT, row)
            except sqlite3.IntegrityError:
                old = self._layer_of(c, node.id)
                if old is None:
                    raise
                self.policy.check_node_write(node.layer, old, allow_transition)
                c.execute(_REPLACE, row)
            if index_now and self.text is not None:
                self.text.reindex_written(c, node.id, row[1], row[12], row[8], True)
            # 派生文本索引：触发器已记脏，首次读之前由 TextIndex.flush 统一（批量）重建
        self.last_written = (node.id, row, node.condition_space._plain())
        return node.id

    def fresh(self, node_id: str) -> Optional[Node]:
        """刚由 :meth:`put` 写入的节点（按落库行还原，免回读）；不是最近一次写入则返回 None。
        仅当正文/模态为 str（列亲和性不会改写其类型）时可用，否则调用方应回读。"""
        lw = self.last_written
        if lw is None or lw[0] != node_id:
            return None
        row = lw[1]
        if row[1].__class__ is not str or row[2].__class__ is not str:
            return None
        return Node.from_written(row[:16], lw[2])

    def _reindex(self) -> None:
        """写时维护派生文本索引（同一事务；触发器已记脏）。"""
        if self.text is not None:
            self.text.flush()

    def update(self, node_id: str, allow_transition: bool = False, **fields: Any) -> bool:
        """按白名单字段更新；layer 变化走迁移守卫。返回是否命中。"""
        bad = set(fields) - _UPDATABLE
        if bad:
            raise ValueError(f"不可更新的字段: {sorted(bad)}")
        enc = self._encode(fields)
        with self.db.tx() as c:
            old = self._layer_of(c, node_id)
            if old is None:
                return False
            new = MemoryLayer.coerce(fields.get("layer", old))
            if new != old:
                self.policy.check_node_write(new, old, allow_transition)
            elif set(fields) <= {"tags", "state_attributes"}:
                self.policy.check_node_annotate(old)
            else:
                self.policy.check_node_write(new, old)
            if "content" in enc:
                enc["dedup_key"] = dedup.content_key(enc["content"])
            sets = ", ".join(f"{k}=?" for k in enc)
            c.execute(f"UPDATE nodes SET {sets} WHERE id=?", tuple(enc.values()) + (node_id,))
            if {"content", "tags", "layer"} & set(enc):
                self._reindex()
        return True

    @staticmethod
    def _encode(fields: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in fields.items():
            if k in ("importance", "confidence"):
                v = unit(v, k)
            elif k == "layer":
                v = MemoryLayer.coerce(v).value
            elif k == "tags":
                v = dumps(list(dict.fromkeys(str(t) for t in v)))
            elif k in ("state_attributes", "semantic_coordinates", "spatial_coordinates"):
                v = dumps(v or {})
            out[k] = v
        return out

    def add_tags(self, node_id: str, tags: Iterable[str]) -> bool:
        """幂等追加标签（共享层需 PRIMARY）。"""
        with self.db.tx():
            n = self.get(node_id)
            if n is None:
                return False
            merged = list(dict.fromkeys(n.tags + [str(t) for t in tags]))
            if merged != n.tags:
                self.update(node_id, tags=merged)
        return True

    def remove_tags(self, node_id: str, tags: Iterable[str]) -> bool:
        """移除标签（共享层需 PRIMARY）。"""
        drop = set(tags)
        with self.db.tx():
            n = self.get(node_id)
            if n is None:
                return False
            kept = [t for t in n.tags if t not in drop]
            if kept != n.tags:
                self.update(node_id, tags=kept)
        return True

    def touch(self, node_ids: Sequence[str]) -> None:
        """访问计数 +1（同一连接、同一事务；不会落进另一个空库，#52）。"""
        ids = list(dict.fromkeys(node_ids))
        if not ids:
            return
        t = now()
        with self.db.tx() as c:
            for part in chunks(ids):
                c.execute(f"UPDATE nodes SET access_count=COALESCE(access_count,0)+1, last_access=? "
                          f"WHERE id IN ({placeholders(len(part))})", (t, *part))

    def delete(self, node_id: str, force: bool = False) -> bool:
        """删除节点及其全部关联边（N5）。``force`` 仅供维护周期的自然遗忘使用。"""
        with self.db.tx() as c:
            layer = self._layer_of(c, node_id)
            if layer is None:
                return False
            if not force:
                self.policy.check_node_delete(layer)
            c.execute("DELETE FROM edges WHERE source_id=? OR target_id=?", (node_id, node_id))
            c.execute("DELETE FROM nodes WHERE id=?", (node_id,))
            c.execute("DELETE FROM protections WHERE node_id=?", (node_id,))
        return True

    # ------------------------------------------------------------ 读
    def get(self, node_id: str) -> Optional[Node]:
        """按 id 取节点。"""
        row = self.db.one(f"{_SELECT} WHERE id=?", (node_id,))
        return Node.from_row(tuple(row)) if row else None

    def get_many(self, ids: Sequence[str]) -> Dict[str, Node]:
        """批量取（分块，不受 SQLite 变量上限影响）。"""
        out: Dict[str, Node] = {}
        uniq = list(dict.fromkeys(ids))
        for part in chunks(uniq):
            for r in self.db.all(f"{_SELECT} WHERE id IN ({placeholders(len(part))})", part):
                out[r[0]] = Node.from_row(tuple(r))
        return out

    def layer_of(self, node_id: str) -> Optional[MemoryLayer]:
        """节点所在层（不存在返回 None）。"""
        v = self.db.scalar("SELECT layer FROM nodes WHERE id=?", (node_id,))
        return MemoryLayer(v) if v else None

    def query(self, layer: Optional[MemoryLayer] = None, modality: Optional[str] = None,
              min_importance: float = 0.0, limit: Optional[int] = 50,
              order: str = "importance") -> List[Node]:
        """过滤查询。order ∈ {importance, created, created_desc, temporal_desc, written, written_desc}。"""
        where, params = ["COALESCE(importance, 0) >= ?"], [min_importance]
        if layer is not None:
            where.append("layer=?")
            params.append(MemoryLayer.coerce(layer).value)
        if modality is not None:
            where.append("modality=?")
            params.append(modality)
        orders = {"importance": "importance DESC, last_access DESC, id",
                  "created": "created_at ASC, id", "created_desc": "created_at DESC, id",
                  "temporal_desc": "temporal_coordinate DESC, id",
                  "written": "rowid ASC", "written_desc": "rowid DESC"}   # 写入顺序（上游 #259）
        if order in _LAZY_ORDERS:
            self.db.need_lazy_indexes()
        sql = f"{_SELECT} WHERE {' AND '.join(where)} ORDER BY {orders[order]}"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return [Node.from_row(tuple(r)) for r in self.db.all(sql, params)]

    def by_tag(self, tag: str, limit: Optional[int] = 50) -> List[Node]:
        """精确标签匹配（N2）。"""
        sql = (f"{_SELECT} WHERE EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid(nodes.tags) THEN nodes.tags ELSE '[]' END) WHERE value = ?) "
               "ORDER BY importance DESC, last_access DESC, id")
        params: List[Any] = [tag]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return [Node.from_row(tuple(r)) for r in self.db.all(sql, params)]

    def by_key(self, key: str, layers: Optional[Sequence[MemoryLayer]] = None) -> List[Node]:
        """按规范化内容键精确查找（M5 精确去重入口，无视野上限）。"""
        if not key:
            return []
        self.db.need_keys()
        sql, params = f"{_SELECT} WHERE dedup_key=?", [key]
        if layers:
            sql += f" AND layer IN ({placeholders(len(layers))})"
            params += [MemoryLayer.coerce(x).value for x in layers]
        return [Node.from_row(tuple(r)) for r in self.db.all(sql + " ORDER BY created_at, id", params)]

    def in_range(self, start: float, end: float, layer: Optional[MemoryLayer] = None,
                 limit: Optional[int] = 50) -> List[Node]:
        """时间坐标范围查询（走索引，不先截 importance 前 N 条，#179）。"""
        self.db.need_lazy_indexes()
        sql, params = f"{_SELECT} WHERE temporal_coordinate BETWEEN ? AND ?", [start, end]
        if layer is not None:
            sql += " AND layer=?"
            params.append(MemoryLayer.coerce(layer).value)
        sql += " ORDER BY temporal_coordinate DESC, id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return [Node.from_row(tuple(r)) for r in self.db.all(sql, params)]

    def undated_in_range(self, start: float, end: float) -> List[Node]:
        """无时间坐标（NULL）的行按 created_at 落在 [start, end] 取（时空查询的 created_at 回落口径，
        上游 PR #91：只替 NULL 回落，显式 0.0 仍按 0.0）。IS NULL 走时间坐标索引。"""
        self.db.need_lazy_indexes()
        sql = f"{_SELECT} WHERE temporal_coordinate IS NULL AND created_at BETWEEN ? AND ? ORDER BY created_at, id"
        return [Node.from_row(tuple(r)) for r in self.db.all(sql, (start, end))]

    def texts(self, ids: Optional[Sequence[str]] = None, layers: Optional[Sequence[MemoryLayer]] = None,
              limit: Optional[int] = None, newest_first: bool = False) -> List[tuple]:
        """轻量投影 [(id, content, tags_json, modality, importance)]——不做整行反序列化。"""
        sql, params = "SELECT id, content, tags, modality, importance FROM nodes WHERE 1=1", []
        if ids is not None:
            out: List[tuple] = []
            for part in chunks(list(dict.fromkeys(ids))):
                out += [tuple(r) for r in self.db.all(sql + f" AND id IN ({placeholders(len(part))})", part)]
            return out
        self.db.need_lazy_indexes()
        if layers:
            sql += f" AND layer IN ({placeholders(len(layers))})"
            params = [MemoryLayer.coerce(x).value for x in layers]
        sql += " ORDER BY created_at DESC, id" if newest_first else " ORDER BY created_at, id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return [tuple(r) for r in self.db.all(sql, params)]

    def rows_newest_first(self, ids: Sequence[str], layer: MemoryLayer) -> List[tuple]:
        """[(id, content, created_at)]：给定 id 中属于 ``layer`` 的节点，按创建时间新→旧。"""
        out: List[tuple] = []
        for part in chunks(list(dict.fromkeys(ids))):
            out += [tuple(r) for r in self.db.all(
                f"SELECT id, content, created_at FROM nodes WHERE +layer=? AND id IN ({placeholders(len(part))})",
                [MemoryLayer.coerce(layer).value, *part])]
        out.sort(key=lambda r: (-(r[2] or 0.0), r[0]))
        return out

    def scan(self, layers: Optional[Sequence[MemoryLayer]] = None) -> Iterator[Node]:
        """全量流式扫描（可限层）。"""
        self.db.need_lazy_indexes()
        sql, params = _SELECT, []
        if layers:
            sql += f" WHERE layer IN ({placeholders(len(layers))})"
            params = [MemoryLayer.coerce(x).value for x in layers]
        for r in self.db.iterate(sql + " ORDER BY created_at, id", params):
            yield Node.from_row(tuple(r))

    def count(self, layer: Optional[MemoryLayer] = None) -> int:
        """节点计数。"""
        if layer is None:
            return int(self.db.scalar("SELECT COUNT(*) FROM nodes", default=0))
        return int(self.db.scalar("SELECT COUNT(*) FROM nodes WHERE layer=?",
                                  (MemoryLayer.coerce(layer).value,), default=0))

    def state_attr(self, node_id: str, key: str, default: Any = None) -> Any:
        """读 state_attributes 的单键。"""
        raw = self.db.scalar("SELECT state_attributes FROM nodes WHERE id=?", (node_id,))
        try:
            sa = loads(raw, {})
        except ValueError:
            sa = {}
        return sa.get(key, default) if isinstance(sa, dict) else default

    def set_state_attr(self, node_id: str, key: str, value: Any) -> None:
        """写 state_attributes 的单键（事务内读改写）。"""
        with self.db.tx():
            n = self.get(node_id)
            if n is None:
                return
            sa = dict(n.state_attributes or {})
            sa[key] = value
            self.update(node_id, state_attributes=sa)
