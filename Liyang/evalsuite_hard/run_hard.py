#!/usr/bin/env python3
"""HARD 榜调度：快照冻结 → 作业（维度 × 种子 × 参数）→ 结果缓存（可分段续跑）→ score.py 计分渲染。

沙箱单条命令 ≤115s，故调度是「分段」的：每次调用在 --budget 秒内尽量多跑未完成作业（2 并发），
已完成作业写入 out/cache/<run>/<snap>/<job>.json，下次调用跳过；全部完成后 `--render` 输出 json 与榜单。

  python3 evalsuite_hard/run_hard.py --run r1 --snap base=/workspace/work/ls/upstream@2bb8291#legacy \
      --snap integrated=/workspace/work/ls/integrated@667e84a#legacy --snap ng=/workspace/work/ls/rewrite@HEAD#ng --budget 100
  python3 evalsuite_hard/run_hard.py --run r1 --status
  python3 evalsuite_hard/run_hard.py --run r1 --render
"""
import argparse, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "runner.py")
OUT = os.path.join(HERE, "out")
SEEDS = (0, 1)


TIMING = ("scale_", "causal_big", "world_scene", "world_nn", "causal2_huge", "world2_scene20k")
REPS = 3


def is_timing(key):
    return key.startswith(TIMING)


def jobs_for(seed, reps=REPS):
    """(key, dim, args, 预估秒, 依赖 key)。v1 作业键不变；v2 新增作业以 robust2_/causal2_/world2_/stability2_ 开头。
    计时作业（TIMING 前缀）另有 reps-1 份重复：<key>.r1、<key>.r2（score._load 逐指标取中位数）。"""
    J = []
    for n in (1000, 10000, 50000):
        J.append((f"retrieval_{n}_s{seed}", "retrieval", {"sizes": [n]}, 30 if n == 50000 else 10, None))
    J.append((f"dedup_s{seed}", "dedup", {}, 40, None))
    for c in ("unicode", "empty", "long", "numeric", "sqlish", "threads", "crash", "roundtrip", "stress"):
        J.append((f"robust_{c}_s{seed}", "robust", {"only": [c]}, 40, None))
    J.append((f"meta_s{seed}", "meta", {}, 15, None))
    J.append((f"causal_small_s{seed}", "causal", {"part": "small"}, 15, None))
    J.append((f"causal_big_s{seed}", "causal", {"part": "big"}, 70, None))
    for c in range(5):
        J.append((f"stability_c{c}_s{seed}", "stability", {"chunk": c}, 45, f"stability_c{c - 1}_s{seed}" if c else None))
    for n in (1000, 10000, 50000, 200000):
        J.append((f"scale_{n}_s{seed}", "scale", {"n": n}, {1000: 5, 10000: 10, 50000: 40, 200000: 100}[n], None))
    for p in ("hexgen", "scene", "stcnn", "nn"):
        J.append((f"world_{p}_s{seed}", "world", {"part": p}, 60 if p == "nn" else 20, None))
    if os.environ.get("HARD_LLM") == "1":          # 可选 LLM 判官维（网络依赖，默认不跑）
        J.append((f"llm_s{seed}", "llm", {}, 90, None))
    # ---- hard-rules-v2 新增 ----
    for it in ("crash_maint", "crash_export", "import_read"):
        J.append((f"robust2_{it}_s{seed}", "robust2", {"only": [it]}, 60, None))
    for c in range(4):
        J.append((f"robust2_prep_c{c}_s{seed}", "robust2", {"prep_chunk": c}, 85, f"robust2_prep_c{c - 1}_s{seed}" if c else None))
    J.append((f"robust2_crash200k_s{seed}", "robust2", {"only": ["crash200k"]}, 60, f"robust2_prep_c3_s{seed}"))
    for p in ("johnson", "chains", "huge"):
        J.append((f"causal2_{p}_s{seed}", "causal2", {"part": p}, 90 if p == "huge" else 20, None))
    for p in ("scene20k", "hexgen_open"):
        J.append((f"world2_{p}_s{seed}", "world2", {"part": p}, 40, None))
    for c in range(5):
        J.append((f"stability2_c{c}_s{seed}", "stability2", {"chunk": c}, 90, f"stability2_c{c - 1}_s{seed}" if c else None))
    out = []
    for j in J:
        out.append(j)
        if is_timing(j[0]):
            for r in range(1, reps):
                out.append((f"{j[0]}.r{r}",) + j[1:])
    return out


