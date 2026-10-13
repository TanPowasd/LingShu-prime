# -*- coding: utf-8 -*-
"""zh-v13 查询延迟验收（PREREG_ZH 修订 11）。DuRT 某份的各库，逐库按轮换顺序跑各配置（ABBA 式抵消宿主负载漂移），
每 (配置, 库) 一个子进程（lat_worker.py），结果存 runs/durt/v13/lat/<run>/<cfg>_<库>.json（已存在跳过 = 断点续跑）。
  python v13/lat.py run <run> <split> <nstores> name=ROOT|K=V|K=V ...
  python v13/lat.py show <run> [cfgA cfgB ...]
冷 = 打分件已加载、问句-段落分与段落向量均无缓存（空缓存目录）；热 = 同进程同批问句第二遍（全部命中缓存）。模型加载、建库、预取另记。"""
import json, os, statistics, subprocess, sys, tempfile, shutil
H = os.path.dirname(os.path.abspath(__file__)); B = os.path.dirname(H); sys.path.insert(0, B)
os.environ.setdefault("T2R_SET", "durt")
import t2r_eval as E  # noqa: E402

WT = os.path.dirname(B)
OUTR = os.path.join(E.OUT, "v13", "lat")


def parse(spec):
    name, rest = spec.split("=", 1)
    parts = rest.split("|")
    root = parts[0] or WT
    env = {}
    for p in parts[1:]:
        k, v = p.split("=", 1); env[k] = v
    return name, root, env


def one(st, qs, root, env, of, prefetch):
    jd = tempfile.mkdtemp(prefix="zhlatj_", dir="/tmp")
    cache = os.path.join(jd, "cache"); os.makedirs(cache)
    jf = os.path.join(jd, "j.json")
    json.dump({"docs": [x["text"] for x in st["docs"]], "queries": qs, "prefetch": prefetch}, open(jf, "w", encoding="utf-8"), ensure_ascii=False)
    e = dict(os.environ, PYTHONHASHSEED="0", G1_FROZEN_CLOCK="1760000000", LINGSHU_NG_SEM_CACHE=cache)
    e.pop("LINGSHU_NG_ASSOC", None); e.update(env)
    e["PYTHONPATH"] = root + os.pathsep + os.path.join(B, "clockshim")
    tmp = of + ".tmp"
    p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(H, "lat_worker.py"), jf, tmp], env=e, cwd=jd, capture_output=True, text=True)
    shutil.rmtree(jd, ignore_errors=True)
    if not os.path.exists(tmp):
        raise RuntimeError(p.stderr[-3000:])
    os.replace(tmp, of)


def run(rname, split, nst, specs):
    cfgs = [parse(s) for s in specs]
    od = os.path.join(OUTR, rname); os.makedirs(od, exist_ok=True)
    json.dump({"split": split, "cfgs": specs}, open(os.path.join(od, "_cfg.json"), "w"), ensure_ascii=False)
    cs = E.cards(split)
    sids = sorted({c["store"] for c in cs})[:nst]
    for k, sid in enumerate(sids):
        st = E.T()["S"][sid]
        qs = [{"qid": c["qid"], "q": c["question"], "limit": 100} for c in cs if c["store"] == sid]
        order = cfgs if k % 2 == 0 else cfgs[::-1]
        for name, root, env in order:
            of = os.path.join(od, f"{name}_{sid}.json")
            if os.path.exists(of):
                continue
            pre = env.pop("_PREFETCH", None) == "1"
            one(st, qs, root, env, of, pre)
            if pre:
                env["_PREFETCH"] = "1"
            print(name, sid, flush=True)
    open(os.path.join(od, "done"), "w").close()


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p
    f = int(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def show(rname, names=None):
    od = os.path.join(OUTR, rname)
    files = sorted(f for f in os.listdir(od) if f.endswith(".json") and not f.startswith("_"))
    by = {}
    for f in files:
        name, sid = f[:-5].rsplit("_", 1)
        by.setdefault(name, {})[sid] = json.load(open(os.path.join(od, f), encoding="utf-8"))
    names = names or sorted(by)
    common = set.intersection(*[set(by[n]) for n in names if n in by])
    res = {}
    for n in names:
        R = [by[n][s] for s in sorted(common)]
        c = [x for r in R for x in r["pass"][0]["ms"]]; w = [x for r in R for x in r["pass"][1]["ms"]]
        res[n] = {"stores": len(R), "nq": len(c), "cold_p50": pct(c, .5), "cold_p95": pct(c, .95), "cold_mean": statistics.mean(c),
                  "warm_p50": pct(w, .5), "warm_p95": pct(w, .95), "load_ms": statistics.mean(r["load_ms"] for r in R),
                  "write_ms": statistics.mean(r["write_ms"] for r in R), "prefetch_ms": statistics.mean(r.get("prefetch_ms", 0) for r in R),
                  "warm_same_rank": all(r["pass"][0]["rank"] == r["pass"][1]["rank"] for r in R)}
        print(f"{n:10s} 库{len(R)} 题{len(c)} 冷 p50 {res[n]['cold_p50']:.0f} p95 {res[n]['cold_p95']:.0f} 均 {res[n]['cold_mean']:.0f} | 热 p50 {res[n]['warm_p50']:.1f} p95 {res[n]['warm_p95']:.1f} | 载入 {res[n]['load_ms']:.0f} 建库 {res[n]['write_ms']:.0f} 预取 {res[n]['prefetch_ms']:.0f} ms")
    # 名次逐位比较（冷遍）
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            diff = [q for s in common for q, r in by[a][s]["pass"][0]["rank"].items() if by[b][s]["pass"][0]["rank"].get(q) != r]
            print(f"  名次 {a} vs {b}：不同 {len(diff)} 题")
            res[f"diff:{a}:{b}"] = sorted(diff)
    json.dump(res, open(os.path.join(od, "_summary.json"), "w"), ensure_ascii=False, indent=1)
    return res


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5:])
    else:
        show(sys.argv[2], sys.argv[3:] or None)
