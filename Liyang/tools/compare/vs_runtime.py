"""同机、同数据、同度量：上游 cb3a6ea 与 ng 兼容门面的写入 / 召回 / 衰减 / 晋升（stab-r5）。

    UP_ROOT=/tmp/up_cb3a6ea [NG_ROOT=<含 lingshu_ng 的目录，缺省本仓>] python tools/compare/vs_runtime.py <out_dir> [规模...]

上游快照须是 ``git -C <上游仓> archive cb3a6ea | tar -x -C /tmp/up_cb3a6ea`` 得到的只读副本；本脚本只把它放进子进程的
PYTHONPATH，不复制、不修改其实现。ng 侧 LINGSHU_NG_SEM=off（零模型，与上游同为纯词面）。两边串行，各一个子进程。
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "perf"))
import corpus  # noqa: E402


def run(impl, docs, queries, bench=True, timeout=None):
    jd = tempfile.mkdtemp(prefix=f"vs_{impl}_", dir="/tmp")
    jf, of = os.path.join(jd, "job.json"), os.path.join(jd, "out.json")
    json.dump({"docs": docs, "queries": queries, "db": os.path.join(jd, "m.db"), "bench": bench},
              open(jf, "w", encoding="utf-8"), ensure_ascii=False)
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
    if impl == "up":
        env["PYTHONPATH"] = os.environ.get("UP_ROOT", "/tmp/up_cb3a6ea")
    else:
        env["PYTHONPATH"] = os.environ.get("NG_ROOT", ROOT)
        env["LINGSHU_NG_SEM"] = "off"
    p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "vs_worker.py"), impl, jf, of],
                       env=env, cwd=jd, capture_output=True, text=True, timeout=timeout)
    if not os.path.exists(of):
        raise RuntimeError(p.stderr[-3000:])
    out = json.load(open(of, encoding="utf-8"))
    import shutil
    shutil.rmtree(jd, ignore_errors=True)
    return out


def main():
    od = sys.argv[1]
    sizes = [int(x) for x in sys.argv[2:]] or [1000, 10000]
    os.makedirs(od, exist_ok=True)
    for n in sizes:
        docs, qs, src = corpus.build(n, 200)
        queries = [{"qid": f"q{i}", "q": q, "limit": 10} for i, q in enumerate(qs)]
        for impl in ("ng", "up"):
            f = os.path.join(od, f"rt_{impl}_{n}.json")
            if os.path.exists(f):
                continue
            r = run(impl, docs, queries)
            r["corpus"] = src
            json.dump(r, open(f, "w", encoding="utf-8"), ensure_ascii=False)
            print(impl, n, {k: v for k, v in r.items() if k not in ("rank", "query_ms", "segment_s_per_1000")}, flush=True)


if __name__ == "__main__":
    main()
