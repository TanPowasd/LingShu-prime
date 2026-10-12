# -*- coding: utf-8 -*-
"""gen-v1 评测驱动（口径＝prime-test/work/item4_gen.py 的 ng 臂；切分见 PREREG.md）。

  python gen_eval.py prep                                   # 生成 /tmp/gen_jobs/{lme,loc}_{dev,test}.jsonl + meta
  python gen_eval.py run <tag> <set> [--root R] [--cfg JSON] [--np 2] [--limit N]
        set ∈ lme_dev / lme_test / loc_dev / loc_test；root＝被测 lingshu_ng 所在目录（缺省本 worktree）；
        cfg → 环境变量 LINGSHU_NG_LEXICAL（词面检索配置覆盖，JSON）。结果写 /tmp/gen_runs/<tag>/<set>.<i>.jsonl（断点续跑）
  python gen_eval.py score <tag> <set>                      # 逐题指标 → bench_gen/out/<tag>/<set>.json，打印均值
  python gen_eval.py cmp <tagA> <tagB|tc2|turn_sdm|...> <set>   # 逐题配对（bootstrap 95% + 符号检验）
  python gen_eval.py snap <rev>                             # git archive <rev> lingshu_ng → /tmp/ng-gen-<rev>
"""
import glob, hashlib, json, math, os, random, statistics, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(HERE)
LME = "/workspace/work/pes/taskpacks/longmemeval/raw/longmemeval_s_cleaned.json"
LOCOMO = "/workspace/work/ls/prime-test/data/locomo10.json"
ITEM4 = "/workspace/work/ls/prime-test/out/item4"
JOBS = "/tmp/gen_jobs"
RUNS = os.path.join(HERE, "runs")   # 断点续跑：沙箱重启会清空 /tmp
OUT = os.path.join(HERE, "out")
LIMIT = 60
LOC_DEV = {"conv-26", "conv-30", "conv-41"}


def dump(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)


def lme_split(qid):
    return "dev" if int(hashlib.md5(qid.encode()).hexdigest(), 16) % 10 in (0, 1) else "test"


def prep():
    os.makedirs(JOBS, exist_ok=True)
    d = json.load(open(LME, encoding="utf-8"))
    files = {s: open(os.path.join(JOBS, f"lme_{s}.jsonl"), "w", encoding="utf-8") for s in ("dev", "test")}
    meta = {"dev": {}, "test": {}}
    for x in d:
        if x["question_id"].endswith("_abs"):
            continue
        s = lme_split(x["question_id"])
        sess = sorted(zip(x["haystack_dates"], x["haystack_session_ids"], x["haystack_sessions"]), key=lambda z: z[0])
        turns, s_of, ans_t = [], [], set()
        for _, sid, ss in sess:
            for t in ss:
                if t.get("has_answer"):
                    ans_t.add(len(turns))
                turns.append(t["content"]); s_of.append(sid)
        keep = [i for i, t in enumerate(turns) if t.strip()]
        k2d = {k: j for j, k in enumerate(keep)}
        files[s].write(json.dumps({"key": x["question_id"], "docs": [turns[i] for i in keep],
                                   "queries": [{"qid": "q", "q": x["question"], "limit": LIMIT}]}, ensure_ascii=False) + "\n")
        meta[s][x["question_id"]] = {"type": x["question_type"], "s_of": [s_of[i] for i in keep],
                                     "ans": sorted(k2d[i] for i in ans_t if i in k2d), "ans_full": len(ans_t),
                                     "gold": x["answer_session_ids"]}
    for f in files.values():
        f.close()
    for s in meta:
        dump(os.path.join(JOBS, f"meta_lme_{s}.json"), meta[s])
    L = json.load(open(LOCOMO, encoding="utf-8"))
    files = {s: open(os.path.join(JOBS, f"loc_{s}.jsonl"), "w", encoding="utf-8") for s in ("dev", "test")}
    meta = {"dev": {}, "test": {}}
    for c in L:
        s = "dev" if c["sample_id"] in LOC_DEV else "test"
        conv = c["conversation"]
        n = sorted(int(k.split("_")[1]) for k in conv if k.startswith("session_") and not k.endswith("date_time"))
        turns, ids = [], []
        for i in n:
            for t in conv[f"session_{i}"]:
                txt = f"{t['speaker']}: {t['text']}"
                if t.get("blip_caption"):
                    txt += f" [image: {t['blip_caption']}]"
                turns.append(txt); ids.append(t["dia_id"])
        idx = {dd: i for i, dd in enumerate(ids)}
        qs, m = [], {}
        for qi, q in enumerate([q for q in c["qa"] if q.get("category") != 5]):
            ev = set()
            for e in q.get("evidence", []):
                for pp in str(e).replace(";", ",").split(","):
                    pp = pp.strip()
                    if pp in idx:
                        ev.add(idx[pp])
            if ev:
                qs.append({"qid": str(qi), "q": q["question"], "limit": LIMIT})
                m[str(qi)] = {"cat": q["category"], "ev": sorted(ev)}
        files[s].write(json.dumps({"key": c["sample_id"], "docs": turns, "queries": qs}, ensure_ascii=False) + "\n")
        meta[s][c["sample_id"]] = m
    for f in files.values():
        f.close()
    for s in meta:
        dump(os.path.join(JOBS, f"meta_loc_{s}.json"), meta[s])
    print({k: len(v) for k, v in meta.items()})


