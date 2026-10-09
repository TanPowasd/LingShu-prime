"""H-ROB2（hard-rules-v2 新增子项，v1 的 d_robust.py 不动）：

  crash_maint  维护周期途中 SIGKILL：预灌 5000 条 + 2000 因果边后子进程循环 run_maintenance_cycle / decay / 写入，
               分别在进入循环后 0.4s、1.3s、2.5s 处 SIGKILL（三次独立崩溃，第三次在第二次恢复后的同一库上继续），
               每次检查：已确认写入全部存在、预灌节点抽样逐字可读、完整性、可继续使用。
  crash_export 导出途中 SIGKILL：父进程预灌 20000 条 + 边并关闭，子进程反复 export_all 到同一路径，于 0.6s / 1.7s 处 SIGKILL；
               检查：原库完整性与节点数不变、可用、恢复后重新导出→新库导入等价（节点数 + 抽样逐字）；
               被打断的导出文件：导入时干净拒绝（ValueError/TypeError/JSON 错误，目标库仍可用且无半截写入）
               或导入成功且导入的每个节点内容都与原库逐字一致（原子写入的上一份完整导出）——两者都算通过。
  crash200k    200k 库的崩溃恢复：库由 robust2 prep 作业分段灌好（20 万条，HARD_STATE_DIR），子进程在其上
               写入 + 连边 + 每 50 条一次 decay，2.0s 后 SIGKILL；检查已确认写入、预灌抽样、20 万条仍在、完整性、可用。
               记 reopen_ms（重开 + 首次召回）作备注。prep 未灌满 → 本组全部记失败（按规模给分的口径只用于稳定性维）。
  import_read  导入期间的并发读：目标库已有 2000 条，主线程 import_all 一份 20000 条的导出，3 个读线程同时
               get（预有节点逐字）/ recall / count；检查：导入无异常、读线程无异常、读到的预有节点内容全部正确、
               读线程确实在导入期间完成了读（>0 次）、导入后计数 = 22000、抽样逐字、完整性。
判据口径与 v1 相同：每个检查 pass/fail；组内通过率即该子项分（score.py v2）。
"""
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import threading
import time

from dims.d_robust import _usable

RAW = False
STATE_DIR = os.environ.get("HARD_STATE_DIR", "/tmp/hard_state")
N_BIG = 200000

CHILD = r'''
import sys, os, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.environ["HARD_DIR"])
from hadapt import Adapter
A = Adapter(sys.argv[1]); m = A.open(sys.argv[2]); mode = sys.argv[3]
log = open(sys.argv[4], "a", encoding="utf-8")
log.write("READY\n"); log.flush()
if mode == "maint":
    k = 0
    while True:
        m.maintenance()
        m.decay(1, 0.3)
        for _ in range(5):
            nid = m.add(f"维护崩溃写入 {time.time_ns()} {k}", skip_dedup=True)
            log.write(f"C {k} {nid}\n"); log.flush(); k += 1
elif mode == "export":
    k = 0
    while True:
        m.export(sys.argv[5])
        log.write(f"E {k}\n"); log.flush(); k += 1
elif mode == "big":
    prev = None
    for i in range(10**6):
        nid = m.add(f"大库崩溃写入{i} {i*7919}", skip_dedup=True)
        if prev is not None:
            m.add_edge(prev, nid, "causal", 0.5)
        if i % 50 == 0:
            m.decay(1)
        prev = nid
        log.write(f"C {i} {nid}\n"); log.flush()
'''


def _spawn(A, db, mode, logp, extra=()):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, HARD_DIR=here)
    return subprocess.Popen([sys.executable, "-c", CHILD, A.impl, db, mode, logp, *extra],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)


def _wait_ready(logp, t_max=60):
    t0 = time.time()
    while time.time() - t0 < t_max:
        if os.path.exists(logp) and "READY" in open(logp, encoding="utf-8").read():
            return True
        time.sleep(0.05)
    return False


def _committed(logp):
    txt = open(logp, encoding="utf-8").read() if os.path.exists(logp) else ""
    return [ln.split() for ln in txt.splitlines() if ln.startswith("C ") and len(ln.split()) == 3]


def _sample_ok(m, pairs):
    try:
        return all((m.get(nid) or {}).get("content") == c for nid, c in pairs)
    except Exception:
        return False


