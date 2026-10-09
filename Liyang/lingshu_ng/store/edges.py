# -*- coding: utf-8 -*-
"""edges · 边仓储

不变量：
  E1 写边前在同一事务内确认两端节点存在（应用层参照完整性，替代从未启用的
     FOREIGN KEY，#93），并按两端**当前层**做角色守卫（#244/#234）；同 id 覆盖时
     旧边的两端也要过守卫（防止 SUB 用同 id 切断 PRIMARY 的结构层边）。
  E2 置信度/权重经 numeric 校验（#117 verify_edge 接受 5.0/-1）。
  E3 遍历类读接口按 rowid（插入序）返回，保证同输入同输出（环枚举可复现）。
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..layers import LayerPolicy
from ..numeric import require_finite, unit
from ..types import Edge, EdgeType, MemoryLayer, now
from .db import Database
from .schema import chunks, placeholders

__all__ = ["EdgeRepo"]

_COLS = ("id, source_id, target_id, relation_type, condition_space, confidence, weight, "
         "verified, created_at, last_verified, source_evidence")
_SELECT = f"SELECT {_COLS} FROM edges"
_TWO_LAYERS = ("SELECT (SELECT COALESCE(layer, '') FROM nodes WHERE id=?), "
               "(SELECT COALESCE(layer, '') FROM nodes WHERE id=?)")
_INSERT = f"INSERT INTO edges ({_COLS}) VALUES ({','.join('?' * 11)})"
_REPLACE = f"INSERT OR REPLACE INTO edges ({_COLS}) VALUES ({','.join('?' * 11)})"


class EdgeRepo:
    """边仓储。"""

    def __init__(self, db: Database, policy: LayerPolicy) -> None:
        self.db = db
        self.policy = policy

    def _layers(self, c: Any, ids: Iterable[str]) -> List[Optional[MemoryLayer]]:
        ids = list(ids)
        if len(ids) == 2:                       # 边两端：一次查询、一行（不存在 ⇒ NULL；层为 NULL ⇒ '' 照旧报错）
            row = c.execute(_TWO_LAYERS, ids).fetchone()
            return [None if v is None else MemoryLayer(v) for v in (row[0], row[1])]
        out: List[Optional[MemoryLayer]] = []
        for nid in ids:
            r = c.execute("SELECT layer FROM nodes WHERE id=?", (nid,)).fetchone()
            out.append(MemoryLayer(r[0]) if r else None)
        return out

    def _guard_existing(self, c: Any, edge_id: str) -> Optional[Tuple[str, str]]:
        r = c.execute("SELECT source_id, target_id FROM edges WHERE id=?", (edge_id,)).fetchone()
        if r is None:
            return None
        self.policy.check_edge_write(self._layers(c, (r[0], r[1])))
        return r[0], r[1]

    # ------------------------------------------------------------ 写
    def put(self, edge: Edge) -> str:
        """新建/覆盖边（E1 + E2）。端点缺失抛 ``ValueError``。"""
        edge.relation_type = EdgeType.coerce(edge.relation_type)
        edge.confidence = unit(edge.confidence, "confidence")
        edge.weight = require_finite(edge.weight, "weight")
        with self.db.tx() as c:
            layers = self._layers(c, (edge.source_id, edge.target_id))
            if None in layers:
                raise ValueError(f"边端点不存在: {edge.source_id} → {edge.target_id}")
            self.policy.check_edge_write(layers)
            row = edge.to_row()
            try:                                   # 新 id（常态）直接插入；主键冲突才守卫旧边两端后覆盖
                c.execute(_INSERT, row)
            except sqlite3.IntegrityError:
                if self._guard_existing(c, edge.id) is None:
                    raise
                c.execute(_REPLACE, row)
        return edge.id

    def verify(self, edge_id: str, new_confidence: Optional[float] = None) -> bool:
        """标记已验证（可同时改置信度，经值域校验）。"""
        conf = None if new_confidence is None else unit(new_confidence, "new_confidence")
        with self.db.tx() as c:
            if self._guard_existing(c, edge_id) is None:
                return False
            if conf is None:
                c.execute("UPDATE edges SET verified=1, last_verified=? WHERE id=?", (now(), edge_id))
            else:
                c.execute("UPDATE edges SET verified=1, last_verified=?, confidence=? WHERE id=?",
                          (now(), conf, edge_id))
        return True

    def delete(self, edge_id: str) -> bool:
        """删边（守卫两端层）。"""
        with self.db.tx() as c:
            if self._guard_existing(c, edge_id) is None:
                return False
            c.execute("DELETE FROM edges WHERE id=?", (edge_id,))
        return True

    # ------------------------------------------------------------ 读
    def get(self, edge_id: str) -> Optional[Edge]:
        """按 id 取边。"""
        r = self.db.one(f"{_SELECT} WHERE id=?", (edge_id,))
        return Edge.from_row(tuple(r)) if r else None

    def outgoing(self, node_id: str, types: Optional[Sequence[str]] = None) -> List[Edge]:
        """出边（插入序）。``types`` 为关系取值过滤。"""
        return self._adjacent("source_id", node_id, types)

    def incoming(self, node_id: str, types: Optional[Sequence[str]] = None) -> List[Edge]:
        """入边（插入序）。"""
        return self._adjacent("target_id", node_id, types)

    def _adjacent(self, col: str, node_id: str, types: Optional[Sequence[str]]) -> List[Edge]:
        sql, params = f"{_SELECT} WHERE {col}=?", [node_id]
        if types:
            vals = [EdgeType.coerce(t).value for t in types]
            sql += f" AND relation_type IN ({placeholders(len(vals))})"
            params += vals
        return [Edge.from_row(tuple(r)) for r in self.db.all(sql + " ORDER BY rowid", params)]

    def topology(self, types: Optional[Sequence[str]] = None) -> List[Tuple[str, str, str, str, float]]:
        """轻量拓扑：[(id, src, dst, relation, confidence)]（插入序，不反序列化条件空间）。"""
        sql, params = "SELECT id, source_id, target_id, relation_type, confidence FROM edges", []
        if types:
            vals = [EdgeType.coerce(t).value for t in types]
            sql += f" WHERE relation_type IN ({placeholders(len(vals))})"
            params = vals
        return [tuple(r) for r in self.db.all(sql + " ORDER BY rowid", params)]

    def pairs(self, types: Optional[Sequence[str]] = None) -> List[Tuple[str, str]]:
        """判环快路径用的 (源, 目标) 对（无序、不取边 id）。"""
        sql, params = "SELECT source_id, target_id FROM edges", []
        if types:
            vals = [EdgeType.coerce(t).value for t in types]
            sql += f" WHERE relation_type IN ({placeholders(len(vals))})"
            params = vals
        with self.db.lock:
            cur = self.db.conn.cursor()
            cur.row_factory = None
            return cur.execute(sql, params).fetchall()

    def arcs(self, types: Optional[Sequence[str]] = None) -> List[Tuple[str, str, str]]:
        """判环/枚举用的最小拓扑：[(id, src, dst)]（插入序）。"""
        sql, params = "SELECT id, source_id, target_id FROM edges", []
        if types:
            vals = [EdgeType.coerce(t).value for t in types]
            sql += f" WHERE relation_type IN ({placeholders(len(vals))})"
            params = vals
        with self.db.lock:
            cur = self.db.conn.cursor()
            cur.row_factory = None                       # 纯元组：免逐行构造 sqlite3.Row
            return cur.execute(sql + " ORDER BY rowid", params).fetchall()

    def get_many(self, ids: Sequence[str]) -> Dict[str, Edge]:
        """批量取边（分块）。"""
        out: Dict[str, Edge] = {}
        for part in chunks(list(dict.fromkeys(ids))):
            for r in self.db.all(f"{_SELECT} WHERE id IN ({placeholders(len(part))})", part):
                out[r[0]] = Edge.from_row(tuple(r))
        return out

    def between(self, ids: Sequence[str]) -> List[Tuple[str, str, str]]:
        """两端都在 ``ids`` 内的边 [(src, dst, relation)]。"""
        s = set(ids)
        return [(a, b, r) for _, a, b, r, _ in self.topology() if a in s and b in s]

    def count(self, verified: Optional[bool] = None) -> int:
        """边计数。"""
        if verified is None:
            return int(self.db.scalar("SELECT COUNT(*) FROM edges", default=0))
        return int(self.db.scalar("SELECT COUNT(*) FROM edges WHERE verified=?",
                                  (int(verified),), default=0))

    def orphans(self) -> int:
        """引用缺失节点的边端点数（完整性校验）。"""
        a = self.db.scalar("SELECT COUNT(*) FROM edges e LEFT JOIN nodes n ON e.source_id=n.id "
                           "WHERE n.id IS NULL", default=0)
        b = self.db.scalar("SELECT COUNT(*) FROM edges e LEFT JOIN nodes n ON e.target_id=n.id "
                           "WHERE n.id IS NULL", default=0)
        return int(a) + int(b)
