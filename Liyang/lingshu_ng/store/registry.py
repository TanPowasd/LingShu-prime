# -*- coding: utf-8 -*-
"""registry · 保护名单 / 盲区 / 晋升提案 / 校验标准 / 升级点（治理类小表）

不变量：
  R1 保护登记受层守卫（SUB 不能给共享层节点登记保护，#217）；保护随节点删除而清除，
     名单不会只增不减(#257)。
  R2 盲区状态白名单 {open, resolved}；离开 open 必须带设计者密钥——校验在本层(#222)。
  R3 晋升提案在登记时锁定内容哈希；复核/终裁时内容已变 ⇒ 拒绝(#140)。状态机单向：
     pending → verified → approved|rejected；复核人 ≠ 提案人；rejected 不可复活(#118)。
  R4 校验标准四步：pending → reviewed → cs_approved → approved|denied，各步签名人互不相同。
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Dict, List, Optional

from ..governance import require_designer
from ..layers import LayerPolicy
from ..types import MemoryLayer, now
from .db import Database

__all__ = ["Registry"]

BLINDSPOT_STATUS = ("open", "resolved")


def _hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Registry:
    """治理类表的仓储集合。"""

    def __init__(self, db: Database, policy: LayerPolicy) -> None:
        self.db = db
        self.policy = policy

    # ------------------------------------------------------------ 保护
    def protect(self, node_id: str, reason: str) -> bool:
        """登记不可遗忘保护 + no_forget 标签（同一事务）。节点不存在返回 False。"""
        from .nodes import NodeRepo  # 局部导入避免循环
        with self.db.tx() as c:
            r = c.execute("SELECT layer FROM nodes WHERE id=?", (node_id,)).fetchone()
            if r is None:
                return False
            self.policy.check_node_annotate(MemoryLayer(r[0]))
            c.execute("INSERT OR REPLACE INTO protections (node_id, reason, created_at) VALUES (?,?,?)",
                      (node_id, reason, now()))
            NodeRepo(self.db, self.policy).add_tags(node_id, ["no_forget"])
        return True

    def protected_ids(self) -> List[str]:
        """保护名单（只含仍存在的节点）。"""
        return [r[0] for r in self.db.all(
            "SELECT p.node_id FROM protections p JOIN nodes n ON n.id=p.node_id ORDER BY p.created_at")]

    # ------------------------------------------------------------ 盲区
    def add_blindspot(self, code: str, description: str, severity: str = "medium",
                      category: str = "operational", predictability: str = "pending_assessment") -> str:
        """登记盲区（meta 类别零记录，由引擎层拒绝）。"""
        bid = _uid("bs")
        self.db.run("INSERT INTO blindspots (id, code, description, severity, category, status, "
                    "created_at, resolved_at, predictability) VALUES (?,?,?,?,?,?,?,?,?)",
                    (bid, code, description, severity, category, "open", now(), None, predictability))
        return bid

    def list_blindspots(self, status: Optional[str] = None) -> List[Dict]:
        """列盲区。"""
        sql, p = "SELECT * FROM blindspots", ()
        if status:
            sql, p = sql + " WHERE status=?", (status,)
        out = []
        for r in self.db.all(sql + " ORDER BY created_at, id", p):
            d = dict(r)
            d.setdefault("attempts", 0)
            out.append(d)
        return out

    def set_blindspot_status(self, blindspot_id: str, status: str,
                             designer_key: Optional[str] = None) -> bool:
        """R2：状态白名单；离开 open 需设计者密钥。"""
        if status not in BLINDSPOT_STATUS:
            raise ValueError(f"非法盲区状态: {status!r}（允许 {BLINDSPOT_STATUS}）")
        if status != "open":
            require_designer(designer_key, "关闭盲区")
        return self.db.run("UPDATE blindspots SET status=?, resolved_at=? WHERE id=?",
                           (status, now() if status != "open" else None, blindspot_id)) > 0

    # ------------------------------------------------------------ 晋升提案
    def add_proposal(self, node_id: str, requester: str, reason: str, content: str) -> str:
        """登记晋升提案并锁定内容哈希（R3）。"""
        pid = _uid("pp")
        self.db.run("INSERT INTO promotion_proposals (id, node_id, requester, reason, verified_by, "
                    "adjudicated_by, status, created_at, decided_at, content_hash) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (pid, node_id, requester, reason, "", "", "pending", now(), None, _hash(content)))
        return pid

    def proposal(self, pid: str) -> Optional[Dict]:
        """取提案。"""
        r = self.db.one("SELECT * FROM promotion_proposals WHERE id=?", (pid,))
        return dict(r) if r else None

    def verify_proposal(self, pid: str, verified_by: str, current_content: str) -> bool:
        """复核：仅 pending、复核人≠提案人、内容未被改写。"""
        p = self.proposal(pid)
        if not p or p["status"] != "pending" or verified_by == p["requester"]:
            return False
        if p.get("content_hash") and p["content_hash"] != _hash(current_content):
            return False
        return self.db.run("UPDATE promotion_proposals SET verified_by=?, status='verified' "
                           "WHERE id=? AND status='pending'", (verified_by, pid)) > 0

    def decide_proposal(self, pid: str, by: str, approved: bool, designer_key: Optional[str],
                        current_content: str) -> Optional[Dict]:
        """终裁（需密钥）：仅 verified、内容未改写；返回提案（含决定）或 None。"""
        require_designer(designer_key, "晋升终裁")
        p = self.proposal(pid)
        if not p or p["status"] != "verified":
            return None
        if p.get("content_hash") and p["content_hash"] != _hash(current_content):
            return None
        status = "approved" if approved else "rejected"
        self.db.run("UPDATE promotion_proposals SET adjudicated_by=?, status=?, decided_at=? "
                    "WHERE id=? AND status='verified'", (by, status, now(), pid))
        p.update(status=status, adjudicated_by=by)
        return p

    # ------------------------------------------------------------ 校验标准
    def add_standard(self, name: str, param: str, value: float, reason: str, proposer: str) -> str:
        """登记校验标准提案。"""
        vid = _uid("vs")
        self.db.run("INSERT INTO verifier_standards (id, name, param, value, reason, proposer, "
                    "independent_reviewer, cs_reviewer, adjudicator, status, created_at, decided_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (vid, name, param, value, reason, proposer, "", "", "", "pending", now(), None))
        return vid

    def list_standards(self, status: Optional[str] = None) -> List[Dict]:
        """列校验标准。"""
        sql, p = "SELECT * FROM verifier_standards", ()
        if status:
            sql, p = sql + " WHERE status=?", (status,)
        return [dict(r) for r in self.db.all(sql + " ORDER BY created_at, id", p)]

    def step_standard(self, vid: str, who: str, approved: bool, stage: str,
                      designer_key: Optional[str] = None) -> Optional[Dict]:
        """推进一步（R4）。stage ∈ {review, cs_review, adjudicate}。"""
        flow = {"review": ("pending", "independent_reviewer", "reviewed", "rejected"),
                "cs_review": ("reviewed", "cs_reviewer", "cs_approved", "cs_rejected"),
                "adjudicate": ("cs_approved", "adjudicator", "approved", "denied")}
        need, col, ok_s, no_s = flow[stage]
        if stage == "adjudicate":
            require_designer(designer_key, "校验标准终裁")
        rows = self.list_standards()
        row = next((r for r in rows if r["id"] == vid), None)
        if not row or row["status"] != need:
            return None
        signers = {row["proposer"], row["independent_reviewer"], row["cs_reviewer"]} - {""}
        if who in signers:
            return None
        status = ok_s if approved else no_s
        self.db.run(f"UPDATE verifier_standards SET {col}=?, status=?, decided_at=? WHERE id=?",
                    (who, status, now() if stage == "adjudicate" else None, vid))
        row.update({col: who, "status": status})
        return row

    # ------------------------------------------------------------ 升级点
    def add_escalation(self, code: str, trigger: str, condition: str, action: str,
                       severity: str = "medium") -> str:
        """登记升级点。"""
        eid = _uid("esc")
        self.db.run("INSERT INTO escalation_points (id, code, trigger, condition, action, severity, "
                    "enabled, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (eid, code, trigger, condition, action, severity, 1, now()))
        return eid

    def list_escalations(self, enabled_only: bool = True) -> List[Dict]:
        """列升级点。"""
        sql = "SELECT * FROM escalation_points" + (" WHERE enabled=1" if enabled_only else "")
        out = []
        for r in self.db.all(sql + " ORDER BY created_at, id"):
            d = dict(r)
            d["enabled"] = bool(d["enabled"])
            out.append(d)
        return out

    def set_escalation_enabled(self, eid: str, enabled: bool, designer_key: Optional[str] = None) -> bool:
        """启停升级点均需设计者密钥（上游 #130：与终裁同款 fail-closed）。"""
        require_designer(designer_key, "启停升级点")
        return self.db.run("UPDATE escalation_points SET enabled=? WHERE id=?",
                           (int(bool(enabled)), eid)) > 0