def case_crash_maint(A, rnd):
    out = {}
    db = A.tmpdb("crash_maint")
    m = A.open(db)
    ids = []
    for i in range(5000):
        c = f"维护预灌{i} 状态{(i * 7919) % 100003}"
        ids.append((m.add(c, importance=round(rnd.random(), 3), skip_dedup=True), c))
    for _ in range(2000):
        a, b = sorted(rnd.sample(range(5000), 2))
        m.add_edge(ids[a][0], ids[b][0], "causal", 0.6)
    try:
        m.close()
    except Exception:
        pass
    sample = rnd.sample(ids, 200)
    seen_committed = []
    for k, delay in enumerate([0.4, 1.3, 2.5]):
        logp = db + f".log{k}"
        p = _spawn(A, db, "maint", logp)
        ready = _wait_ready(logp)
        time.sleep(delay)
        os.kill(p.pid, signal.SIGKILL)
        p.wait()
        tag = f"crash_maint{k}"
        done = _committed(logp)
        seen_committed += [(nid, None) for _, _, nid in done]
        out[f"_n_{tag}"] = len(done)
        out[f"{tag}:child_ready"] = ready
        try:
            mm = A.open(db)
            out[f"{tag}:committed_present"] = all(
                str((mm.get(nid) or {}).get("content", "")).startswith("维护崩溃写入") for nid, _ in seen_committed)
            # 预灌节点：维护周期可改重要度/置信度、可归档，但不得丢失或改写内容
            out[f"{tag}:prefill_sample_verbatim"] = _sample_ok(mm, sample)
            try:
                out[f"{tag}:integrity"] = bool(mm.integrity().get("integrity_ok", False))
            except Exception:
                out[f"{tag}:integrity"] = False
            if k == 2:
                out[f"{tag}:usable"] = _usable(mm)
            try:
                mm.close()
            except Exception:
                pass
        except Exception as ex:
            for c in ("committed_present", "prefill_sample_verbatim", "integrity"):
                out[f"{tag}:{c}"] = False
            out[f"_{tag}_err"] = f"{type(ex).__name__}:{str(ex)[:100]}"
    return out


def case_crash_export(A, rnd):
    out = {}
    db = A.tmpdb("crash_exp")
    m = A.open(db)
    ids = []
    for i in range(20000):
        c = f"导出预灌{i} 值{(i * 7919) % 100003}"
        ids.append((m.add(c, importance=round(rnd.random(), 3), skip_dedup=True), c))
    for _ in range(3000):
        a, b = sorted(rnd.sample(range(20000), 2))
        m.add_edge(ids[a][0], ids[b][0], "causal", 0.6)
    n0 = m.count("knowledge")
    try:
        m.close()
    except Exception:
        pass
    content_of = dict(ids)
    sample = rnd.sample(ids, 300)
    for k, delay in enumerate([0.6, 1.7]):
        tag = f"crash_export{k}"
        logp = db + f".elog{k}"
        path = A.tmpfile(f"crash_export_{k}_{time.time_ns()}.json")
        p = _spawn(A, db, "export", logp, (path,))
        _wait_ready(logp)
        time.sleep(delay)
        os.kill(p.pid, signal.SIGKILL)
        p.wait()
        txt = open(logp, encoding="utf-8").read() if os.path.exists(logp) else ""
        out[f"_n_{tag}_exports_done"] = txt.count("\nE ") + txt.startswith("E ")
        try:
            mm = A.open(db)
            out[f"{tag}:db_integrity"] = bool(mm.integrity().get("integrity_ok", False))
            out[f"{tag}:db_count_unchanged"] = mm.count("knowledge") == n0
            out[f"{tag}:db_sample_verbatim"] = _sample_ok(mm, sample)
            out[f"{tag}:usable"] = _usable(mm)
            n0 = mm.count("knowledge")             # 可用性探针会新写一条：下一轮以探针后的计数为基准
            # 恢复后重新导出 → 新库导入等价
            p2 = A.tmpfile(f"crash_export_re_{k}_{time.time_ns()}.json")
            try:
                mm.export(p2)
                mi = A.open(A.tmpdb("crash_exp_re"))
                mi.import_(p2)
                out[f"{tag}:reexport_import_equal"] = mi.count("knowledge") >= n0 and _sample_ok(mi, sample)
            except Exception as ex:
                out[f"{tag}:reexport_import_equal"] = False
                out[f"_{tag}_reexport_err"] = f"{type(ex).__name__}:{str(ex)[:100]}"
            try:
                mm.close()
            except Exception:
                pass
        except Exception as ex:
            for c in ("db_integrity", "db_count_unchanged", "db_sample_verbatim", "usable", "reexport_import_equal"):
                out[f"{tag}:{c}"] = False
            out[f"_{tag}_err"] = f"{type(ex).__name__}:{str(ex)[:100]}"
        # 被打断的导出文件
        ok = True
        if os.path.exists(path):
            mt = A.open(A.tmpdb("crash_exp_partial"))
            try:
                mt.import_(path)
                nodes = [n for n in mt.all_nodes(limit=10 ** 6) if n["layer"] == "knowledge"]
                byc = set(content_of.values())
                ok = all(n["content"] in byc for n in nodes if str(n["content"]).startswith("导出预灌"))
                out[f"_{tag}_partial"] = f"accepted:{len(nodes)}"
            except (ValueError, TypeError) as ex:
                try:
                    ok = mt.count("knowledge") == 0 and _usable(mt)
                except Exception:
                    ok = False
                out[f"_{tag}_partial"] = f"rejected:{type(ex).__name__}"
            except Exception as ex:
                ok = False
                out[f"_{tag}_partial"] = f"error:{type(ex).__name__}:{str(ex)[:80]}"
        else:
            out[f"_{tag}_partial"] = "no_file"
        out[f"{tag}:partial_file_safe"] = ok
    return out


