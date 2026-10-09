# -*- coding: utf-8 -*-
"""exchange · M13 全库导出 / 导入 / 完整性校验

旧实现的缺陷类别：缺失表即抛 OperationalError(#16)；JSON 键原样拼进 SQL 列名、导入是
无密钥的全权写通道（篡改备份即可改写结构层、伪造终裁、关闭升级点）(#125)；孤儿边可经
导入引入(#93/PR113)。

不变量：
  X1 导出/导入只处理 :data:`TABLES` 中**实际存在**的表；缺失表显式列入 skipped_tables。
  X2 列名白名单：声明表用 schema 声明列，扩展表（如 entities）用库中 PRAGMA 实际列；
     任何不在白名单的键被丢弃并计入 ``dropped_columns``，绝不拼进 SQL。
  X3 受保护数据（共享层节点、治理表）无设计者密钥时不导入，计入 ``quarantined``。
  X4 节点先于边导入；端点缺失的边拒绝导入（``orphan_edges_rejected``）。
  X5 导出内容确定性：每张表按主键/rowid 排序。
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence, Tuple

from . import dedup
from .governance import verify_designer
from .layers import LayerPolicy
from .store import Store, schema
from .types import now

__all__ = ["TABLES", "GOVERNANCE_TABLES", "export_all", "import_all", "verify_integrity"]

TABLES: Tuple[str, ...] = ("nodes", "edges", "blindspots", "skills", "promotion_proposals",
                           "protections", "rejected_paths", "verifier_standards",
                           "escalation_points", "entities",
                           # 上游 #270：OBS-REV1 持久化表（D 序列 / 行为日志 / 飞轮基线等）同样进全库备份
                           "gap_history", "action_logs", "engine_meta", "flywheel_reuse",
                           "self_snapshots", "activation_nodes")
GOVERNANCE_TABLES = frozenset({"promotion_proposals", "protections", "verifier_standards",
                               "escalation_points", "self_snapshots"})


def _not_exported(store: Store) -> List[str]:
    """库内实际存在、但不在 :data:`TABLES` 里的表（派生索引表等，可由 nodes 重建）——显式列出，
    让「全库备份」漏了什么一目了然（上游 #270：不得静默漏表）。"""
    return sorted(t for t in store.db.tables() if t not in TABLES and not t.startswith("sqlite_"))


def _internal_meta(table: str, row: Dict) -> bool:
    """engine_meta 里以 ``_`` 开头的键（如 _schema_version）是本库结构元数据，不随备份迁移。"""
    return table == "engine_meta" and str(row.get("key", "")).startswith("_")


def _reject(name: str) -> None:
    raise ValueError(f"备份含非标准 JSON 常量 {name}，拒绝导入")


def _columns(store: Store, table: str) -> Tuple[str, ...]:
    if table in schema.TABLES:
        return schema.columns_of(table)
    return tuple(r[1] for r in store.db.all(f"PRAGMA table_info({table})"))


