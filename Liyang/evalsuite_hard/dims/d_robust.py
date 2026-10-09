"""H-ROB 对抗与边界：Unicode、空值、超长文本、数值越界、SQL/LIKE 元字符、并发写、崩溃恢复（SIGKILL 后重开）、
持久化往返、导出导入往返、反复开关。每个用例 pass/fail，分数 = 通过率。

判据口径（对两种实现相同）：
- 「干净拒绝」= 抛 ValueError / TypeError；「接受」= 写入后能按 id 原样读回且引擎仍可用（随后的 recall/decay/self_check 不崩）。
  二者都算通过；其他异常、读回失真、拒绝后引擎坏掉 = 失败。
- 数值（importance）：拒绝，或读回值有限且在 [0,1]。
"""
import json
import math
import os
import signal
import subprocess
import sys
import threading
import time

RAW = False

UNICODE = {
    "emoji_zwj": "家庭👨‍👩‍👧‍👦与旗帜🏳️‍🌈的记录",
    "combining": "e\u0301 a\u0308 n\u0303 组合字符",
    "rtl": "مرحبا بالعالم 混排 שלום",
    "cjk_extb": "𠀀𠀁𠮷𡈽 扩展B区",
    "tibetan_devanagari": "བོད་ཡིག हिन्दी",
    "zero_width": "零\u200b宽\u200c字\u200d符\ufeff",
    "control": "响铃\x07退格\x08换页\x0c",
    "nul": "空字符\x00之后",
    "math_bold": "𝐀𝐁𝐂 𝟏𝟐𝟑",
    "lone_surrogate": "孤立代理\ud800项",
    "newlines_tabs": "多行\r\n文本\t制表\n结尾",
    "quotes_backslash": "引号'\"\\反斜杠\\\\",
}
SQLISH = ["100%_done' OR 1=1 --", "a%b_c\\d", "'); DROP TABLE nodes; --", "[x]*?(y)+^$|"]


def _accepted_or_clean(fn):
    """→ ('ok', val) | ('rejected', None) | ('error', msg)"""
    try:
        return "ok", fn()
    except (ValueError, TypeError) as ex:
        return "rejected", str(ex)[:60]
    except Exception as ex:
        return "error", f"{type(ex).__name__}:{str(ex)[:60]}"


def _usable(m):
    try:
        m.recall("健康检查", limit=3)
        m.decay(1)
        m.self_check()
        nid = m.add("可用性探针 记录", skip_dedup=True)
        return m.get(nid) is not None
    except Exception:
        return False


def case_unicode(A):
    out = {}
    m = A.open(A.tmpdb("uni"))
    for k, s in UNICODE.items():
        st, nid = _accepted_or_clean(lambda: m.add(s, skip_dedup=True))
        if st == "ok":
            try:
                got = m.get(nid)
                ok = got is not None and got["content"] == s
                if ok:   # 原样检索：用整串查，应在前 10
                    res = m.recall(s, limit=10)
                    ok = any(n["id"] == nid for n, _ in res)
            except Exception:
                ok = False
            out[f"unicode:{k}"] = ok
        else:
            out[f"unicode:{k}"] = st == "rejected"
    out["unicode:engine_usable_after"] = _usable(m)
    return out


def case_empty(A):
    out = {}
    m = A.open(A.tmpdb("empty"))
    for k, v in {"empty": "", "spaces": "   \t ", "none": None, "int": 12345}.items():
        st, nid = _accepted_or_clean(lambda: m.add(v, skip_dedup=True))
        if st == "ok":
            try:
                g = m.get(nid)
                ok = g is not None and g["content"] == v
            except Exception:
                ok = False
        else:
            ok = st == "rejected"
        out[f"empty:{k}"] = ok
    for k, q in {"recall_empty": "", "recall_spaces": "   ", "recall_punct": "？！。，"}.items():
        st, r = _accepted_or_clean(lambda: m.recall(q, limit=5))
        out[f"empty:{k}"] = st == "rejected" or (st == "ok" and len(r) == 0)
    out["empty:engine_usable_after"] = _usable(m)
    return out


