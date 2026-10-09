"""H-SCL 规模：N ∈ {1k, 10k, 50k, 200k} 的原始耗时与内存（相对「理想上限」参考值取对数倍率分，见 score.py）。

灌库（公开 add，skip_dedup=True）：N 条知识 + N/10 情境 + N/2 条 DAG 因果边；另在开头写 20 条「针」事实。
测量：build_us_per_add（灌库均摊）、add_ms（去重路径，k=30 中位）、recall_ms（k=20 中位）、needle_found@10、
dedup_far_merge（重写最早的 10 条事实是否合并）、decay_ms（k=2）、self_check_ms（k=1）、reopen_ms（关闭+重开+首次召回）、maxrss_mb。
每测完一项即写入 HARD_PARTIAL 文件，超时也保留已测项（缺项计 0）。
"""
import json
import os
import random
import resource
import statistics
import time


def _med(fn, k):
    ts = []
    for i in range(k):
        t0 = time.perf_counter()
        fn(i)
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts) * 1000.0


def run(A, seed, n=1000):
    part = os.environ.get("HARD_PARTIAL")
    out = {"n": n}

    def save():
        out["maxrss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        if part:
            json.dump(out, open(part, "w"), ensure_ascii=False)

    rnd = random.Random(seed * 7 + n)
    words = ["服务器", "数据库", "备份", "用户", "配置", "端口", "证书", "日志", "预算", "会议", "合同", "版本"]
    db = A.tmpdb(f"scale{n}")
    m = A.open(db)
    needles = []
    for j in range(20):
        needles.append(m.add(f"针事实{j}：仓库钥匙编号{seed}{j:02d}藏在{rnd.choice(words)}柜", skip_dedup=True))
    early = [f"早期事实{j}：{rnd.choice(words)}{rnd.choice(words)}编号{j * 7919 + seed}" for j in range(10)]
    early_ids = [m.add(s) for s in early]
    t0 = time.perf_counter()
    ids = []
    for i in range(n):
        ids.append(m.add(f"{rnd.choice(words)}{rnd.choice(words)}记录{i}：{rnd.choice(words)}状态{i * 7919 % 100003}",
                         importance=round(rnd.random(), 3), skip_dedup=True))
    out["build_us_per_add"] = round((time.perf_counter() - t0) / n * 1e6, 2)
    save()
    for i in range(n // 10):
        m.add(f"情境{i}：{rnd.choice(words)}", layer="context", importance=round(rnd.random(), 3))
    t0 = time.perf_counter()
    for _ in range(n // 2):
        a, b = sorted(rnd.sample(range(n), 2))
        m.add_edge(ids[a], ids[b], "causal", 0.6)
    out["edge_us"] = round((time.perf_counter() - t0) / max(1, n // 2) * 1e6, 2)
    save()
    out["add_ms"] = round(_med(lambda i: m.add(f"规模新增 {i} 值{rnd.random()}"), 30), 4)
    save()
    out["recall_ms"] = round(_med(lambda i: m.recall(f"{words[i % len(words)]}状态", limit=10), 20), 4)
    save()
    hit = 0
    for j in range(20):
        r = m.recall(f"仓库钥匙编号{seed}{j:02d}", limit=10)
        hit += any(x["id"] == needles[j] for x, _ in r)
    out["needle_found@10"] = hit / 20
    save()
    merged = 0
    for s, i0 in zip(early, early_ids):
        try:
            merged += m.add(s) == i0
        except Exception:
            pass
    out["dedup_far_merge"] = merged / 10
    save()
    out["decay_ms"] = round(_med(lambda i: m.decay(1), 2), 3)
    save()
    out["self_check_ms"] = round(_med(lambda i: m.self_check(), 1), 3)
    save()
    t0 = time.perf_counter()
    m2 = m.reopen()
    m2.recall("仓库钥匙", limit=5)
    out["reopen_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    save()
    return out
