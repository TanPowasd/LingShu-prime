# -*- coding: utf-8 -*-
"""bench_scale · ng 与旧版（lingshu.core @ integrated-v2）的规模基准

用法（仓根）：
    python tests_ng/bench_scale.py                         # 两实现 × N=1k,10k,50k
    python tests_ng/bench_scale.py --sizes 1000 5000 --impl ng
    python tests_ng/bench_scale.py --out tests_ng/bench_scale_result.json

口径（与 bench/bench_perf.py 一致的确定性灌库，同一 seed 两实现完全同样的数据）：
  知识层 ≈0.9N（add_perception skip_dedup=True，2 标签 + 1 实体）、情境层 ≈0.1N（受 FIFO 上限）、
  结构 5 / 锚点 3、因果边 N 条；:memory: 库。每个实现、每个 N 在独立子进程里跑（互不污染）。
  测量：add（带 M5 去重的单次写入）、recall（双词查询，bench_perf 同一查询表）、decay（单轮
  decay_cycle）、self_check、activation（ActivationEngine(store=engine.store).activate）。
  每 op 预热 1 次后取 repeat 次中位数（ms）；add 放最后（前面各 op 看到的库规模恰为 N）。
  first_read_ms：灌库结束后**第一次** recall 的单次冷耗时（不预热，在各 op 之前测；含惰性派生
  索引的首读重建——ng 的写路径只记脏，这一笔成本落在首读上，与 build_ms 合看才是完整建库代价）。
旧版路径由 ``--legacy-root``（默认 /workspace/work/ls/integrated）给出。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import resource
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY_ROOT = "/workspace/work/ls/integrated"
WORDS = ["记忆", "视觉", "图像", "语义", "识别", "检测", "实验", "验证", "对话", "语音",
         "因果", "时间", "空间", "实体", "场景", "结构", "知识", "推理", "预测", "反思",
         "汽车", "红色", "圆形", "条纹", "左边", "右边", "上方", "下方", "移动", "静止",
         "灵枢", "协议", "引擎", "节点", "边", "层", "衰减", "巩固", "检索", "召回"]
REPEAT = {"recall": 21, "decay": 5, "self_check": 5, "activation": 5, "add": 21}


def sentence(rng: random.Random, k: int = 8) -> str:
    """确定性随机句（与 bench_perf 同构）。"""
    return "".join(rng.choice(WORDS) for _ in range(k)) + f"#{rng.randrange(10**6)}"


def queries(n: int = 64, seed: int = 11):
    """bench_perf 同一查询表：双词拼接。"""
    q = random.Random(seed)
    return [q.choice(WORDS) + q.choice(WORDS) for _ in range(n)]


def load_impl(impl: str, legacy_root: str):
    """返回 (SpacetimeMemoryEngine, EdgeType, ActivationEngine)。"""
    if impl == "legacy":
        sys.path.insert(0, legacy_root)
        from lingshu.core.activation import ActivationEngine
        from lingshu.core.core import EdgeType, SpacetimeMemoryEngine
    else:
        sys.path.insert(0, ROOT)
        from lingshu_ng.compat import EdgeType, SpacetimeMemoryEngine
        from lingshu_ng.compat_activation import ActivationEngine
    return SpacetimeMemoryEngine, EdgeType, ActivationEngine


def build(engine_cls, edge_type, n: int, seed: int = 7):
    """确定性灌库，返回 (引擎, 灌库耗时 ms)。"""
    t0 = time.perf_counter()
    eng = engine_cls(db_path=":memory:")
    rng = random.Random(seed)
    ids = []
    n_ctx = max(1, n // 10)
    for _ in range(max(1, n - n_ctx - 8)):
        ids.append(eng.add_perception(sentence(rng), importance=round(rng.random(), 3),
                                      tags=[f"topic:{rng.randrange(20)}", rng.choice(WORDS)],
                                      entities=[f"car_{rng.randrange(50)}"], skip_dedup=True).id)
    for _ in range(n_ctx):
        ids.append(eng.add_context(sentence(rng), importance=0.4 + 0.5 * rng.random()).id)
    for i in range(5):
        eng.add_structure_node(f"结构规则{i}：" + sentence(rng))
    for i in range(3):
        eng.set_anchor(f"锚点{i}：" + sentence(rng))
    live = [i for i in ids if eng.store.get_node(i) is not None]
    for _ in range(n):
        a, b = rng.sample(live, 2)
        eng.add_edge(a, b, edge_type.CAUSAL, confidence=0.3 + 0.6 * rng.random())
    return eng, (time.perf_counter() - t0) * 1000.0


def timed(fn, repeat: int):
    """预热 1 次后 repeat 次耗时（ms）。"""
    fn()
    out = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000.0)
    return out


def run_one(impl: str, n: int, legacy_root: str) -> dict:
    """单实现单规模（在子进程中调用）。"""
    engine_cls, edge_type, act_cls = load_impl(impl, legacy_root)
    eng, build_ms = build(engine_cls, edge_type, n)
    qs, qi = queries(), [0]

    def nextq():
        qi[0] += 1
        return qs[qi[0] % len(qs)]

    act = act_cls(store=eng.store, audit_path=os.devnull)
    w = random.Random(13)
    ops = [("recall", lambda: eng.recall(nextq())),
           ("decay", lambda: eng.decay_cycle(factor=0.02)),
           ("self_check", lambda: eng.self_check()),
           ("activation", lambda: act.activate(nextq(), workset="bench")),
           ("add", lambda: eng.add_perception(sentence(w), importance=0.5, tags=["bench"]))]
    row = {"impl": impl, "N": n, "build_ms": round(build_ms, 1)}
    t0 = time.perf_counter()                 # 建库后第一次读：冷耗时、不预热（含派生索引的首读重建）
    eng.recall(qs[0])
    row["first_read_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    for name, fn in ops:
        ts = timed(fn, REPEAT[name])
        row[name] = round(statistics.median(ts), 3)
    row["maxrss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)
    eng.close()
    return row


def main(argv=None) -> int:
    """命令行入口：逐 (impl, N) 起子进程并汇总为表。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[1000, 10000, 50000])
    ap.add_argument("--impl", nargs="+", default=["legacy", "ng"])
    ap.add_argument("--legacy-root", default=LEGACY_ROOT)
    ap.add_argument("--out", default=None)
    ap.add_argument("--child", nargs=2, default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.child:
        print("@@ROW@@" + json.dumps(run_one(a.child[0], int(a.child[1]), a.legacy_root)))
        return 0
    rows = []
    for n in a.sizes:
        for impl in a.impl:
            p = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", impl, str(n),
                                "--legacy-root", a.legacy_root], capture_output=True, text=True,
                               cwd=a.legacy_root if impl == "legacy" else ROOT)
            line = [x for x in p.stdout.splitlines() if x.startswith("@@ROW@@")]
            row = json.loads(line[0][7:]) if line else {"impl": impl, "N": n, "error": p.stderr[-800:]}
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