def case_long(A):
    out = {}
    m = A.open(A.tmpdb("long"))
    filler = "灵枢长文本压力测试。" * 100000          # ≈1M 字符
    s = filler[:500000] + "独一无二的锚词鸮鹦鹉螺" + filler[500000:]
    t0 = time.perf_counter()
    st, nid = _accepted_or_clean(lambda: m.add(s, skip_dedup=True))
    out["long:add_s<2"] = st == "rejected" or (st == "ok" and time.perf_counter() - t0 < 2.0)
    if st == "ok":
        g = m.get(nid)
        out["long:roundtrip"] = g is not None and g["content"] == s
        t0 = time.perf_counter()
        try:
            res = m.recall("独一无二的锚词鸮鹦鹉螺", limit=5)
            out["long:findable"] = any(n["id"] == nid for n, _ in res)
        except Exception:
            out["long:findable"] = False
        out["long:recall_s<1"] = time.perf_counter() - t0 < 1.0
    else:
        out["long:roundtrip"] = out["long:findable"] = out["long:recall_s<1"] = True
    # 2000 个不同长文本中的定位（存储面逐字可定位）
    ids = []
    for i in range(300):
        ids.append(m.add(f"段落{i}：" + "背景噪声文本" * 200 + f" 唯一标记XQ{i:04d}ZZ " + "尾部填充" * 100, skip_dedup=True))
    hit = 0
    for i in range(0, 300, 10):
        try:
            res = m.recall(f"唯一标记XQ{i:04d}ZZ", limit=3)
            hit += any(n["id"] == ids[i] for n, _ in res)
        except Exception:
            pass
    out["long:verbatim_locate_30"] = hit == 30
    out["long:verbatim_locate_ratio>=0.9"] = hit >= 27
    return out


def case_numeric(A):
    out = {}
    m = A.open(A.tmpdb("num"))
    for k, v in {"nan": float("nan"), "inf": float("inf"), "-inf": float("-inf"), "neg": -1.0,
                 "huge": 1e6, "str": "0.5"}.items():
        st, nid = _accepted_or_clean(lambda: m.add(f"数值边界 {k}", importance=v, skip_dedup=True))
        if st == "ok":
            try:
                imp = m.get(nid)["importance"]
                ok = isinstance(imp, (int, float)) and math.isfinite(imp) and 0.0 <= imp <= 1.0
            except Exception:
                ok = False
        else:
            ok = st == "rejected"
        out[f"num:importance_{k}"] = ok
    out["num:engine_usable_after"] = _usable(m)
    return out


def case_sqlish(A):
    out = {}
    m = A.open(A.tmpdb("sql"))
    for i, s in enumerate(SQLISH):
        st, nid = _accepted_or_clean(lambda: m.add(s, skip_dedup=True))
        out[f"sql:content_{i}"] = st == "ok" and m.get(nid)["content"] == s
    a = m.add("车辆一号", tags=["ent:car_1"], skip_dedup=True)
    b = m.add("车辆十二号", tags=["ent:car_12"], skip_dedup=True)
    c = m.add("车辆X", tags=["ent:carX1"], skip_dedup=True)
    try:
        got = {n["id"] for n in m.by_tag("ent:car_1")}
        out["sql:tag_exact"] = got == {a}
    except Exception:
        out["sql:tag_exact"] = False
    try:
        out["sql:table_alive"] = m.count("knowledge") >= 3
    except Exception:
        out["sql:table_alive"] = False
    return out


