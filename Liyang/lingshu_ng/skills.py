# -*- coding: utf-8 -*-
"""skills · 技能记忆（M9 / P1-3）

旧实现(#200)：record_action_sequence 用 ``LIKE %hint%`` 认技能——「备份」的步骤被追加进
「删除备份」并为其增信；hint 含 ``_``/``%`` 命中任意技能；失败从不降信；程序重复追加。

不变量：
  K1 技能身份 = 规范化名称键 ``name_key``（精确匹配，无子串、无通配符）。
  K2 置信度 = Beta(1,1) 先验下的后验均值 (s+1)/(s+f+2)，由成功/失败计数**推导**，
     不接受外部任意增量；手动增量接口只在计数上体现（delta>0 记成功，<0 记失败）。
  K3 程序步骤去重追加：已包含的步骤序列不重复写入。
  K4 负记忆把关：新建技能时导入此前同名失败次数；失败显著多于成功时不再追加程序步骤。
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from .dedup import bigrams, jaccard, normalize
from .numeric import require_finite, unit
from .store import Store
from .types import now

__all__ = ["SkillBook", "posterior"]


def posterior(successes: int, failures: int) -> float:
    """K2：Beta 后验均值。"""
    return (successes + 1.0) / (successes + failures + 2.0)


def _row(r) -> Dict:
    d = dict(r)
    d["successes"] = d.get("successes") or 0
    d["failures"] = d.get("failures") or 0
    out = {k: d[k] for k in ("id", "name", "description", "procedure", "confidence", "version",
                             "successes", "failures")}
    out["failure_count"] = out["failures"]          # 旧字段名（上游 #216）
    return out


class SkillBook:
    """技能仓。"""

    def __init__(self, store: Store) -> None:
        self.store = store

    def add(self, name: str, description: str, procedure: str, confidence: float = 0.5) -> str:
        """登记技能；同名（规范化）已存在则返回既有 id（不重复建卡）。"""
        key = normalize(name)
        if not key:
            raise ValueError("技能名不能为空")
        existing = self.by_name(name)
        if existing:
            return existing["id"]
        sid = f"sk_{uuid.uuid4().hex[:12]}"
        t = now()
        self.store.db.run("INSERT INTO skills (id, name, description, procedure, confidence, version, "
                          "created_at, updated_at, name_key, successes, failures) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (sid, name, description, procedure, unit(confidence), 1, t, t, key, 0, 0))
        return sid

    def by_name(self, name: str) -> Optional[Dict]:
        """K1：精确名查找。"""
        r = self.store.db.one("SELECT * FROM skills WHERE name_key=? ORDER BY created_at LIMIT 1",
                              (normalize(name),))
        return _row(r) if r else None

    def get(self, skill_id: str) -> Optional[Dict]:
        """按 id 取。"""
        r = self.store.db.one("SELECT * FROM skills WHERE id=?", (skill_id,))
        return _row(r) if r else None

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """检索：精确名优先，其余按字面子串（非通配）/ bigram 相似度排序；无关的不返回。"""
        q = (query or "").strip()
        rows = [_row(r) for r in self.store.db.all("SELECT * FROM skills ORDER BY created_at, id")]
        if not q:
            return rows[:limit]
        qk, qg = normalize(q), bigrams(q)
        scored = []
        for s in rows:
            text = s["name"] + s["description"] + (s.get("procedure") or "")   # 上游 #272：步骤字段参与检索
            hay = normalize(text)
            exact = normalize(s["name"]) == qk
            sim = jaccard(qg, bigrams(text))
            # 字面子串：规范化后命中，或原文直接含查询（纯符号查询如 "_" 规范化后为空，按原文字面匹配，#200）
            lit = bool(qk and qk in hay) or q.lower() in text.lower()
            if exact or lit or sim > 0:
                scored.append((2.0 if exact else (1.0 if lit else 0.0) + sim, s))
        scored.sort(key=lambda x: (-x[0], x[1]["id"]))
        return [s for _, s in scored[:limit]]

    def record_outcome(self, skill_id: str, success: bool) -> Optional[float]:
        """记一次成败，置信度按后验重算（K2）。"""
        with self.store.db.tx() as c:
            col = "successes" if success else "failures"
            c.execute(f"UPDATE skills SET {col}=COALESCE({col},0)+1, updated_at=? WHERE id=?",
                      (now(), skill_id))
            r = c.execute("SELECT successes, failures FROM skills WHERE id=?", (skill_id,)).fetchone()
            if r is None:
                return None
            conf = posterior(r[0] or 0, r[1] or 0)
            c.execute("UPDATE skills SET confidence=? WHERE id=?", (conf, skill_id))
            return conf

    def seed_failures(self, skill_id: str, failures: int) -> Optional[float]:
        """新建技能时导入此前的失败次数（负记忆计入后验，K4）。"""
        with self.store.db.tx() as c:
            c.execute("UPDATE skills SET failures=? WHERE id=?", (max(0, int(failures)), skill_id))
            r = c.execute("SELECT successes, failures FROM skills WHERE id=?", (skill_id,)).fetchone()
            if r is None:
                return None
            conf = posterior(r[0] or 0, r[1] or 0)
            c.execute("UPDATE skills SET confidence=? WHERE id=?", (conf, skill_id))
            return conf

    def adjust(self, skill_id: str, delta: float) -> Optional[float]:
        """兼容旧增量接口：delta>0 记成功、<0 记失败、=0 不变（K2）。"""
        d = require_finite(delta, "delta")
        if d == 0:
            s = self.get(skill_id)
            return s["confidence"] if s else None
        return self.record_outcome(skill_id, d > 0)

    def append_procedure(self, skill_id: str, step: str) -> bool:
        """K3：去重追加步骤序列（版本 +1）。"""
        with self.store.db.tx() as c:
            r = c.execute("SELECT procedure FROM skills WHERE id=?", (skill_id,)).fetchone()
            if r is None:
                return False
            proc = r[0] or ""
            if step and normalize(step) in normalize(proc):
                return False
            merged = f"{proc} → {step}" if proc else step
            c.execute("UPDATE skills SET procedure=?, version=version+1, updated_at=? WHERE id=?",
                      (merged, now(), skill_id))
        return True

    def count(self) -> int:
        """技能总数。"""
        return int(self.store.db.scalar("SELECT COUNT(*) FROM skills", default=0))
