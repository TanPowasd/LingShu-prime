# -*- coding: utf-8 -*-
"""store · 持久化层（SQLite，纯标准库）

``Store`` 是一个薄聚合：一个 :class:`Database`（连接 + 锁 + 事务）+ 绑定同一
:class:`LayerPolicy` 的各仓储。上层组件只依赖 ``Store``，不直接拼 SQL 改节点/边。
"""
from __future__ import annotations

import sqlite3

from ..layers import LayerPolicy
from ..types import Role
from .db import Database
from .edges import EdgeRepo
from .meta import MetaRepo
from .nodes import NodeRepo
from .registry import Registry
from .textindex import TextIndex

__all__ = ["Store", "Database", "NodeRepo", "EdgeRepo", "MetaRepo", "Registry", "TextIndex"]


class Store:
    """持久化聚合。``path=':memory:'`` 为进程内私有库（只能经本对象共享）。"""

    def __init__(self, path: str = ":memory:", role: Role = Role.PRIMARY) -> None:
        self.db = Database(path)
        self.policy = LayerPolicy(role)
        self.text = TextIndex(self.db)
        self.nodes = NodeRepo(self.db, self.policy, self.text)
        self.edges = EdgeRepo(self.db, self.policy)
        self.meta = MetaRepo(self.db)
        self.registry = Registry(self.db, self.policy)

    @property
    def role(self) -> Role:
        """当前实例角色。"""
        return self.policy.role

    @property
    def conn(self):
        """底层连接（仅供兼容层/诊断；ng 组件不经此写库）。"""
        return self.db.conn

    def close(self) -> None:
        """关闭（幂等）。关闭前把记脏的派生索引落盘，库文件里不留待重建的脏节点。"""
        if not self.db.closed:
            try:
                self.text.flush()
            except sqlite3.Error:  # 只读介质等：脏表留在库里，下次打开后首读前重建（不丢正确性）
                pass
        self.db.close()