def case_threads(A):
    out = {}
    m = A.open(A.tmpdb("thr"))
    errs, ids, lock = [], [], threading.Lock()

    def writer(t):
        for i in range(250):
            try:
                nid = m.add(f"线程{t}写入第{i}条 独立内容{t * 1000 + i}", skip_dedup=True)
                with lock:
                    ids.append((nid, f"线程{t}写入第{i}条 独立内容{t * 1000 + i}"))
            except Exception as ex:
                with lock:
                    errs.append(type(ex).__name__)

    def reader():
        for i in range(150):
            try:
                m.recall(f"线程{i % 8}写入", limit=5)
            except Exception as ex:
                with lock:
                    errs.append("R" + type(ex).__name__)

    ths = [threading.Thread(target=writer, args=(t,)) for t in range(8)] + [threading.Thread(target=reader) for _ in range(2)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(60)
    out["threads:no_exceptions"] = not errs
    try:
        out["threads:all_ids_distinct"] = len({i for i, _ in ids}) == 2000 and len(ids) == 2000
        out["threads:all_readable"] = all((m.get(i) or {}).get("content") == c for i, c in ids)
    except Exception:
        out["threads:all_ids_distinct"] = out["threads:all_readable"] = False
    try:
        out["threads:count_exact"] = m.count("knowledge") == 2000
    except Exception:
        out["threads:count_exact"] = False
    try:
        m2 = m.reopen()
        out["threads:persisted"] = m2.count("knowledge") == 2000
    except Exception:
        out["threads:persisted"] = False
    out["_thread_errors"] = errs[:5]
    return out


CHILD = r'''
import sys, os, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.environ["HARD_DIR"])
from hadapt import Adapter
A = Adapter(sys.argv[1]); m = A.open(sys.argv[2]); mode = sys.argv[3]
log = open(sys.argv[4], "w", encoding="utf-8")
if mode == "bulk":
    for i in range(20000):
        m.add(f"预灌第{i}条 {i}", skip_dedup=True)
    log.write("READY\n"); log.flush()
    while True:
        m.decay(1, 0.3)
        m.maintenance() if hasattr(m.e, "run_maintenance_cycle") else None
        nid = m.add(f"维护中写入 {time.time_ns()}", skip_dedup=True)
        log.write(f"C -1 {nid}\n"); log.flush()
prev = None
for i in range(10**6):
    nid = m.add(f"崩溃恢复第{i}条 {i*7919}", skip_dedup=True)
    if mode == "edges" and prev is not None:
        m.add_edge(prev, nid, "causal", 0.5)
        if i % 50 == 0:
            m.decay(1)
    prev = nid
    log.write(f"C {i} {nid}\n"); log.flush()
'''


def case_crash(A):
    out = {}
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, HARD_DIR=here)
    for k, (mode, delay) in enumerate([("plain", 1.5), ("edges", 2.0), ("plain", 0.7), ("bulk", 3.0)]):
        db = A.tmpdb(f"crash{k}")
        logp = db + ".log"
        p = subprocess.Popen([sys.executable, "-c", CHILD, A.impl, db, mode, logp], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, env=env)
        t0 = time.time()
        if mode == "bulk":            # 等预灌完成再进入维护循环计时（上限 40s）
            while time.time() - t0 < 40 and "READY" not in (open(logp, encoding="utf-8").read() if os.path.exists(logp) else ""):
                time.sleep(0.2)
        time.sleep(delay + (0 if mode == "bulk" else 1.0))
        os.kill(p.pid, signal.SIGKILL)
        p.wait()
        txt = open(logp, encoding="utf-8").read() if os.path.exists(logp) else ""
        done = [ln.split() for ln in txt.splitlines() if ln.startswith("C ") and len(ln.split()) == 3]
        tag = f"crash{k}:{mode}"
        out[f"{tag}:wrote_something"] = len(done) > 0
        try:
            m = A.open(db)
            pre = (lambda i: "维护中写入") if mode == "bulk" else (lambda i: f"崩溃恢复第{i}条")
            ok = all(str((m.get(nid) or {}).get("content", "")).startswith(pre(i)) for _, i, nid in done)
            out[f"{tag}:committed_present"] = ok
            try:
                out[f"{tag}:integrity"] = bool(m.integrity().get("integrity_ok", False))
            except Exception:
                out[f"{tag}:integrity"] = False
            out[f"{tag}:usable"] = _usable(m)
        except Exception:
            out[f"{tag}:committed_present"] = out[f"{tag}:integrity"] = out[f"{tag}:usable"] = False
        out[f"_n_{tag}"] = len(done)
    return out


def _snap_nodes(m):
    return sorted((n["id"], n["content"], n["layer"], round(n["importance"] or 0, 6), tuple(sorted(n["tags"] or [])))
                  for n in m.all_nodes() if n["layer"] in ("knowledge", "context", "anchor", "structure"))