def run(tag, sset, root=None, cfg=None, np_=2, limit=None, sweep=None):
    root = root or WT
    jf = os.path.join(JOBS, f"{sset}.jsonl")
    lines = [x for x in open(jf, encoding="utf-8").read().split("\n") if x.strip()]
    if limit:
        lines = lines[:limit]
    os.makedirs(os.path.join(RUNS, tag), exist_ok=True)
    env = dict(os.environ, PYTHONPATH=root, PYTHONHASHSEED="0")
    for k in ("LINGSHU_NG_MEMORY_BACKEND", "LINGSHU_NG_EMBED_MODEL", "LINGSHU_NG_LEXICAL"):
        env.pop(k, None)
    if cfg:
        env["LINGSHU_NG_LEXICAL"] = cfg
    if os.environ.get("GEN_EMBED"):              # r7：语义第二路（模型目录）与向量缓存
        env["LINGSHU_NG_EMBED_MODEL"] = os.environ["GEN_EMBED"]
        env["LINGSHU_NG_EMBED_CACHE"] = os.environ.get("GEN_EMBED_CACHE", "/workspace/work/ls/_shared/models/_vec_cache")
    if os.environ.get("G1_FROZEN_CLOCK"):          # 确定性模式（结构核对用）：clockshim 钉住 time.time 与 os.urandom
        env["PYTHONPATH"] = os.path.join(HERE, "clockshim") + os.pathsep + root
    if os.environ.get("GEN_PATCH_DEFAULT"):
        env["GEN_PATCH_DEFAULT"] = os.environ["GEN_PATCH_DEFAULT"]
    if sweep:
        env["GEN_SWEEP"] = open(sweep).read() if os.path.exists(sweep) else sweep
    dump(os.path.join(RUNS, tag, "run_meta.json"), {"root": root, "cfg": cfg, "set": sset, "sweep": env.get("GEN_SWEEP"), "patch_default": env.get("GEN_PATCH_DEFAULT"),
                                                     "frozen_clock": os.environ.get("G1_FROZEN_CLOCK"), "embed": os.environ.get("GEN_EMBED")})
    procs = []
    for i in range(np_):
        sh = os.path.join(RUNS, tag, f"{sset}.jobs{i}.jsonl")
        with open(sh, "w", encoding="utf-8") as f:
            f.write("\n".join(lines[i::np_]) + "\n")
        out = os.path.join(RUNS, tag, f"{sset}.{i}.jsonl")
        procs.append(subprocess.Popen([sys.executable, "-X", "utf8", os.path.join(HERE, "gen_worker.py"), sh, out],
                                      env=env, cwd="/tmp", stderr=open(os.path.join(RUNS, tag, f"{sset}.{i}.err"), "a")))
    for p in procs:
        p.wait()
    print("done", tag, sset, [p.returncode for p in procs])


