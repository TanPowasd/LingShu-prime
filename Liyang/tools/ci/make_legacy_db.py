# -*- coding: utf-8 -*-
"""生成「旧版写出的库」测试夹具（stab-r3 #4）。

用法（PYTHONPATH 指向旧版代码根，例如 rel-v1.10 = wt-rel 5782f4f4 的 ``git archive``）：
    PYTHONPATH=<旧版根> python tools/ci/make_legacy_db.py <out.sqlite> <manifest.json> <label>

写入一组确定的内容（感知 / 情境 / 共享层 / 边 / 保护 / 盲区 / 自我模型修改），把 WAL 检查点合并回主文件并切回
DELETE 日志模式（夹具是单个文件），清单记下每条内容与计数，供 tests_ng/test_db_safety.py 用当前代码重开核对。
"""
import json
import os
import sqlite3
import sys

out, man, label = sys.argv[1], sys.argv[2], sys.argv[3]
if os.path.exists(out):
    os.remove(out)
from lingshu_ng.compat import SpacetimeMemoryEngine, EdgeType, MemoryLayer  # noqa: E402

e = SpacetimeMemoryEngine(out)
texts = [f"旧库条目{i:02d}：项目代号青鸾的第{i}次周会纪要，负责人王{i % 5}，结论编号K{i * 7}" for i in range(20)]
texts += [f"legacy entry {i}: the quarterly review for project Heron, owner Lee{i % 3}, item Z{i * 11}" for i in range(10)]
ids = []
for t in texts:
    n = e.add_perception(t)
    ids.append(n if isinstance(n, str) else n.id)
ctx = e.ng.add_context("旧库情境：本周优先处理合同续签", importance=0.5)
ctx_id = ctx if isinstance(ctx, str) else getattr(ctx, "node_id", None) or ctx.id
e.ng.link(ids[0], ids[1], EdgeType.CAUSAL)
e.ng.link(ids[2], ids[3], EdgeType.CAUSAL)
e.ng.protect(ids[4], "夹具：不可遗忘")
e.ng.register_blindspot("FIX01", "夹具盲区", "low")
e.ng.self_store.update({"current_goal": "夹具目标：验证旧库升级"}, reason="fixture")
e.close()
c = sqlite3.connect(out)
c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
c.execute("PRAGMA journal_mode=DELETE")
c.execute("VACUUM")
counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("nodes", "edges")}
ver = c.execute("SELECT value FROM engine_meta WHERE key='_schema_version'").fetchone()
c.close()
for suf in ("-wal", "-shm"):
    if os.path.exists(out + suf):
        os.remove(out + suf)
json.dump({"label": label, "texts": texts, "ids": ids, "ctx_id": ctx_id, "protected": ids[4],
           "edges": [[ids[0], ids[1]], [ids[2], ids[3]]], "counts": counts,
           "schema_version": ver[0] if ver else None, "goal": "夹具目标：验证旧库升级"},
          open(man, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(label, counts, "schema", ver[0] if ver else None, os.path.getsize(out), "bytes")