def _big_db(A, seed):
    return os.path.join(STATE_DIR, f"big200k_{A.impl}_{seed}.db")


def prep(A, seed, chunk=0, deadline=80):
    """分段灌 20 万条（每段至多 deadline 秒），状态记在同名 .json；返回 {count, done}。"""
    os.makedirs(STATE_DIR, exist_ok=True)
    db = _big_db(A, seed)
    stf = db + ".json"
    if chunk == 0:
        for f in (db, stf, db + "-wal", db + "-shm"):
            if os.path.exists(f):
                os.remove(f)
        st = {"count": 0, "sample": []}
    else:
        st = json.load(open(stf))
    t0 = time.time()
    if st["count"] < N_BIG:
        m = A.open(db)
        rnd = random.Random(seed * 31 + st["count"])
        words = ["服务器", "数据库", "备份", "用户", "配置", "端口", "证书", "日志", "预算", "会议", "合同", "版本"]
        i = st["count"]
        while i < N_BIG and time.time() - t0 < deadline:
            c = f"{rnd.choice(words)}{rnd.choice(words)}大库记录{i}：状态{(i * 7919) % 100003}"
            nid = m.add(c, importance=round(rnd.random(), 3), skip_dedup=True)
            if i % 1000 == 7:
                st["sample"].append([nid, c])
            i += 1
        st["count"] = i
        try:
            m.close()
        except Exception:
            pass
        json.dump(st, open(stf, "w"))
    return {"count": st["count"], "done": st["count"] >= N_BIG, "sec": round(time.time() - t0, 1)}