def results(tag, sset):
    R = {}
    name = None
    if "@" in tag:
        tag, name = tag.split("@", 1)
    for f in glob.glob(os.path.join(RUNS, tag, f"{sset}.[0-9]*.jsonl")):
        for line in open(f, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if name is not None:
                r["rank"] = r["rank"].get(name, {})
            R[r["key"]] = r
    return R


def sweep_score(tag, sset, main=None):
    """扫描结果：对每个配置名打分，按主指标排序打印。"""
    meta = json.load(open(os.path.join(RUNS, tag, "run_meta.json")))
    names = list(json.loads(meta["sweep"]))
    rows = []
    for nm in names:
        r = score(f"{tag}@{nm}", sset, quiet=True)
        rows.append((nm, r["mean"], r["n"]))
    k = main or ("s@5" if sset.startswith("lme") else "r@10")
    for nm, m, n in sorted(rows, key=lambda x: -x[1].get(k, 0)):
        print(f"{nm:40s} n={n} " + " ".join(f"{kk}={v:.4f}" for kk, v in m.items()))


def score(tag, sset, quiet=False):
    R = results(tag, sset)
    data, split = sset.split("_")
    meta = json.load(open(os.path.join(JOBS, f"meta_{data}_{split}.json"), encoding="utf-8"))
    per, lat = {}, []
    if data.startswith("lme"):
        for qid, m in meta.items():
            if qid not in R:
                continue
            order = R[qid]["rank"]["q"]
            so, seen = [], set()
            for t in order:
                s = m["s_of"][t]
                if s not in seen:
                    seen.add(s); so.append(s)
            gold, ans = set(m["gold"]), set(m["ans"])
            per[qid] = {"type": m["type"], "s@5": float(bool(gold & set(so[:5]))), "s@10": float(bool(gold & set(so[:10]))),
                        "t@10": float(bool(ans & set(order[:10]))) if m["ans_full"] else None,
                        "t@50": float(bool(ans & set(order[:50]))) if m["ans_full"] else None}
            lat.append((1000 * R[qid]["write_sec"] / max(1, R[qid]["n_docs"]), R[qid]["query_ms"][0]))
        keys = ("s@5", "s@10", "t@10", "t@50")
    else:
        for cid, mm in meta.items():
            if cid not in R:
                continue
            for qi, m in mm.items():
                o = R[cid]["rank"][qi]
                ev = set(m["ev"])
                per[f"{cid}/{qi}"] = {"cat": m["cat"], **{f"r@{k}": len(ev & set(o[:k])) / len(ev) for k in (5, 10, 25)}}
                if data.startswith("cm"):   # r5 轮级（ConvoMem）：任一证据入前 k（= LME t@k 同型）、全部证据入前 10
                    per[f"{cid}/{qi}"].update({"hit@5": float(bool(ev & set(o[:5]))), "hit@10": float(bool(ev & set(o[:10]))),
                                               "all@10": float(ev <= set(o[:10]))})
            lat.append((1000 * R[cid]["write_sec"] / R[cid]["n_docs"], statistics.median(R[cid]["query_ms"])))
        keys = ("r@5", "r@10", "r@25") + (("hit@5", "hit@10", "all@10") if data.startswith("cm") else ())
    n_exp = sum(len(v) for v in meta.values()) if not data.startswith("lme") else len(meta)
    agg = {k: round(statistics.mean(v[k] for v in per.values() if v[k] is not None), 4) for k in keys} if per else {}
    grp = "type" if data.startswith("lme") else "cat"
    main = "s@5" if data.startswith("lme") else "r@10"
    by = {str(g): round(statistics.mean(v[main] for v in per.values() if v[grp] == g), 4) for g in sorted({v[grp] for v in per.values()}, key=str)}
    res = {"tag": tag, "set": sset, "n": len(per), "n_expected": n_exp, "mean": agg, f"by_{grp}.{main}": by,
           "write_ms_per_doc_median": round(statistics.median(x[0] for x in lat), 3) if lat else None,
           "query_ms_median": round(statistics.median(x[1] for x in lat), 2) if lat else None,
           "run_meta": json.load(open(os.path.join(RUNS, tag.split("@")[0], "run_meta.json"))) if os.path.exists(os.path.join(RUNS, tag.split("@")[0], "run_meta.json")) else None,
           "per": per}
    dump(os.path.join(OUT, tag.replace("@", "/sweep/"), f"{sset}.json"), res)
    if quiet:
        return res
    print(json.dumps({k: res[k] for k in ("tag", "set", "n", "n_expected", "mean", f"by_{grp}.{main}", "write_ms_per_doc_median", "query_ms_median")}, ensure_ascii=False))
    return res


TEAM_ARMS = ("v11", "tc11s", "tc2b", "tc2", "tc2r", "turn_v1", "turn_sdm", "ng")


def team_per(arm, sset):
    """队友各臂 + 旧 ng 臂在 item4（prime-test）中的逐题读数，按本切分取子集。"""
    data, split = sset.split("_")
    per = {}
    if data == "lme":
        meta = json.load(open(os.path.join(JOBS, f"meta_lme_{split}.json"), encoding="utf-8"))
        for f in glob.glob(os.path.join(ITEM4, "lme", "*.json")):
            r = json.load(open(f, encoding="utf-8"))
            if r["id"] in meta:
                per[r["id"]] = {k: (None if v is None else float(v)) for k, v in r["res"][arm].items()}
    else:
        meta = json.load(open(os.path.join(JOBS, f"meta_loc_{split}.json"), encoding="utf-8"))
        for cid in meta:
            f = os.path.join(ITEM4, "locomo", f"{cid}.json")
            if not os.path.exists(f):
                continue
            r = json.load(open(f, encoding="utf-8"))
            for qi, row in zip(meta[cid], r["rows"]):
                per[f"{cid}/{qi}"] = row["res"][arm]
    return per


def per_of(tag, sset):
    if tag.startswith("item4:"):
        return team_per(tag[6:], sset)
    return json.load(open(os.path.join(OUT, tag.replace("@", "/sweep/"), f"{sset}.json"), encoding="utf-8"))["per"]


def boot(d, n=10000, seed=0):
    import numpy as np
    d = np.asarray(d, float)
    rng = np.random.default_rng(seed)
    m = d[rng.integers(0, len(d), (n, len(d)))].mean(1)
    return [round(float(d.mean()), 4), round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]


def sign(a, b):
    w = sum(x > y for x, y in zip(a, b)); l = sum(x < y for x, y in zip(a, b)); n = w + l
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(w, l) + 1)) / 2 ** n) if n else 1.0
    return {"win": w, "loss": l, "tie": len(a) - n, "p": round(p, 4)}