def case_roundtrip(A):
    out = {}
    db = A.tmpdb("rt")
    m = A.open(db)
    ids = [m.add(f"往返事实{i} 内容{i * 13}", importance=round((i % 10) / 10, 1), tags=[f"t{i % 7}"], skip_dedup=True)
           for i in range(400)]
    ctx = [m.add(f"情境{i}", layer="context") for i in range(30)]
    anc = m.add("往返锚点：不可遗忘", layer="anchor")
    eids = []
    for i in range(0, 380, 2):
        try:
            eids.append(m.add_edge(ids[i], ids[i + 1], "causal", 0.6))
        except Exception:
            pass
    try:
        m.update_self({"identity": "往返测试体"})
    except Exception:
        pass
    m.protect(ids[3])
    before = _snap_nodes(m)
    edges_before = sorted((e["src"], e["dst"], e["rel"]) for i in ids[:380] for e in m.edges_of(i) if e["src"] == i)
    self_before = m.self_state()["identity"]
    m2 = m.reopen()
    out["persist:nodes_equal"] = _snap_nodes(m2) == before
    out["persist:edges_equal"] = sorted((e["src"], e["dst"], e["rel"]) for i in ids[:380] for e in m2.edges_of(i) if e["src"] == i) == edges_before
    out["persist:self_identity"] = m2.self_state()["identity"] == self_before == "往返测试体"
    out["persist:protected"] = ids[3] in [x if isinstance(x, str) else (x.get("node_id") if isinstance(x, dict) else getattr(x, "node_id", x)) for x in m2.protected()]
    # 导出 → 新库导入
    path = A.tmpfile(f"exp{time.time_ns()}.json")
    try:
        m2.export(path)
        m3 = A.open(A.tmpdb("rt_imp"))
        m3.import_(path)
        got = _snap_nodes(m3)
        want = [x for x in before if x[2] in ("knowledge", "context")]
        gotk = [x for x in got if x[2] in ("knowledge", "context")]
        out["export:local_layers_equal"] = gotk == want
        out["export:edges_equal"] = sorted((e["src"], e["dst"], e["rel"]) for i in ids[:380] for e in m3.edges_of(i) if e["src"] == i) == edges_before
        # 再导出一次：两份导出的节点集一致（幂等）
        path2 = A.tmpfile(f"exp2{time.time_ns()}.json")
        m3.export(path2)
        m4 = A.open(A.tmpdb("rt_imp2"))
        m4.import_(path2)
        out["export:idempotent"] = [x for x in _snap_nodes(m4) if x[2] in ("knowledge", "context")] == gotk
    except Exception:
        out["export:local_layers_equal"] = out["export:edges_equal"] = out["export:idempotent"] = False
    # 反复开关 60 次
    try:
        mm = m2
        for _ in range(60):
            mm = mm.reopen()
        out["persist:reopen_60x"] = mm.count("knowledge") == 400 + (1 if False else 0) or mm.count("knowledge") >= 400
    except Exception:
        out["persist:reopen_60x"] = False
    return out


