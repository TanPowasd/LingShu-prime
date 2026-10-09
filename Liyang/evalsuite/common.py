"""run_all 的子进程调度：每个探针 / 性质一个子进程 + 超时隔离，线程池并行。"""
import json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "probe_runner.py")


def child_env(root):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([root, HERE])
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONUTF8"] = "1"
    env.pop("AEIS_DESIGNER_KEY", None)
    env.pop("MDCG_ROOT", None)
    return env


def run_child(root, impl, args, timeout):
    cwd = tempfile.mkdtemp(prefix="evs_cwd_")
    t0 = time.perf_counter()
    try:
        p = subprocess.run([sys.executable, RUNNER, "--impl", impl] + args, cwd=cwd, env=child_env(root),
                           capture_output=True, text=True, timeout=timeout)
        out = p.stdout
    except subprocess.TimeoutExpired as ex:
        out = ex.stdout.decode() if isinstance(ex.stdout, bytes) else (ex.stdout or "")
        return {"verdict": "TIMEOUT", "reading": f"超时 {timeout}s", "sec": round(time.perf_counter() - t0, 2)}
    for line in reversed(out.splitlines()):
        if line.startswith("@@RESULT "):
            return json.loads(line[9:])
    for line in reversed(out.splitlines()):   # 探针自行 os._exit 前打印的 BUG/OK 行
        s = line.strip()
        if s.startswith("BUG") or s.startswith("OK"):
            return {"verdict": s.split()[0], "reading": s[:300], "sec": round(time.perf_counter() - t0, 2)}
    tail = (p.stderr or "").strip().splitlines()[-1:] or ["<no output>"]
    return {"verdict": "ERR", "reading": f"rc={p.returncode} {tail[0][:200]}", "sec": round(time.perf_counter() - t0, 2)}


def list_items(root, impl="legacy"):
    r = subprocess.run([sys.executable, RUNNER, "--impl", impl, "--list"], cwd=tempfile.mkdtemp(),
                       env=child_env(root), capture_output=True, text=True, timeout=120)
    for line in reversed(r.stdout.splitlines()):
        if line.startswith("@@RESULT "):
            return json.loads(line[9:])
    raise RuntimeError("list failed: " + r.stderr[-500:])


def pmap(jobs, workers):
    """jobs: list of (key, fn) → dict key->result（线程池里每个 fn 自己起子进程）。"""
    res = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn): key for key, fn in jobs}
        for f in futs:
            res[futs[f]] = f.result()
    return res
