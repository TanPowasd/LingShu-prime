# -*- coding: utf-8 -*-
"""schema · 单一声明式表定义 + 结构对照式迁移

不变量：
  S1 :data:`TABLES` / :data:`INDEXES` 是库结构的**唯一**来源；建表、补列、补索引、
     导出导入的列白名单全部由它推导（根除 #92「版本号与 DDL 无绑定，老库永远补不上」、
     旧守卫「不含索引」的已知缺口，以及 #125「JSON 键原样拼进 SQL 列名」）。
  S2 打开库时先**只读**比对实际结构（表/列/索引）；结构齐全则零写入返回
     （保住多进程启动只读化的初衷）；有缺失则在单个事务内补齐并写版本标记。
  S3 nodes/edges 的前 16/11 列保持旧列序；ng 新增列只追加在尾部。
  S4 派生文本索引（倒排 node_terms / df / 新奇特征计数）由纯 SQL 触发器「写时记脏 + 删时级联」
     维护，任何连接的裸写都不会让索引静默过期；触发器缺失（旧库）⇒ 全量记脏重建。
"""
from __future__ import annotations

import sqlite3
from typing import Dict, Iterable, List, Sequence, Set, Tuple

__all__ = ["SCHEMA_VERSION", "TABLES", "INDEXES", "TRIGGERS", "columns_of", "missing_parts", "migrate",
           "existing_tables", "DERIVED_TABLES"]

SCHEMA_VERSION = 3

Column = Tuple[str, str]

