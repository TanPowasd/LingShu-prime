# -*- coding: utf-8 -*-
"""negative · 负记忆（被否决路径 / 失败经验）是一等公民

旧实现(#216)：rejected_paths 只写不读——设计者否决过的提案原文重提即写入结构层；
同一失败犯 21 次技能照常提取；失败 importance 0.4 对成功 0.6（「负记忆同价」反向落地）。

不变量：
  X1 每条负记忆带规范化键 ``path_key``（kind + 规范化描述的 sha1）；同键再犯不新建行，
     而是 ``hits+1``（重犯计数可查）。
  X2 :meth:`NegativeMemory.check` 是**唯一**的查询入口，提案、技能提取、召回、激活
     全部经它判断（见 engine.py 的调用点），不允许各处各写一套。
  X3 成功与失败经验同价（:data:`EXPERIENCE_IMPORTANCE`）。
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Dict, List, Optional

from .dedup import bigrams, jaccard, normalize
from .store import Store
from .types import now

__all__ = ["NegativeMemory", "EXPERIENCE_IMPORTANCE", "path_key"]

EXPERIENCE_IMPORTANCE = 0.5
SIMILAR = 0.8


def path_key(kind: str, text: str) -> str:
    """X1：负记忆键。"""
    return hashlib.sha1(f"{kind}|{normalize(text)}".encode("utf-8")).hexdigest()


class NegativeMemory:
    """负记忆仓（rejected_paths 表）。"""

    def __init__(self, store: Store) -> None:
        self.store = store

    def record(self, kind: str, description: str, reason: str, evidence: str = "",
               subject: Optional[str] = None) -> str:
        """登记/累计一条负记忆；``subject`` 为判同依据（默认 description）。返回行 id。"""
        key = path_key(kind, subject if subject is not None else description)
        with self.store.db.tx() as c:
            r = c.execute("SELECT id FROM rejected_paths WHERE path_key=? AND status='open'",
                          (key,)).fetchone()
            if r:
                c.execute("UPDATE rejected_paths SET hits=COALESCE(hits,1)+1, reason=?, evidence=? "
                          "WHERE id=?", (reason, evidence, r[0]))
                return r[0]
            rid = f"rp_{uuid.uuid4().hex[:12]}"
            c.execute("INSERT INTO rejected_paths (id, path_type, description, reason, evidence, status, "
                      "created_at, consumed_at, path_key, hits) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (rid, kind, description, reason, evidence, "open", now(), None, key, 1))
            return rid

    def check(self, kind: Optional[str], text: str, fuzzy: bool = True) -> List[Dict]:
        """X2：与 ``text`` 相同（或高度相似）的开放负记忆，按重犯次数降序。"""
        rows = self.list(status="open")
        if kind is not None:
            rows = [r for r in rows if r["path_type"] == kind]
        keys = {path_key(r["path_type"], text) for r in rows}
        exact = [r for r in rows if r.get("path_key") in keys]
        if exact or not fuzzy:
            return sorted(exact, key=lambda r: -(r.get("hits") or 1))
        q = bigrams(text)
        near = [r for r in rows if jaccard(q, bigrams(r["description"])) >= SIMILAR]
        return sorted(near, key=lambda r: -(r.get("hits") or 1))

    def failures_of(self, subject: str) -> int:
        """某主题（如技能名）的累计失败次数。"""
        r = self.store.db.one("SELECT COALESCE(SUM(hits),0) FROM rejected_paths WHERE path_key=? "
                              "AND status='open'", (path_key("action_sequence", subject),))
        return int(r[0]) if r else 0

    def list(self, status: Optional[str] = None) -> List[Dict]:
        """列负记忆。"""
        sql, p = "SELECT * FROM rejected_paths", ()
        if status:
            sql, p = sql + " WHERE status=?", (status,)
        rows = [dict(r) for r in self.store.db.all(sql + " ORDER BY created_at, id", p)]
        for r in rows:
            r["count"] = r.get("hits") or 1          # 旧字段名（上游 #216：重犯计数可查）
        return rows

    def find(self, query: str, limit: int = 10, min_sim: float = 0.15) -> List[Dict]:
        """相似负记忆检索（供学习闭环消费）。"""
        q = bigrams(query)
        scored = [(r, jaccard(q, bigrams(r["description"] + r["reason"]))) for r in self.list("open")]
        scored.sort(key=lambda x: (-x[1], x[0]["id"]))
        return [r for r, s in scored if s > min_sim][:limit]

    def consume(self, rid: str) -> bool:
        """标记已消费（同类问题复用该否决答案后）。"""
        return self.store.db.run("UPDATE rejected_paths SET status='consumed', consumed_at=? WHERE id=?",
                                 (now(), rid)) > 0
