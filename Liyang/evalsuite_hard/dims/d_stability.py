"""H-STB 长期稳定性：同一文件库上 5 段 × 2 万次混合操作（共 10 万次，每段重开引擎），每段后检查不变量。

操作配比（固定）：写入 38%（其中 3% 走去重路径）、读 17%、召回 7%、连边 15%、改重要度 10%、删除 5%、
自我更新 5%、保护 1%、衰减 2%（单轮）。
不变量：① 全部节点 importance/confidence 有限且 ∈[0,1]；② verify_integrity 通过；③ 受保护节点全部仍在；
④ 删除的节点不复现；⑤ 哨兵事实（第 0 段首条写入）召回在前 10；⑥ 自我层历史 ≤ 1000；⑦ 无非 Value/Type 异常。
另记写入延迟漂移（末段中位 / 首段中位）。
"""
import json
import os
import random
import statistics
import time

STATE_DIR = os.environ.get("HARD_STATE_DIR", "/tmp/hard_state")


def run(A, seed, chunk=0, ops=20000, tag="x"):
    os.makedirs(STATE_DIR, exist_ok=True)
    db = os.path.join(STATE_DIR, f"stab_{tag}_{A.impl}_{seed}.db")
    stf = db + ".json"
    if chunk == 0:
        for f in (db, stf, db + "-wal", db + "-shm"):
            if os.path.exists(f):
                os.remove(f)
        st = {"live": [], "deleted": [], "protected": [], "sentinel": None, "lat": {}}
    else:
        st = json.load(open(stf))
    rnd = random.Random(seed * 1000003 + chunk)
    m = A.open(db)
    live, deleted, prot = st["live"], set(st["deleted"]), st["protected"]
    if st["sentinel"] is None:
        st["sentinel"] = m.add("哨兵事实：灵枢稳定性测试的暗号是青松白鹤七七九", importance=0.9, skip_dedup=True)
        m.protect(st["sentinel"])
        prot.append(st["sentinel"])
    errs, lat_add = {}, []
    for k in range(ops):
        x = rnd.random()
        try:
            if x < 0.38:
                t0 = time.perf_counter()
                nid = m.add(f"长期运行{chunk}-{k}：事件{rnd.randrange(10**6)}的状态{rnd.choice('甲乙丙丁')}",
                            importance=round(rnd.random(), 3), skip_dedup=x >= 0.03)
                lat_add.append(time.perf_counter() - t0)
                if nid not in live:
                    live.append(nid)
            elif x < 0.55 and live:
                m.get(rnd.choice(live))
            elif x < 0.62:
                m.recall(f"事件{rnd.randrange(10**6)}的状态", limit=5)
            elif x < 0.77 and len(live) > 2:
                a, b = rnd.sample(live[-2000:], 2)
                m.add_edge(a, b, rnd.choice(["causal", "similar"]), round(rnd.random(), 3))
            elif x < 0.87 and live:
                m.set_importance_delta(rnd.choice(live), rnd.uniform(-0.3, 0.3))
            elif x < 0.92 and len(live) > 100:
                v = live.pop(rnd.randrange(len(live) - 50))
                if v not in prot:
                    m.delete(v)
                    deleted.add(v)
                else:
                    live.append(v)
            elif x < 0.97:
                m.update_self({"identity": f"长期体{chunk}-{k}"})
            elif x < 0.98 and live:
                v = rnd.choice(live)
                m.protect(v)
                prot.append(v)
            else:
                m.decay(1)
        except (ValueError, TypeError, KeyError):
            pass
        except Exception as ex:
            n = type(ex).__name__
            errs[n] = errs.get(n, 0) + 1
    inv = {}
    try:
        nodes = m.all_nodes(limit=10**7)
        inv["values_finite_in_range"] = all(
            isinstance(n["importance"], (int, float)) and 0 <= n["importance"] <= 1 and
            isinstance(n["confidence"], (int, float)) and 0 <= n["confidence"] <= 1 for n in nodes)
        ids = {n["id"] for n in nodes}
        inv["protected_present"] = all(p in ids for p in prot)
        inv["deleted_absent"] = not (deleted & ids)
    except Exception as ex:
        inv["values_finite_in_range"] = inv["protected_present"] = inv["deleted_absent"] = False
        errs["scan:" + type(ex).__name__] = 1
    try:
        inv["integrity"] = bool(m.integrity().get("integrity_ok"))
    except Exception:
        inv["integrity"] = False
    try:
        inv["sentinel_recalled"] = any(n["id"] == st["sentinel"] for n, _ in m.recall("灵枢稳定性测试的暗号", limit=10))
    except Exception:
        inv["sentinel_recalled"] = False
    try:
        inv["self_history_bounded"] = m.self_state()["history_len"] <= 1000
    except Exception:
        inv["self_history_bounded"] = False
    inv["no_unexpected_exceptions"] = not errs
    st["lat"][str(chunk)] = statistics.median(lat_add) * 1000 if lat_add else None
    st["live"], st["deleted"], st["protected"] = live, sorted(deleted), prot
    try:
        m.close()
    except Exception:
        pass
    json.dump(st, open(stf, "w"))
    return {"chunk": chunk, "invariants": inv, "errors": errs, "add_p50_ms": st["lat"][str(chunk)],
            "lat_by_chunk": st["lat"], "n_live": len(live), "db_mb": round(os.path.getsize(db) / 2 ** 20, 2)}