#: 表 → (列定义序列, 表级约束)。列定义中的类型/默认值与旧 DDL 一致。
TABLES: Dict[str, Tuple[Tuple[Column, ...], str]] = {
    "nodes": ((
        ("id", "TEXT PRIMARY KEY"), ("content", "TEXT"), ("modality", "TEXT"),
        ("spatial_coordinates", "TEXT"), ("temporal_coordinate", "REAL"),
        ("condition_space", "TEXT"), ("importance", "REAL"), ("confidence", "REAL"),
        ("layer", "TEXT"), ("access_count", "INTEGER DEFAULT 0"), ("last_access", "REAL"),
        ("created_at", "REAL"), ("tags", "TEXT"),
        ("semantic_coordinates", "TEXT DEFAULT '{}'"), ("state_attributes", "TEXT DEFAULT '{}'"),
        ("entity_id", "TEXT"),
        ("dedup_key", "TEXT"),                 # ng：规范化内容键（M5 精确去重，无视野上限）
    ), ""),
    "edges": ((
        ("id", "TEXT PRIMARY KEY"), ("source_id", "TEXT"), ("target_id", "TEXT"),
        ("relation_type", "TEXT"), ("condition_space", "TEXT"), ("confidence", "REAL"),
        ("weight", "REAL"), ("verified", "INTEGER DEFAULT 0"), ("created_at", "REAL"),
        ("last_verified", "REAL"), ("source_evidence", "TEXT DEFAULT 'extracted'"),
    ), "FOREIGN KEY (source_id) REFERENCES nodes(id), FOREIGN KEY (target_id) REFERENCES nodes(id)"),
    "blindspots": ((
        ("id", "TEXT PRIMARY KEY"), ("code", "TEXT"), ("description", "TEXT"),
        ("severity", "TEXT"), ("category", "TEXT DEFAULT 'operational'"),
        ("status", "TEXT DEFAULT 'open'"), ("created_at", "REAL"), ("resolved_at", "REAL"),
        ("predictability", "TEXT DEFAULT 'pending_assessment'"),
    ), ""),
    "skills": ((
        ("id", "TEXT PRIMARY KEY"), ("name", "TEXT"), ("description", "TEXT"),
        ("procedure", "TEXT"), ("confidence", "REAL DEFAULT 0.5"), ("version", "INTEGER DEFAULT 1"),
        ("created_at", "REAL"), ("updated_at", "REAL"),
        ("name_key", "TEXT"),                  # ng：规范化技能名（精确匹配，无 LIKE）
        ("successes", "INTEGER DEFAULT 0"), ("failures", "INTEGER DEFAULT 0"),
    ), ""),
    "promotion_proposals": ((
        ("id", "TEXT PRIMARY KEY"), ("node_id", "TEXT"), ("requester", "TEXT"), ("reason", "TEXT"),
        ("verified_by", "TEXT DEFAULT ''"), ("adjudicated_by", "TEXT DEFAULT ''"),
        ("status", "TEXT DEFAULT 'pending'"), ("created_at", "REAL"), ("decided_at", "REAL"),
        ("content_hash", "TEXT"),              # ng：提案锁定内容（#140）
    ), ""),
    "protections": ((("node_id", "TEXT PRIMARY KEY"), ("reason", "TEXT"), ("created_at", "REAL")), ""),
    "rejected_paths": ((
        ("id", "TEXT PRIMARY KEY"), ("path_type", "TEXT"), ("description", "TEXT"),
        ("reason", "TEXT"), ("evidence", "TEXT DEFAULT ''"), ("status", "TEXT DEFAULT 'open'"),
        ("created_at", "REAL"), ("consumed_at", "REAL"),
        ("path_key", "TEXT"), ("hits", "INTEGER DEFAULT 1"),   # ng：负记忆键 + 重犯计数
    ), ""),
    "verifier_standards": ((
        ("id", "TEXT PRIMARY KEY"), ("name", "TEXT"), ("param", "TEXT"), ("value", "REAL"),
        ("reason", "TEXT"), ("proposer", "TEXT"), ("independent_reviewer", "TEXT DEFAULT ''"),
        ("cs_reviewer", "TEXT DEFAULT ''"), ("adjudicator", "TEXT DEFAULT ''"),
        ("status", "TEXT DEFAULT 'pending'"), ("created_at", "REAL"), ("decided_at", "REAL"),
    ), ""),
    "escalation_points": ((
        ("id", "TEXT PRIMARY KEY"), ("code", "TEXT"), ("trigger", "TEXT"), ("condition", "TEXT"),
        ("action", "TEXT"), ("severity", "TEXT DEFAULT 'medium'"), ("enabled", "INTEGER DEFAULT 1"),
        ("created_at", "REAL"),
    ), ""),
    "action_logs": ((
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"), ("ts", "REAL"), ("action_type", "TEXT"),
        ("summary", "TEXT"), ("node_ids", "TEXT DEFAULT '[]'"), ("outcome", "TEXT DEFAULT '{}'"),
        ("context", "TEXT DEFAULT '{}'"),
    ), ""),
    "engine_meta": ((("key", "TEXT PRIMARY KEY"), ("value", "TEXT")), ""),
    "gap_history": ((("id", "INTEGER PRIMARY KEY AUTOINCREMENT"), ("ts", "REAL"), ("d_norm", "REAL")), ""),
    "flywheel_reuse": ((
        ("session_id", "TEXT"), ("round", "INTEGER"), ("node_id", "TEXT"), ("ts", "REAL"),
    ), ""),
    "self_snapshots": ((
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"), ("ts", "REAL"), ("identity", "TEXT"),
        ("reason", "TEXT"), ("payload", "TEXT"),
    ), ""),
    "activation_nodes": ((
        ("id", "TEXT PRIMARY KEY"), ("workset", "TEXT NOT NULL"), ("node_id", "TEXT NOT NULL"),
        ("activation", "REAL NOT NULL"), ("source", "TEXT NOT NULL"), ("hop", "INTEGER NOT NULL"),
        ("ts", "REAL NOT NULL"), ("polarity", "INTEGER DEFAULT 1"),
    ), ""),
    # ---- ng 派生文本索引（textindex.py；可由 nodes 完全重建，不导出）----
    "node_terms": ((("term", "TEXT NOT NULL"), ("nkey", "INTEGER NOT NULL"), ("grams", "INTEGER NOT NULL DEFAULT 0")),
                   "PRIMARY KEY (term, nkey)"),
    "term_df": ((("term", "TEXT PRIMARY KEY"), ("df", "INTEGER NOT NULL DEFAULT 0")), ""),
    "feature_df": ((("feat", "TEXT PRIMARY KEY"), ("df", "INTEGER NOT NULL DEFAULT 0")), ""),
    "node_index": ((
        ("nkey", "INTEGER PRIMARY KEY"), ("node_id", "TEXT NOT NULL UNIQUE"), ("terms", "TEXT NOT NULL"),
        ("feats", "TEXT NOT NULL"), ("grams", "INTEGER NOT NULL"),
    ), ""),
    "index_dirty": ((("node_id", "TEXT PRIMARY KEY"),), ""),
    # 派生索引状态：('feats','0') = 新奇特征尚未构建（node_index.feats 全为 '[]'、feature_df 全 0，
    # 首次新奇度查询时批量补建）；无该行 = 已构建（旧库兼容）。('bulk',…) 仅在批量重建事务内存在，
    # 令 trg_index_ins 让位给集合式批量写入（事务结束前删除，其它连接永远看不到）。
    "index_state": ((("key", "TEXT PRIMARY KEY"), ("value", "TEXT")), ""),
}