def cmp(a, b, sset, keys=None):
    A, B = per_of(a, sset), per_of(b, sset)
    keys = keys or (("s@5", "s@10", "t@10", "t@50") if sset.startswith("lme") else ("r@5", "r@10", "r@25"))
    out = {}
    for k in keys:
        qs = sorted(q for q in A if q in B and A[q].get(k) is not None and B[q].get(k) is not None)
        x, y = [float(A[q][k]) for q in qs], [float(B[q][k]) for q in qs]
        if qs:
            out[k] = {"n": len(qs), "a": round(statistics.mean(x), 4), "b": round(statistics.mean(y), 4),
                      "diff_ci95": boot([i - j for i, j in zip(x, y)]), **sign(x, y)}
    print(a, "vs", b, sset, json.dumps(out, ensure_ascii=False))
    return out


def snap(rev):
    d = f"/tmp/ng-gen-{rev}"
    if not os.path.exists(os.path.join(d, "lingshu_ng")):
        os.makedirs(d, exist_ok=True)
        subprocess.run(f"git -C {WT} archive {rev} lingshu_ng | tar -x -C {d}", shell=True, check=True)
    print(d)
    return d


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "prep":
        prep()
    elif a[0] == "run":
        kw = {}
        for i, x in enumerate(a):
            if x == "--root": kw["root"] = a[i + 1]
            if x == "--cfg": kw["cfg"] = a[i + 1]
            if x == "--np": kw["np_"] = int(a[i + 1])
            if x == "--limit": kw["limit"] = int(a[i + 1])
            if x == "--sweep": kw["sweep"] = a[i + 1]
        run(a[1], a[2], **kw)
    elif a[0] == "score":
        score(a[1], a[2])
    elif a[0] == "sweep":
        sweep_score(a[1], a[2])
    elif a[0] == "cmp":
        cmp(a[1], a[2], a[3])
    elif a[0] == "snap":
        snap(a[1])
