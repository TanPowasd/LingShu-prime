# -*- coding: utf-8 -*-
"""db · 连接与事务边界

不变量：
  D1 每个 :class:`Database` 持有**一个**连接 + 一把可重入锁；跨线程的全部读写都在锁内
     串行（根除 #81「共享单连接 2 写线程 235 次异常」）。``:memory:`` 库只能经同一个
     Database 对象共享（显式），不存在“另开一个连接落进空库”(#52)。
  D2 所有写操作在 :meth:`tx` 里执行：``BEGIN IMMEDIATE`` → 成功 COMMIT / 任何异常 ROLLBACK，
     可嵌套（内层并入外层）。不会留下半截事务占着写锁(#184)。
  D4 ``PRAGMA foreign_keys=ON``：端点不存在的边写不进、删点前必须先删边（ng 全部写路径如此）；
     旧库中历史遗留的孤儿边不会阻止打开（SQLite 只检查新写入），可用 :meth:`fk_violations` 体检。
  D3 连接为 autocommit 模式（isolation_level=None），旧调用方直接 ``conn.execute`` +
     ``conn.commit()`` 依旧可用（commit 为无操作），但 ng 代码内部从不依赖隐式事务。
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Sequence

from . import schema

__all__ = ["Database"]


class Database:
    """SQLite 连接 + 锁 + 事务。``path=':memory:'`` 时为进程内私有库。"""

    def __init__(self, path: str = ":memory:", timeout: float = 30.0) -> None:
        self.path = path
        if path != ":memory:" and not path.startswith("file:"):
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=timeout,
                                    isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._depth = 0
        # D4 参照完整性由 SQLite 强制（edges.source_id/target_id → nodes.id）；所有 ng 写路径先删边再删点
        self.conn.execute("PRAGMA foreign_keys=ON")
        if path != ":memory:":
            self._pragma("PRAGMA journal_mode=WAL")
            self._pragma(f"PRAGMA busy_timeout={int(timeout * 1000)}")
        self.migrated = schema.migrate(self.conn)
        self.closed = False

    def _pragma(self, sql: str) -> None:
        try:
            self.conn.execute(sql)
        except sqlite3.DatabaseError:
            pass  # 只读介质/内存库不支持 WAL：保持默认日志模式即可

    # ------------------------------------------------------------ 事务
    def tx(self) -> "_Tx":
        """写事务（可嵌套）。异常时整体回滚并原样抛出。（类式上下文管理器：热路径免生成器开销）"""
        return _Tx(self)

    # ------------------------------------------------------------ 读
    def all(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        """执行查询并取全部行（锁内）。"""
        with self.lock:
            return self.conn.execute(sql, tuple(params)).fetchall()

    def one(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        """执行查询并取首行（锁内）。"""
        with self.lock:
            return self.conn.execute(sql, tuple(params)).fetchone()

    def scalar(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        """取首行首列。"""
        row = self.one(sql, params)
        return default if row is None else row[0]

    def iterate(self, sql: str, params: Sequence[Any] = (), batch: int = 500) -> Iterator[sqlite3.Row]:
        """分批流式读取（大库全量扫描时不一次性物化）。"""
        with self.lock:
            cur = self.conn.execute(sql, tuple(params))
            rows = cur.fetchmany(batch)
        while rows:
            for r in rows:
                yield r
            with self.lock:
                rows = cur.fetchmany(batch)

    # ------------------------------------------------------------ 写
    def run(self, sql: str, params: Sequence[Any] = ()) -> int:
        """单语句写（自带事务），返回受影响行数。"""
        with self.tx() as c:
            return c.execute(sql, tuple(params)).rowcount

    def fk_violations(self) -> List[tuple]:
        """``PRAGMA foreign_key_check`` 结果（空 = 参照完整）。"""
        with self.lock:
            return [tuple(r) for r in self.conn.execute("PRAGMA foreign_key_check").fetchall()]

    def tables(self) -> set:
        """当前实际存在的表。"""
        with self.lock:
            return schema.existing_tables(self.conn)

    def close(self) -> None:
        """关闭连接（幂等）。"""
        with self.lock:
            if not self.closed:
                self.conn.close()
                self.closed = True


class _Tx:
    """:meth:`Database.tx` 的上下文对象：外层 ``BEGIN IMMEDIATE`` → COMMIT / 异常 ROLLBACK，内层并入外层。"""
    __slots__ = ("db", "outer")

    def __init__(self, db: Database) -> None:
        self.db = db
        self.outer = False

    def __enter__(self) -> sqlite3.Connection:
        db = self.db
        db.lock.acquire()
        try:
            self.outer = db._depth == 0
            if self.outer:
                db.conn.execute("BEGIN IMMEDIATE")
        except BaseException:
            db.lock.release()
            raise
        db._depth += 1
        return db.conn

    def __exit__(self, et, ev, tb) -> bool:
        db = self.db
        try:
            db._depth -= 1
            if self.outer:
                db.conn.execute("ROLLBACK" if et is not None else "COMMIT")
        finally:
            db.lock.release()
        return False