#: 派生表（索引数据，可由 nodes 重建；导出/导入与完整性校验不涉及）
DERIVED_TABLES = frozenset({"node_terms", "term_df", "feature_df", "node_index", "index_dirty", "index_state"})
#: 表选项（CREATE TABLE … 之后的修饰）
_TABLE_OPTIONS = {"node_terms": " WITHOUT ROWID", "term_df": " WITHOUT ROWID", "feature_df": " WITHOUT ROWID",
                  "index_state": " WITHOUT ROWID"}
#: 引用派生表结构的触发器（派生表重建时一并重建）
_DERIVED_TRIGGERS = ("trg_index_ins", "trg_index_del")

#: 索引名 → (表, 列表达式, 是否唯一)
INDEXES: Dict[str, Tuple[str, str, bool]] = {
    "idx_nodes_layer": ("nodes", "layer", False),
    # 部分索引（见 INDEX_WHERE）：情境层 FIFO 按写入顺序（rowid）淘汰免排序——索引项按 (layer, rowid) 有序（上游 #259）
    "idx_nodes_ctx_seq": ("nodes", "layer", False),
    "idx_edges_source": ("edges", "source_id", False),
    "idx_edges_target": ("edges", "target_id", False),
    "idx_nodes_dedup": ("nodes", "dedup_key", False),
    "idx_nodes_created": ("nodes", "created_at", False),
    "idx_nodes_temporal": ("nodes", "temporal_coordinate", False),
    "idx_skills_name_key": ("skills", "name_key", False),
    "idx_rejected_key": ("rejected_paths", "path_key", False),
    "idx_flywheel_unique": ("flywheel_reuse", "session_id, round, node_id", True),
    "idx_act_ws": ("activation_nodes", "workset", False),
    "idx_index_grams": ("node_index", "grams", False),
}

#: 部分索引的 WHERE（只有字面量写出同一条件的查询才会用到它，不干扰 ``layer=?`` 类查询的计划）
INDEX_WHERE: Dict[str, str] = {"idx_nodes_ctx_seq": "layer = 'context'"}

#: 触发器（纯 SQL，不依赖应用函数——任何连接、包括旧代码的裸写都会维护派生索引）：
#: nodes 增改 ⇒ 记脏；nodes 删 ⇒ 删 node_index；node_index 增删 ⇒ 维护倒排、df、新奇特征计数。
TRIGGERS: Dict[str, str] = {
    "trg_nodes_ins": "AFTER INSERT ON nodes BEGIN "
                     "INSERT OR IGNORE INTO index_dirty(node_id) VALUES (NEW.id); END",
    "trg_nodes_upd": "AFTER UPDATE OF id, content, tags, layer ON nodes BEGIN "
                     "INSERT OR IGNORE INTO index_dirty(node_id) VALUES (NEW.id); "
                     "DELETE FROM node_index WHERE node_id = OLD.id AND OLD.id <> NEW.id; END",
    "trg_nodes_del": "AFTER DELETE ON nodes BEGIN "
                     "DELETE FROM node_index WHERE node_id = OLD.id; "
                     "DELETE FROM index_dirty WHERE node_id = OLD.id; END",
    "trg_index_ins": "AFTER INSERT ON node_index "
                     "WHEN NOT EXISTS (SELECT 1 FROM index_state WHERE key = 'bulk') BEGIN "
                     "INSERT INTO node_terms(term, nkey, grams) SELECT value, NEW.nkey, NEW.grams FROM json_each(NEW.terms); "
                     "INSERT INTO term_df(term, df) SELECT value, 1 FROM json_each(NEW.terms) WHERE 1 "
                     "ON CONFLICT(term) DO UPDATE SET df = df + 1; "
                     "INSERT INTO feature_df(feat, df) SELECT value, 1 FROM json_each(NEW.feats) WHERE 1 "
                     "ON CONFLICT(feat) DO UPDATE SET df = df + 1; END",
    "trg_index_del": "AFTER DELETE ON node_index BEGIN "
                     "DELETE FROM node_terms WHERE nkey = OLD.nkey "
                     "AND term IN (SELECT value FROM json_each(OLD.terms)); "
                     "UPDATE term_df SET df = df - 1 WHERE term IN (SELECT value FROM json_each(OLD.terms)); "
                     "UPDATE feature_df SET df = df - 1 WHERE feat IN (SELECT value FROM json_each(OLD.feats)); END",
}


def columns_of(table: str) -> Tuple[str, ...]:
    """声明中的列名（导出/导入列白名单）。"""
    return tuple(c for c, _ in TABLES[table][0])


