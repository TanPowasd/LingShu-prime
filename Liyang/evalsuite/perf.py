"""性能：add / recall / decay_cycle / self_check / activation 在规模 N 下的中位耗时与峰值内存。

口径（对所有实现相同）：
  - 文件库（激活引擎需要文件库）；用公开 add(skip_dedup=True) 灌入 N 个知识节点 + N/10 个情境节点，
    以及 N/2 条 DAG 因果边（i→j 且 i<j，无环，避免把 #252 的环枚举爆炸混进性能读数——那归缺陷探针）。
  - 每个操作在灌库后重复 k 次取中位数（add k=50、recall k=10、decay/self_check/activation k=3）。
  - 计时与内存分两个子进程跑（tracemalloc 会拖慢计时）：计时进程报 ru_maxrss（含 SQLite C 堆），
    内存进程开 tracemalloc 报 Python 堆峰值（灌库+全部操作各一遍）。
  - 灌库耗时单独报告（build_s），不计入任何操作的中位数。
  - first_read_ms：灌库后、各操作之前的第一次 recall 单次冷耗时（惰性派生索引的首读成本）。
    只记录并在报告中列出，**不计分**（评分规则 v1 已冻结，PERF_OPS 不含它）。
"""
import random
import resource
import statistics
import time
import tracemalloc

from adapters import Adapter, NA


def _med(fn, k):
    ts = []
    for i in range(k):
        t0 = time.perf_counter()
        fn(i)
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts) * 1000.0


def run_perf(impl, n, ops=None, trace=False):
    A = Adapter(impl)
    rnd = random.Random(n)
    words = ["服务器", "数据库", "备份", "用户", "配置", "端口", "证书", "日志", "预算", "会议", "合同", "版本"]
    if trace:
        tracemalloc.start()
    t0 = time.perf_counter()
    m = A.open(A.tmpdb(f"perf{n}"))
    ids = []
    for i in range(n):
        ids.append(m.add(f"{rnd.choice(words)}{rnd.choice(words)}记录{i}：{rnd.choice(words)}状态{i * 7919 % 100003}",
                         importance=round(rnd.random(), 3), skip_dedup=True))
    for i in range(n // 10):
        m.add(f"情境{i}：{rnd.choice(words)}", layer="context", importance=round(rnd.random(), 3))
    for _ in range(n // 2):
        a, b = sorted(rnd.sample(range(n), 2))
        m.add_edge(ids[a], ids[b], "causal", 0.6)
    build = time.perf_counter() - t0
    out = {"n": n, "build_s": round(build, 2)}
    t0 = time.perf_counter()     # 建库后首次读（冷、不预热）；只记录与报告列出，不计分（评分规则 v1 冻结）
    try:
        m.recall(f"{words[0]}状态", limit=10)
        out["first_read_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    except Exception as ex:
        out["first_read_ms"] = None
        out.setdefault("err", {})["first_read"] = f"{type(ex).__name__}: {str(ex)[:80]}"
    ops = ops or ["add", "recall", "decay_cycle", "self_check", "activation"]
    for op in ops:
        try:
            if op == "add":
                out[op] = _med(lambda i: m.add(f"新增记忆 {i} {rnd.random()}", importance=0.5), 50)
            elif op == "recall":
                out[op] = _med(lambda i: m.recall(f"{words[i % len(words)]}状态", limit=10), 10)
            elif op == "decay_cycle":
                out[op] = _med(lambda i: m.decay(1), 3)
            elif op == "self_check":
                out[op] = _med(lambda i: m.self_check(), 3)
            elif op == "activation":
                out[op] = _med(lambda i: m.activate(f"{words[i % len(words)]}状态", hops=2, workset=f"w{i}"), 3)
        except NA as ex:
            out[op] = None
            out.setdefault("na", {})[op] = str(ex)[:80]
        except Exception as ex:
            out[op] = None
            out.setdefault("err", {})[op] = f"{type(ex).__name__}: {str(ex)[:80]}"
        if out.get(op) is not None:
            out[op] = round(out[op], 3)
    if trace:
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        out["py_peak_mb"] = round(peak / 2 ** 20, 1)
    out["maxrss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    return out