def _rows(store: Store, table: str) -> List[Dict]:
    cols = _columns(store, table)
    order = "id" if "id" in cols else ("node_id" if "node_id" in cols else "rowid")
    rows = [dict(r) for r in store.db.all(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {order}")]
    return _with_keys(rows) if table == "nodes" else rows


def _with_keys(rows: List[Dict]) -> List[Dict]:
    """S5：灌库期待补（占位/NULL）的 dedup_key 现算（导出与写时即算逐项相同；不写库）。"""
    todo = [r for r in rows if r.get("dedup_key", "") in (None, schema.PENDING_KEY)]
    for r, k in zip(todo, dedup.content_keys([r.get("content") for r in todo])):
        r["dedup_key"] = k
    return rows


def export_all(store: Store, output_path: str) -> Dict:
    """X1/X5：导出实际存在的 M13 表到 JSON。"""
    have = store.db.tables()
    skipped = [t for t in TABLES if t not in have]
    data: Dict[str, object] = {"meta": {"version": "ng-1", "exported_at": now(),
                                        "condition_space": "全库备份 · 有损投影", "skipped_tables": skipped}}
    derived = _not_exported(store)
    data["meta"]["not_exported_tables"] = derived
    for t in TABLES:
        if t in have:
            data[t] = [r for r in _rows(store, t) if not _internal_meta(t, r)]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
    return {"exported_nodes": len(data.get("nodes", [])), "path": output_path,
            "tables": len(data) - 1, "skipped_tables": skipped, "not_exported_tables": derived}


def _protected_row(table: str, row: Dict) -> bool:
    if table in GOVERNANCE_TABLES:
        return True
    if table == "nodes":
        try:
            return LayerPolicy.rule(row.get("layer")).shared
        except (KeyError, ValueError):
            return True
    return False


#: nodes 的 JSON 列 → 期望容器类型（上游 #267：导入面把坏值规范成合法 JSON，单条坏行不得毒化整层）
_NODE_JSON = {"tags": list, "spatial_coordinates": None, "semantic_coordinates": dict,
              "state_attributes": dict}


def _sanitize_node(r: Dict) -> int:
    """就地规范一条待导入节点行的 JSON 列；返回修正的列数。tags 非 JSON 时按逗号切分（旧备份常见写法）；
    condition_space 非对象 JSON 时补默认四栏；spatial_coordinates 接受对象或数组（向量坐标）。"""
    fixed = 0
    for col, kind in _NODE_JSON.items():
        if col not in r:
            continue
        raw = r[col]
        try:
            v = json.loads(raw) if isinstance(raw, str) and raw else raw
        except ValueError:
            v = [t.strip() for t in raw.split(",") if t.strip()] if col == "tags" else None
        ok = isinstance(v, (dict, list)) if kind is None else isinstance(v, kind)
        if col == "tags" and ok:
            ok = all(isinstance(t, str) for t in v)
            v = [str(t) for t in v]
        good = v if ok else ([] if kind is list else {})
        out = json.dumps(good, ensure_ascii=False)
        if out != raw:
            r[col], fixed = out, fixed + 1
    if "condition_space" in r:
        from .types import ConditionSpace
        cs = ConditionSpace.from_json(r["condition_space"]).to_json()
        if cs != r["condition_space"]:
            try:
                same = json.loads(cs) == json.loads(r["condition_space"])
            except (TypeError, ValueError):
                same = False
            if not same:
                r["condition_space"], fixed = cs, fixed + 1
    return fixed


def _insert(store: Store, table: str, rows: Sequence[Dict], node_ids: set, trusted: bool,
            report: Dict) -> int:
    allowed = _columns(store, table)
    n = 0
    for r in rows:
        if not isinstance(r, dict) or _internal_meta(table, r):
            continue
        extra = set(r) - set(allowed)
        report["dropped_columns"].update(f"{table}.{k}" for k in extra)
        if not trusted and _protected_row(table, r):
            report["quarantined"][table] = report["quarantined"].get(table, 0) + 1
            continue
        if table == "edges" and not {r.get("source_id"), r.get("target_id")} <= node_ids:
            report["orphan_edges_rejected"] += 1
            continue
        cols = [c for c in allowed if c in r]
        if not cols:
            continue
        if table == "nodes":
            r = dict(r)
            k = _sanitize_node(r)
            if k:
                report["sanitized_nodes"] = report.get("sanitized_nodes", 0) + 1
        store.db.conn.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "
                              f"VALUES ({schema.placeholders(len(cols))})", tuple(r[c] for c in cols))
        n += 1
    return n


def import_all(store: Store, input_path: str, designer_key: Optional[str] = None) -> Dict:
    """X2–X4：单事务导入；返回各表导入数与隔离/丢弃明细。"""
    with open(input_path, encoding="utf-8") as f:
        data = json.loads(f.read(), parse_constant=_reject)   # 拒收 NaN/Infinity
    trusted = verify_designer(designer_key)
    have = store.db.tables()
    report: Dict = {"imported": {}, "skipped_tables": [], "quarantined": {},
                    "dropped_columns": set(), "orphan_edges_rejected": 0}
    with store.db.tx():
        for t in TABLES:
            if t not in have:
                report["skipped_tables"].append(t)
                continue
            node_ids = {r[0] for r in store.db.all("SELECT id FROM nodes")} if t == "edges" else set()
            report["imported"][t] = _insert(store, t, data.get(t) or [], node_ids, trusted, report)
    if "nodes" in report["imported"]:
        from .store.nodes import NodeRepo
        NodeRepo(store.db, store.policy)          # 回填新导入行的 dedup_key
    report["dropped_columns"] = sorted(report["dropped_columns"])
    # 上游 #113：恢复路径的悬挂引用必须当场可见。ng 拒收孤儿边（X4，不让损坏落库），
    # 这里同时给出旧契约的判据：dangling_rows = 备份中端点缺失的边行数（按行计，
    # 两端都悬挂的一条边算 1），integrity_ok = 备份完整且导入后库内无孤儿边。
    report["dangling_rows"] = report["orphan_edges_rejected"]
    report["integrity_ok"] = report["dangling_rows"] == 0 and store.edges.orphans() == 0
    return report


def verify_integrity(store: Store) -> Dict:
    """完整性：孤儿边端点数 + 各层计数。"""
    orphans = store.edges.orphans()
    return {"orphan_edges": orphans, "integrity_ok": orphans == 0}