def existing_tables(conn: sqlite3.Connection) -> Set[str]:
    """库中实际存在的表名（以 sqlite_master 为准）。"""
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _existing_columns(conn: sqlite3.Connection, table: str) -> Set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def missing_parts(conn: sqlite3.Connection) -> Dict[str, List]:
    """只读比对：返回 {tables:[..], columns:[(t,c,decl)..], indexes:[..]}。"""
    have = existing_tables(conn)
    out: Dict[str, List] = {"tables": [], "columns": [], "indexes": [], "triggers": [], "derived": []}
    for t, (cols, _) in TABLES.items():
        if t not in have:
            out["tables"].append(t)
            continue
        present = _existing_columns(conn, t)
        if t in DERIVED_TABLES:
            if present != {c for c, _ in cols}:
                out["derived"].append(t)          # 派生表结构过期：整体重建（可由 nodes 完全重算）
            continue
        out["columns"].extend((t, c, d) for c, d in cols if c not in present)
    idx = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    out["indexes"] = [i for i in INDEXES if i not in idx]
    trg = {r[0]: r[1] for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")}
    # 缺失或定义过期（旧版本的触发器体）都算缺口：重建触发器并全量重算派生索引
    out["triggers"] = [t for t in TRIGGERS if trg.get(t) != f"CREATE TRIGGER {t} {TRIGGERS[t]}"]
    return out


def _create_sql(table: str) -> str:
    cols, extra = TABLES[table]
    body = ", ".join(f"{c} {d}" for c, d in cols)
    opt = _TABLE_OPTIONS.get(table, "")
    return f"CREATE TABLE IF NOT EXISTS {table} ({body}{', ' + extra if extra else ''}){opt}"


def _alter_decl(decl: str) -> str:
    # SQLite ALTER ADD COLUMN 不接受 PRIMARY KEY/UNIQUE；声明里的追加列都不含这些。
    return decl


def migrate(conn: sqlite3.Connection) -> Dict[str, List]:
    """S2：结构齐全 ⇒ 零写入返回空清单；否则单事务补齐并返回补了什么。

    唯一索引建立前先清理历史重复行（flywheel_reuse 旧库可能已有 #208 的重复计数）。
    """
    gap = missing_parts(conn)
    if not any(gap.values()):
        return gap
    conn.execute("BEGIN IMMEDIATE")
    try:
        if gap["derived"]:
            for name in _DERIVED_TRIGGERS:
                conn.execute(f"DROP TRIGGER IF EXISTS {name}")
            for t in sorted(DERIVED_TABLES - {"index_dirty"}):
                conn.execute(f"DROP TABLE IF EXISTS {t}")
            gap["tables"] = sorted(set(gap["tables"]) | (DERIVED_TABLES - {"index_dirty"}))
            gap["indexes"] = sorted(set(gap["indexes"]) | {n for n, v in INDEXES.items() if v[0] in DERIVED_TABLES})
            gap["triggers"] = sorted(set(gap["triggers"]) | set(_DERIVED_TRIGGERS))
        for t in gap["tables"]:
            conn.execute(_create_sql(t))
        for t, c, d in gap["columns"]:
            conn.execute(f"ALTER TABLE {t} ADD COLUMN {c} {_alter_decl(d)}")
        if "idx_flywheel_unique" in gap["indexes"]:
            conn.execute("DELETE FROM flywheel_reuse WHERE rowid NOT IN (SELECT MIN(rowid) "
                         "FROM flywheel_reuse GROUP BY session_id, round, node_id)")
        for name in gap["indexes"]:
            t, expr, uniq = INDEXES[name]
            where = f" WHERE {INDEX_WHERE[name]}" if name in INDEX_WHERE else ""
            conn.execute(f"CREATE {'UNIQUE ' if uniq else ''}INDEX IF NOT EXISTS {name} ON {t}({expr}){where}")
        for name in gap["triggers"]:
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
            conn.execute(f"CREATE TRIGGER {name} {TRIGGERS[name]}")
        if gap["triggers"]:
            # 触发器缺失/过期期间的写入未进派生索引：全部记脏，由 textindex 在首次读前重建；
            # 新奇特征计数一并清空并标记「未构建」（首次新奇度查询时按需补建）
            for t in ("node_terms", "term_df", "feature_df", "node_index", "index_state"):
                conn.execute(f"DELETE FROM {t}")
            conn.execute("INSERT INTO index_state(key, value) VALUES ('feats', '0')")
            conn.execute("INSERT OR IGNORE INTO index_dirty(node_id) SELECT id FROM nodes")
        conn.execute("INSERT OR REPLACE INTO engine_meta (key, value) VALUES ('_schema_version', ?)",
                     (str(SCHEMA_VERSION),))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return gap


def placeholders(n: int) -> str:
    """生成 n 个 ``?`` 占位符。"""
    return ",".join("?" * n)


def chunks(seq: Sequence, size: int = 400) -> Iterable[Sequence]:
    """按块切分（避免 SQLite 变量上限；根除 #257 2N 占位符爆表）。"""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