def case_stress(A):
    """混合并发（写/连边/衰减/自我更新/删除/召回 同时进行）、双实例同库写、深链、海量标签、保护节点长期衰减、情境层上限。"""
    out = {}
    m = A.open(A.tmpdb("mix"))
    seed_ids = [m.add(f"混合种子{i}", skip_dedup=True) for i in range(200)]
    errs, lock = [], threading.Lock()

    def guard(tag, fn):
        try:
            fn()
        except (ValueError, KeyError):
            pass
        except Exception as ex:
            with lock:
                errs.append(f"{tag}:{type(ex).__name__}")

    def w_add(t):
        for i in range(200):
            guard("add", lambda: m.add(f"混合写{t}-{i}", skip_dedup=True))

    def w_edge(t):
        import random as _r
        r = _r.Random(t)
        for i in range(200):
            a, b = r.sample(seed_ids, 2)
            guard("edge", lambda: m.add_edge(a, b, "causal", 0.5))

    def w_decay():
        for i in range(40):
            guard("decay", lambda: m.decay(1))

    def w_self():
        for i in range(100):
            guard("self", lambda: m.update_self({"identity": f"自我{i}"}))

    def w_recall():
        for i in range(150):
            guard("recall", lambda: m.recall(f"混合写{i % 4}", limit=5))

    def w_del():
        for i in range(100, 150):
            guard("del", lambda: m.delete(seed_ids[i]))

    ths = ([threading.Thread(target=w_add, args=(t,)) for t in range(4)] + [threading.Thread(target=w_edge, args=(t,)) for t in range(3)]
           + [threading.Thread(target=f) for f in (w_decay, w_self, w_recall, w_del)])
    for t in ths:
        t.start()
    for t in ths:
        t.join(90)
    out["stress:mixed_threads_no_errors"] = not errs
    try:
        out["stress:mixed_integrity"] = bool(m.integrity().get("integrity_ok"))
        out["stress:mixed_adds_all_present"] = sum(1 for n in m.all_nodes() if str(n["content"]).startswith("混合写")) == 800
    except Exception:
        out["stress:mixed_integrity"] = out["stress:mixed_adds_all_present"] = False
    out["_mixed_errs"] = sorted(set(errs))[:8]
    # 双实例同库并发写（两个引擎实例 = 两条独立连接）
    db = A.tmpdb("two")
    m1, m2 = A.open(db), A.open(db)
    e2 = []

    def wr(mm, tag):
        for i in range(300):
            try:
                mm.add(f"双实例{tag}-{i}", skip_dedup=True)
            except Exception as ex:
                e2.append(type(ex).__name__)

    t1, t2 = threading.Thread(target=wr, args=(m1, "A")), threading.Thread(target=wr, args=(m2, "B"))
    t1.start(); t2.start(); t1.join(60); t2.join(60)
    out["stress:two_instances_no_errors"] = not e2
    try:
        m3 = A.open(db)
        out["stress:two_instances_no_lost_writes"] = sum(1 for n in m3.all_nodes() if str(n["content"]).startswith("双实例")) == 600
    except Exception:
        out["stress:two_instances_no_lost_writes"] = False
    # 深因果链 3000
    mc = A.open(A.tmpdb("deep"))
    chain = [mc.add(f"链节点{i}", skip_dedup=True) for i in range(3000)]
    for i in range(2999):
        mc.add_edge(chain[i], chain[i + 1], "causal", 0.6)
    st, r = _accepted_or_clean(lambda: mc.reason(chain[0], chain[-1], max_depth=3000))
    out["stress:deep_chain_3000_found"] = st == "ok" and len(r) >= 1
    st, r = _accepted_or_clean(lambda: mc.has_cycle())
    out["stress:deep_chain_no_false_cycle"] = st == "ok" and r is False
    # 悬空边：指向不存在节点
    st, _ = _accepted_or_clean(lambda: mc.add_edge(chain[0], "node_does_not_exist", "causal", 0.5))
    out["stress:dangling_edge_rejected"] = st == "rejected" or (st == "ok" and bool(mc.integrity().get("integrity_ok")))
    st, _ = _accepted_or_clean(lambda: mc.add_edge(chain[0], chain[1], "causal", float("nan")))
    out["stress:nan_edge_conf"] = st == "rejected" or all(
        isinstance(e["confidence"], float) and math.isfinite(e["confidence"]) for e in mc.edges_of(chain[0]))
    # 海量标签
    mt = A.open(A.tmpdb("tags"))
    tags = [f"标签{i}_%{i}" for i in range(1000)]
    st, nid = _accepted_or_clean(lambda: mt.add("海量标签节点", tags=tags, skip_dedup=True))
    out["stress:1000_tags_roundtrip"] = st == "ok" and set(mt.get(nid)["tags"]) >= set(tags)
    out["stress:tag_lookup_exact_in_1000"] = st == "ok" and [n["id"] for n in mt.by_tag("标签7_%7")] == [nid]
    # 保护节点在 300 轮强衰减后仍在；未保护低重要度节点被遗忘
    mp = A.open(A.tmpdb("prot"))
    keep = [mp.add(f"受保护{i}", importance=0.05, skip_dedup=True) for i in range(20)]
    for k in keep:
        mp.protect(k)
    loose = [mp.add(f"未保护{i}", importance=0.05, skip_dedup=True) for i in range(20)]
    try:
        mp.decay(300, 0.3)
        out["stress:protected_survive_300_decays"] = all(mp.get(k) is not None for k in keep)
    except Exception:
        out["stress:protected_survive_300_decays"] = False
    # 情境层上限
    try:
        mp.set_context_cap(100)
        for i in range(1000):
            mp.add(f"情境洪水{i}", layer="context")
        out["stress:context_cap_bounded"] = mp.count("context") <= 100
    except Exception:
        out["stress:context_cap_bounded"] = False
    # 自我层 5000 次更新：历史有界、可重开
    try:
        for i in range(5000):
            mp.update_self({"identity": f"身份{i}"})
        stt = mp.self_state()
        out["stress:self_history_bounded"] = stt["history_len"] <= 1000
        out["stress:self_latest_identity"] = stt["identity"] == "身份4999"
        out["stress:self_snapshots_not_in_recall"] = not any("身份4" in str(n["content"]) for n, _ in mp.recall("身份4999", limit=10))
    except Exception:
        out["stress:self_history_bounded"] = out["stress:self_latest_identity"] = out["stress:self_snapshots_not_in_recall"] = False
    return out


CASES = [case_unicode, case_empty, case_long, case_numeric, case_sqlish, case_threads, case_crash, case_roundtrip, case_stress]


def run(A, seed, only=None):
    res = {}
    for fn in CASES:
        name = fn.__name__[5:]
        if only and name not in only:
            continue
        try:
            r = fn(A)
        except Exception as ex:
            r = {f"{name}:case_crashed": False, f"_{name}_err": f"{type(ex).__name__}:{str(ex)[:120]}"}
        res.update(r)
    checks = {k: bool(v) for k, v in res.items() if not k.startswith("_")}
    return {"checks": checks, "passed": sum(checks.values()), "total": len(checks),
            "notes": {k: v for k, v in res.items() if k.startswith("_")}}
