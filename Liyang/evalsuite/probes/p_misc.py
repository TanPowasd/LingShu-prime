"""事务 / 旧库迁移 / 装配安全 / 门面契约类探针。

注：i184 / i92 两个探针用 sqlite3 直接读写**数据库文件**（外部进程视角：能否写入、老库能否打开），
不读取任何实现内部对象，因此对 legacy / ng 同样适用。
"""
import os
import sqlite3
import sys
import tempfile
import time

from ._base import probe, judge
from adapters import Adapter, NA


@probe("i184-tx-lock", 184, "写方法中途异常后连接停在未提交事务里，外部写入 database is locked")
def _(A):
    db = A.tmpdb("tx")
    m = A.open(db)
    a, b, c = (m.add(x, layer="context") for x in ("事务甲", "事务乙", "事务丙"))
    m.add_edge(a, b, "causal", 0.9)
    try:
        m.add_edge(b, c, "causal", float("nan"))
    except ValueError:
        return judge(False, "NaN 边被拒，无中途异常")
    try:
        m.decay(1)
        raised = False
    except Exception:
        raised = True
    o = sqlite3.connect(db, timeout=0.5)
    try:
        o.execute("CREATE TABLE IF NOT EXISTS evs_probe (x)")
        o.execute("INSERT INTO evs_probe VALUES (1)")
        o.commit()
        locked = False
    except sqlite3.OperationalError as ex:
        locked = "locked" in str(ex)
    finally:
        o.close()
    return judge(locked, f"decay 抛异常={raised}，外部写入被锁={locked}")


@probe("i92-old-schema", 92, "老库（缺后加列/表）打开即崩或永远补不上")
def _(A):
    db = A.tmpdb("old")
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE nodes (id TEXT PRIMARY KEY, content TEXT, modality TEXT,
      spatial_coordinates TEXT, temporal_coordinate REAL, condition_space TEXT, importance REAL,
      confidence REAL, layer TEXT, access_count INTEGER DEFAULT 0, last_access REAL,
      created_at REAL, tags TEXT)""")
    c.execute("""CREATE TABLE edges (id TEXT PRIMARY KEY, source_id TEXT, target_id TEXT,
      relation_type TEXT, condition_space TEXT, confidence REAL, weight REAL,
      verified INTEGER DEFAULT 0, created_at REAL, last_verified REAL)""")
    c.execute("CREATE TABLE engine_meta (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE gap_history (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, d_norm REAL)")
    c.execute("INSERT INTO engine_meta VALUES ('_schema_version', '1')")
    c.commit()
    c.close()
    try:
        m = A.open(db)
        n = m.add("老库上的新记忆")
        m.blindspot("B1", "盲区")
        ok = m.get(n) is not None
    except NA:
        raise
    except Exception as ex:
        return judge(True, f"{type(ex).__name__}: {str(ex)[:60]}")
    return judge(not ok, f"老库可用={ok}")


@probe("i156-cwd-hijack", 156, "构造引擎时按裸模块名从 sys.path 导入：cwd 里同名 .py 被执行", raw=True)
def _(impl):
    d = tempfile.mkdtemp(prefix="hijack_")
    marker = os.path.join(d, "PWNED")
    for name in ("body", "vision", "attention_policy", "prediction_engine", "lifecycle_engine", "flywheel_engine",
                 "self_cognition_engine", "semantic_space", "entity_registry", "cognitive_orchestrator",
                 "blindspot_learning_loop", "pattern_separation", "scene_reconstruction"):
        with open(os.path.join(d, name + ".py"), "w") as f:
            f.write(f"open({marker!r}, 'a').write({name!r} + '\\n')\n")
    sys.path.insert(0, d)
    os.chdir(d)
    A = Adapter(impl)
    m = A.open()
    m.add("触发惰性组件")
    try:
        m.self_check()
    except Exception:
        pass
    hit = open(marker).read().split() if os.path.exists(marker) else []
    return judge(bool(hit), f"cwd 中被执行的同名模块={hit}")


@probe("i243-facade-init", 243, "world 门面声明 init 动作但没有 init 分支")
def _(A):
    m = A.open()
    bad = []
    for name in ("spacetime_consistency", "world_model", "world_learner", "curiosity_explorer", "seven_layer_loop"):
        try:
            r = m.facade(name, "init", {"size": 40})
        except NA:
            raise
        except Exception as ex:
            bad.append(f"{name}:{type(ex).__name__}")
            continue
        if r.get("status") != "ok":
            bad.append(name)
    return judge(bool(bad), f"init 失败的门面={bad}")


@probe("i55-world-degenerate", 55, "world_model run(0) 等退化输入崩溃")
def _(A):
    m = A.open()
    try:
        m.facade("world_model", "run", {"n": 0})
        r2 = m.facade("world_model", "run", {"ticks": 0})
    except NA:
        raise
    except Exception as ex:
        return judge(True, f"{type(ex).__name__}: {str(ex)[:60]}")
    return judge(False, f"status={r2.get('status')}")
