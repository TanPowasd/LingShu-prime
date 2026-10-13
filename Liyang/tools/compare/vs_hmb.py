"""现有检索集上的同口径读数：HMB 检索轨（178 块 / 92 题 / k=10）与状态链检索代理（419 题 test），
被测为上游 cb3a6ea 与 ng（零模型 / 交付缺省两档）。度量、题目、写入方式（每块 add_perception，再 recall）与
bench_gen/gate_cn.py 完全相同，只把子进程工人换成 tools/compare/vs_worker.py（按 impl 选上游或 ng 的同名类）。

    G1_FROZEN_CLOCK=1760000000 UP_ROOT=/tmp/up_cb3a6ea python tools/compare/vs_hmb.py <out_dir> [up ng_off ng_def]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "bench_gen"))
sys.path.insert(0, HERE)
import gate_cn  # noqa: E402
import vs_runtime  # noqa: E402

IMPL = {"v": "ng"}
SHIM = os.path.join(ROOT, "bench_gen", "clockshim")


def fake_run_ng(impl, docs, queries, path="recall", tag="job", timeout=None):
    which = IMPL["v"]
    real = vs_runtime.subprocess.run

    def run(*a, **kw):
        env = dict(kw.get("env") or os.environ)
        if os.environ.get("G1_FROZEN_CLOCK"):
            env["PYTHONPATH"] = SHIM + os.pathsep + env.get("PYTHONPATH", "")
        if which == "ng_def":
            env.pop("LINGSHU_NG_SEM", None)
        kw["env"] = env
        return real(*a, **kw)
    vs_runtime.subprocess.run = run
    try:
        out = vs_runtime.run("up" if which == "up" else "ng", docs, queries, bench=False, timeout=timeout)
    finally:
        vs_runtime.subprocess.run = real
    return out


def main():
    od = sys.argv[1]
    impls = sys.argv[2:] or ["up", "ng_off", "ng_def"]
    os.makedirs(od, exist_ok=True)
    gate_cn.ptlib.run_ng = fake_run_ng
    for impl in impls:
        f = os.path.join(od, f"hmb_{impl}.json")
        if os.path.exists(f):
            continue
        IMPL["v"] = impl
        gate_cn.RANKS.clear()
        res = {"impl": impl, "hmb": gate_cn.hmb(ROOT), "chain": gate_cn.chain(ROOT)}
        json.dump(res, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(gate_cn.RANKS, open(os.path.join(od, f"hmb_{impl}_ranks.json"), "w", encoding="utf-8"), ensure_ascii=False)
        print(json.dumps(res, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
