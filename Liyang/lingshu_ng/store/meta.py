# -*- coding: utf-8 -*-
"""meta · 引擎元数据 / 信息差序列 / 行为日志 / 飞轮复用（观测类小表）

不变量：
  M1 观测写入有界：gap_history 滚动保留 :data:`GAP_KEEP` 条，action_logs 保留
     :data:`LOG_KEEP` 条（旧版只增不删）。
  M2 飞轮复用以 (session, round, node) 唯一索引 + ``INSERT OR IGNORE`` 落库：同轮同节点
     恰好一行，由数据库保证而不是靠内存 tracker（#208/core-py-08）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from ..numeric import require_finite
from ..types import dumps, loads, now
from .db import Database

__all__ = ["MetaRepo", "GAP_KEEP", "LOG_KEEP"]

GAP_KEEP = 2000
LOG_KEEP = 5000


class MetaRepo:
    """观测类表仓储。"""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------ kv
    def get(self, key: Optional[str] = None) -> Dict[str, str]:
        """key 给定 ⇒ {key: value}（不存在为空）；None ⇒ 全部。"""
        if key is not None:
            r = self.db.one("SELECT value FROM engine_meta WHERE key=?", (key,))
            return {key: r[0]} if r else {}
        return {r[0]: r[1] for r in self.db.all("SELECT key, value FROM engine_meta")}

    def set(self, key: str, value: object) -> None:
        """upsert。"""
        self.db.run("INSERT OR REPLACE INTO engine_meta (key, value) VALUES (?, ?)", (key, str(value)))

    # ------------------------------------------------------------ 信息差
    def add_gap(self, d_norm: float) -> None:
        """追加一条 D_norm（有限性校验 + 滚动截断）。"""
        v = require_finite(d_norm, "d_norm")
        with self.db.tx() as c:
            c.execute("INSERT INTO gap_history (ts, d_norm) VALUES (?, ?)", (now(), v))
            c.execute("DELETE FROM gap_history WHERE id <= (SELECT MAX(id) FROM gap_history) - ?",
                      (GAP_KEEP,))

    def gaps(self, limit: int = 200) -> List[Dict]:
        """最近 limit 条（时间正序）。"""
        rows = self.db.all("SELECT ts, d_norm FROM gap_history ORDER BY id DESC LIMIT ?", (limit,))
        return [{"ts": r[0], "d_norm": r[1]} for r in reversed(rows)]

    # ------------------------------------------------------------ 行为日志
    def log_action(self, action_type: str, summary: str = "", node_ids: Sequence[str] = (),
                   outcome: Optional[Dict] = None, context: Optional[Dict] = None) -> None:
        """追加行为日志（有界）。"""
        with self.db.tx() as c:
            c.execute("INSERT INTO action_logs (ts, action_type, summary, node_ids, outcome, context) "
                      "VALUES (?,?,?,?,?,?)", (now(), action_type, (summary or "")[:500],
                                              dumps(list(node_ids)), dumps(outcome or {}),
                                              dumps(context or {})))
            c.execute("DELETE FROM action_logs WHERE id <= (SELECT MAX(id) FROM action_logs) - ?",
                      (LOG_KEEP,))

    def actions(self, limit: int = 50) -> List[Dict]:
        """最近 limit 条行为日志（新→旧）。"""
        out = []
        for r in self.db.all("SELECT * FROM action_logs ORDER BY id DESC LIMIT ?", (limit,)):
            d = dict(r)
            for k in ("node_ids", "outcome", "context"):
                d[k] = loads(d.get(k), None)
            out.append(d)
        return out

    # ------------------------------------------------------------ 飞轮
    def note_reuse(self, session_id: str, round_no: int, node_ids: Sequence[str]) -> int:
        """M2：落库复用观测，返回本次新增行数。"""
        ids = sorted(set(node_ids))
        if not ids:
            return 0
        t = now()
        with self.db.tx() as c:
            before = c.total_changes
            c.executemany("INSERT OR IGNORE INTO flywheel_reuse (session_id, round, node_id, ts) "
                          "VALUES (?,?,?,?)", [(session_id, round_no, n, t) for n in ids])
            return c.total_changes - before

    def reuse_stats(self) -> Dict[str, int]:
        """复用统计：总行数 / 去重节点数 / 轮数。"""
        r = self.db.one("SELECT COUNT(*), COUNT(DISTINCT node_id), COUNT(DISTINCT session_id||'|'||round) "
                        "FROM flywheel_reuse")
        return {"rows": r[0], "nodes": r[1], "rounds": r[2]}