def case_crash200k(A, rnd, seed):
    out = {}
    db = _big_db(A, seed)
    stf = db + ".json"
    st = json.load(open(stf)) if os.path.exists(stf) else {"count": 0, "sample": []}
    out["_prep_count"] = st["count"]
    keys = ("prep_complete", "committed_present", "prefill_sample_verbatim", "prefill_count", "integrity", "usable")
    if st["count"] < N_BIG:
        for c in keys:
            out[f"crash200k:{c}"] = False
        return out
    out["crash200k:prep_complete"] = True
    logp = db + f".clog{time.time_ns()}"
    p = _spawn(A, db, "big", logp)
    _wait_ready(logp, 90)
    time.sleep(2.0)
    os.kill(p.pid, signal.SIGKILL)
    p.wait()
    done = _committed(logp)
    out["_n_committed"] = len(done)
    try:
        t0 = time.perf_counter()
        m = A.open(db)
        m.recall("大库记录 状态", limit=5)
        out["_reopen_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        out["crash200k:committed_present"] = len(done) > 0 and all(
            str((m.get(nid) or {}).get("content", "")).startswith(f"大库崩溃写入{i}") for _, i, nid in done)
        out["crash200k:prefill_sample_verbatim"] = _sample_ok(m, [tuple(x) for x in st["sample"]])
        out["crash200k:prefill_count"] = m.count("knowledge") >= N_BIG
        t0 = time.perf_counter()
        try:
            out["crash200k:integrity"] = bool(m.integrity().get("integrity_ok", False))
        except Exception:
            out["crash200k:integrity"] = False
        out["_integrity_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        out["crash200k:usable"] = _usable(m)
    except Exception as ex:
        for c in keys[1:]:
            out.setdefault(f"crash200k:{c}", False)
        out["_crash200k_err"] = f"{type(ex).__name__}:{str(ex)[:100]}"
    return out


def case_import_read(A, rnd):
    out = {}
    src = A.open(A.tmpdb("ir_src"))
    for i in range(20000):
        src.add(f"导入源{i} 值{(i * 104729) % 1000003}", importance=round(rnd.random(), 3), skip_dedup=True)
    path = A.tmpfile(f"ir_{time.time_ns()}.json")
    src.export(path)
    m = A.open(A.tmpdb("ir_dst"))
    pre = []
    for i in range(2000):
        c = f"预有节点{i} 标记{(i * 31) % 997}"
        pre.append((m.add(c, skip_dedup=True), c))
    errs, bad, reads = [], [], [0, 0]       # reads: [导入期间完成的读次数, 总读次数]
    state = {"importing": True}

    def reader(t):
        r = random.Random(t)
        while state["importing"]:
            try:
                nid, c = r.choice(pre)
                g = m.get(nid)
                if (g or {}).get("content") != c:
                    bad.append(nid)
                if t == 0:
                    m.recall(f"预有节点{r.randrange(2000)}", limit=5)
                elif t == 1:
                    m.count("knowledge")
                if state["importing"]:
                    reads[0] += 1
                reads[1] += 1
            except Exception as ex:
                errs.append(f"{type(ex).__name__}:{str(ex)[:60]}")
                time.sleep(0.01)
            time.sleep(0)

    ths = [threading.Thread(target=reader, args=(t,)) for t in range(3)]
    for t in ths:
        t.start()
    imp_err = None
    try:
        m.import_(path)
    except Exception as ex:
        imp_err = f"{type(ex).__name__}:{str(ex)[:100]}"
    state["importing"] = False
    for t in ths:
        t.join(30)
    out["import_read:import_ok"] = imp_err is None
    out["import_read:readers_no_errors"] = not errs
    out["import_read:reads_consistent"] = not bad
    out["import_read:reads_during_import"] = reads[0] > 0
    try:
        out["import_read:final_count"] = m.count("knowledge") == 22000
        out["import_read:pre_sample_verbatim"] = _sample_ok(m, rnd.sample(pre, 200))
        out["import_read:integrity"] = bool(m.integrity().get("integrity_ok", False))
    except Exception:
        out["import_read:final_count"] = out["import_read:pre_sample_verbatim"] = out["import_read:integrity"] = False
    out["_import_read"] = {"reads_during": reads[0], "reads_total": reads[1], "errs": errs[:3], "bad": len(bad), "imp_err": imp_err}
    return out


ITEMS = ("crash_maint", "crash_export", "crash200k", "import_read")


def run(A, seed, only=None, prep_chunk=None):
    if prep_chunk is not None:
        return prep(A, seed, chunk=prep_chunk)
    rnd = random.Random(seed * 977 + 3)
    res = {}
    for name in ITEMS:
        if only and name not in only:
            continue
        try:
            r = case_crash200k(A, rnd, seed) if name == "crash200k" else globals()[f"case_{name}"](A, rnd)
        except Exception as ex:
            r = {f"{name}:case_crashed": False, f"_{name}_err": f"{type(ex).__name__}:{str(ex)[:120]}"}
        res.update(r)
    checks = {k: bool(v) for k, v in res.items() if not k.startswith("_")}
    return {"checks": checks, "passed": sum(checks.values()), "total": len(checks),
            "notes": {k: v for k, v in res.items() if k.startswith("_")}}
