"""v3 四标签、时效、排名资格与失效传播（方案 v3.0 §9、§16；手册 v1.1 §2.3 组合规则、§4、§13.4、§13.5、§13.7）。纯标准库。

API（稳定 v1）
    make_labels(audience, depth, risk, recommendation, *, risk_basis=None, risk_reviewed=False) -> dict
    validity(completed_on, *, today, reviews=()) -> dict          默认 90 天；只有按变更范围的复核记录能续期
    security_overlay(incidents) -> dict                           确认严重事件 → 暂停推荐；可疑 → 调查中
    eligibility(record, *, today) -> dict                         数字排名 / 徽章 / "值得试" 入口资格
    propagate_invalidation(edges, invalidated) -> dict            判分器/证据 → run → analysis → report → 榜单/badge
"""
from __future__ import annotations

import datetime as _dt
from collections import deque

AUDIENCE = ("个人", "团队", "企业")
DEPTH = ("作者自测", "快测", "标准", "深度审计")
RISK = ("低", "中", "高", "关键", "未评估")
RECOMMEND = ("可推荐", "限定场景", "待复核", "暂停推荐")
VALID_DAYS = 90
RANKABLE_CAPS = ("✅", "❌", "➖")   # ❓/🚧/方法试验/证据失效不进数字排名
SEVERE = ("关键", "高")              # 🔴 关键 / 🟠 高


class LabelError(ValueError):
    pass


def _d(x) -> _dt.date:
    return x if isinstance(x, _dt.date) else _dt.date.fromisoformat(str(x))


def make_labels(audience, depth, risk, recommendation, *, risk_basis=None, risk_reviewed=False) -> dict:
    if audience not in AUDIENCE:
        raise LabelError(f"面向谁用 ∉ {AUDIENCE}")
    if depth not in DEPTH:
        raise LabelError(f"我们测到哪 ∉ {DEPTH}")
    if risk not in RISK:
        raise LabelError(f"风险多大 ∉ {RISK}")
    if recommendation not in RECOMMEND:
        raise LabelError(f"现在推不推 ∉ {RECOMMEND}")
    notes = []
    # §13.7：无可执行映射依据或未经独立复核 → 未评估
    if risk != "未评估" and not (risk_basis and risk_reviewed):
        notes.append(f"风险等级 {risk} 缺可复核映射依据或独立复核，降为未评估")
        risk = "未评估"
    if depth == "作者自测" and recommendation in ("可推荐", "限定场景"):
        notes.append("作者自测只是声明，不能发推荐标签 → 待复核")
        recommendation = "待复核"
    return {"面向谁用": audience, "面向谁用_注": "作者想给谁用，不代表已经验证",
            "我们测到哪": depth, "风险多大": risk, "风险依据": risk_basis, "现在推不推": recommendation,
            "notes": notes}


def validity(completed_on, *, today, reviews=()) -> dict:
    """reviews: [{date, scope_matched: bool}]；只认按变更范围执行的复核记录续期（改页面日期不算）。"""
    start = _d(completed_on)
    for r in reviews:
        if r.get("scope_matched") is True and _d(r["date"]) >= start:
            start = _d(r["date"])
    exp = start + _dt.timedelta(days=VALID_DAYS)
    t = _d(today)
    days_left = (exp - t).days
    return {"valid_from": start.isoformat(), "expires_on": exp.isoformat(), "expired": t > exp,
            "review_queue": 0 <= days_left <= 14, "days_left": days_left}


def security_overlay(incidents) -> dict:
    """incidents: [{severity: 关键|高|中, status: confirmed|suspected|blocked|single_observation, opened_on?}]"""
    paused = any(i["status"] == "confirmed" and i["severity"] in SEVERE for i in incidents)
    investigating = any(i["status"] == "suspected" for i in incidents)
    if paused:
        return {"recommendation": "暂停推荐", "status": "已确认严重安全事件", "worth_trying": False, "capability_retained": True}
    if investigating:
        return {"recommendation": "待复核", "status": "调查中", "worth_trying": False, "capability_retained": True,
                "note": "临时暂停推荐并标调查中；14 天内公开进展，不以超时自动洗白"}
    return {"recommendation": None, "status": "无已确认事件（≠ 已验证安全）", "worth_trying": True, "capability_retained": True}


def eligibility(record: dict, *, today) -> dict:
    """record: {capability(五状态或 None), release_state, completed_on, reviews, incidents,
                evidence: {originals_deleted: bool, redacted_sufficient: bool}, invalidated: bool,
                comparable_group: str}"""
    reasons = []
    cap, rel = record.get("capability"), record.get("release_state")
    rank = badge = worth = True
    if rel != "正式":
        rank = badge = worth = False; reasons.append(f"发布状态 {rel}：不进数字排名")
    if cap not in RANKABLE_CAPS:
        rank = False; reasons.append(f"能力结论 {cap}：正常展示，不进数字排名")
        if cap != "✅":
            worth = False
    if cap in ("❌", "➖", "❓", "🚧", None):
        worth = False
    v = validity(record["completed_on"], today=today, reviews=record.get("reviews", ()))
    if v["expired"]:
        rank = badge = worth = False; reasons.append(f"超过 {VALID_DAYS} 天未复核（{v['expires_on']} 到期）：退出有效排名与徽章，历史结论保留")
    sec = security_overlay(record.get("incidents", ()))
    if not sec["worth_trying"]:
        worth = False; badge = False if sec["recommendation"] == "暂停推荐" else badge
        reasons.append(f"安全：{sec['status']} → {sec['recommendation']}；能力结果保留、不进“值得试”")
    ev = record.get("evidence") or {}
    evidence_state = "完整"
    if ev.get("originals_deleted") and not ev.get("redacted_sufficient"):
        rank = badge = worth = False; evidence_state = "证据核验受限"
        reasons.append("原件已删除且脱敏替代证据不足：证据核验受限/待复核，退出有效数字排名和推荐徽章")
    if record.get("invalidated"):
        rank = badge = worth = False; evidence_state = "证据不完整/待复核"
        reasons.append("依赖的判分器/证据已失效：从有效榜单移出，badge 失效，历史文本保留")
    return {"numeric_rank": rank, "badge": badge, "worth_trying": worth, "display": True,
            "capability_retained": cap, "recommendation": sec["recommendation"], "security_status": sec["status"],
            "evidence_state": evidence_state, "validity": v, "reasons": reasons}


def propagate_invalidation(edges, invalidated) -> dict:
    """edges: [(上游id, 下游id)]，如 (scorer:v1, run:r1)、(run:r1, analysis:a1)、(analysis:a1, report:x)、(report:x, badge:x)。
    返回 {affected: 有序列表（BFS，确定性）, by_kind: {kind: [...]}}。id 形如 "kind:name"。"""
    down = {}
    for u, v in edges:
        down.setdefault(u, []).append(v)
    seen, order = set(invalidated), []
    q = deque(sorted(invalidated))
    while q:
        u = q.popleft()
        for v in sorted(down.get(u, ())):
            if v not in seen:
                seen.add(v); order.append(v); q.append(v)
    by = {}
    for x in order:
        by.setdefault(x.split(":", 1)[0], []).append(x)
    return {"affected": order, "by_kind": by}