def parse_snap(s):
    name, rest = s.split("=", 1)
    impl = "ng" if name.startswith("ng") else "legacy"
    if "#" in rest:
        rest, impl = rest.split("#", 1)
    rev = None
    if "@" in rest:
        rest, rev = rest.split("@", 1)
    path = rest
    full = subprocess.run(["git", "-C", path, "rev-parse", rev or "HEAD"], capture_output=True, text=True).stdout.strip()
    short = full[:7]
    root = os.path.join(OUT, "_snap", f"{name}-{short}")
    if not os.path.isdir(root):
        os.makedirs(root)
        subprocess.run(f"git -C {path} archive {full} | tar -x -C {root}", shell=True, check=True)
    return {"name": name, "impl": impl, "path": path, "rev": full, "root": root}


def run_job(snap, job, cdir, timeout, run):
    key, dim, args, est, dep = job
    env = dict(os.environ)
    env["PYTHONPATH"] = snap["root"]
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONUTF8"] = "1"
    env.pop("AEIS_DESIGNER_KEY", None)
    # 长期稳定的跨段状态库放本地临时盘（与其它维度 tempfile 库同盘）：out/ 位于 JuiceFS(FUSE)，
    # SQLite WAL 的逐语句加锁在 FUSE 上慢约 25 倍，r1 三方稳定性 c0 均因此超时（见 LEADERBOARD 迭代日志 r2）。
    env["HARD_STATE_DIR"] = os.path.join(tempfile.gettempdir(), "hard_state", run, snap["name"])
    os.makedirs(env["HARD_STATE_DIR"], exist_ok=True)
    part = os.path.join(cdir, key + ".partial")
    env["HARD_PARTIAL"] = part
    seed = int(key.rsplit("_s", 1)[1].split(".")[0])
    cmd = [sys.executable, RUNNER, "--impl", snap["impl"], "--dim", dim, "--seed", str(seed)]
    if dim in ("stability", "stability2"):
        args = dict(args, tag=run)
    for k, v in args.items():
        cmd += ["--arg", f"{k}={json.dumps(v)}"]
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=tempfile.mkdtemp(prefix="hard_cwd_"), env=env, capture_output=True, text=True, timeout=timeout)
        res = None
        for line in reversed(p.stdout.splitlines()):
            if line.startswith("@@RESULT "):
                res = json.loads(line[9:])
                break
        if res is None:
            res = {"status": "ERR", "reading": f"rc={p.returncode} {(p.stderr or '').strip()[-300:]}"}
    except subprocess.TimeoutExpired:
        res = {"status": "TIMEOUT", "reading": f"超时 {timeout}s"}
        if os.path.exists(part):
            res["raw"] = json.load(open(part))
    res["wall"] = round(time.perf_counter() - t0, 2)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--snap", action="append", default=[])
    ap.add_argument("--budget", type=float, default=100)
    ap.add_argument("--job-cap", type=float, default=100)
    ap.add_argument("--only", default="")
    ap.add_argument("--seeds", default="0,1")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--redo", default="", help="逗号分隔的作业前缀：删除这些缓存重跑")
    ap.add_argument("--klass", default="all", choices=["all", "timing", "quality"],
                    help="timing：只跑计时作业（建议 --workers 1，三方交替）；quality：只跑非计时作业")
    ap.add_argument("--snaps-only", default="", help="逗号分隔：只调度这些快照")
    ap.add_argument("--skip", default="", help="逗号分隔的作业前缀：本次不调度")
    a = ap.parse_args()
    rdir = os.path.join(OUT, "cache", a.run)
    os.makedirs(rdir, exist_ok=True)
    mf = os.path.join(rdir, "snaps.json")
    if a.snap:
        snaps = [parse_snap(s) for s in a.snap]
        json.dump(snaps, open(mf, "w"), ensure_ascii=False, indent=1)
    snaps = json.load(open(mf))
    if a.render:
        import score
        score.render(a.run, snaps, rdir)
        score.render_v2(a.run, snaps, rdir)
        return
    seeds = [int(x) for x in a.seeds.split(",")]
    pending = []
    sel = [sn for sn in snaps if not a.snaps_only or sn["name"] in a.snaps_only.split(",")]
    for sn in sel:
        cdir = os.path.join(rdir, sn["name"])
        os.makedirs(cdir, exist_ok=True)
        for pref in [x for x in a.redo.split(",") if x]:
            for f in os.listdir(cdir):
                if f.startswith(pref):
                    os.remove(os.path.join(cdir, f))
    # 交替顺序：外层（种子、作业、重复），内层快照——同一作业三方背靠背执行，宿主负载对三方近似同分布
    for sd in seeds:
        for job in jobs_for(sd):
            if a.only and not any(job[0].startswith(o) for o in a.only.split(",")):
                continue
            if a.skip and any(job[0].startswith(o) for o in a.skip.split(",")):
                continue
            if a.klass == "timing" and not is_timing(job[0]):
                continue
            if a.klass == "quality" and is_timing(job[0]):
                continue
            for sn in sel:
                cdir = os.path.join(rdir, sn["name"])
                if not os.path.exists(os.path.join(cdir, job[0] + ".json")):
                    pending.append((sn, job, cdir))
    if a.status:
        for sn, job, _ in pending:
            print("PENDING", sn["name"], job[0])
        print(f"pending={len(pending)}")
        return
    t0 = time.time()
    running = {}
    done_n = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        while pending or running:
            el = time.time() - t0
            started = False
            if len(running) < a.workers:
                for i, (sn, job, cdir) in enumerate(pending):
                    key, dep = job[0], job[4]
                    if dep and not os.path.exists(os.path.join(cdir, dep + ".json")):
                        continue
                    if any(r[0]["name"] == sn["name"] and r[1][1] == job[1] and job[1] in ("stability", "stability2", "robust2") for r in running.values()):
                        continue
                    estf = os.path.join(cdir, key + ".est")
                    est = float(open(estf).read()) if os.path.exists(estf) else job[3]
                    remain = a.budget - el
                    lone = not running and done_n == 0 and el < 5      # 段首空闲：大作业也放行（独占本段）
                    if est * 1.2 + 2 > remain and not lone:
                        continue
                    tmo = a.job_cap if lone else min(a.job_cap, remain)
                    fut = ex.submit(run_job, sn, job, cdir, tmo, a.run)
                    running[fut] = (sn, job, cdir, tmo)
                    pending.pop(i)
                    started = True
                    break
            if started:
                continue
            if not running:
                break
            fin, _ = wait(list(running), timeout=1.0, return_when=FIRST_COMPLETED)
            for f in fin:
                sn, job, cdir, tmo = running.pop(f)
                res = f.result()
                key = job[0]
                if res["status"] == "TIMEOUT" and tmo < a.job_cap - 1:
                    open(os.path.join(cdir, key + ".est"), "w").write(str(max(tmo + 5, job[3])))
                    print("RETRY-LATER", sn["name"], key, flush=True)
                    continue
                json.dump(res, open(os.path.join(cdir, key + ".json"), "w"), ensure_ascii=False)
                open(os.path.join(cdir, key + ".est"), "w").write(str(res["wall"]))
                done_n += 1
                print("DONE", sn["name"], key, res["status"], res["wall"], flush=True)
    left = len(pending) + 0
    print(f"本段完成 {done_n}，剩余 {left}，用时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
