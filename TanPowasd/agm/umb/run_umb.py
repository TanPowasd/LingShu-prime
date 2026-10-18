# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""UMB v0.1 统一跑器（零模型、零 key、单核顺序）。
用法：python -X utf8 run_umb.py --arms bm25,zh --split dev|test|all [--sets a,b] [--limit N] [--budget-secs S]
  · 每集在独立子进程里顺序跑（单核，不并行），子进程结束即释放内存；峰值内存取子进程 ru_maxrss。
  · 题表读本目录冻结文件；检索集语料读 $UMB_OUT/<集>/corpus.jsonl（build_umb.py 重建）；记忆集源经 UMB_LME/UMB_LOCOMO/UMB_HIVE 解析。
  · 逐题结果缓存在 $UMB_OUT/runs/<split>/<集>/<臂>.json（dev/test 各一个目录；--split all 跑两者），断点续跑：已算过的题跳过。
  · --budget-secs：子进程跑到该秒数即存盘退出，下次同命令续跑（后台单任务 ≤1200s 时用）。
  · 汇总：每集主指标（检索集 nDCG@10、记忆集 r@10）、12 集等权宏平均、记忆/英文/中文组宏平均、
    每集与合并的配对符号检验（各臂 vs bm25），写 $UMB_OUT/runs/summary_<split>[_lim<N>].json/.md。
臂（全部复用现有实现，不重写指标）：
  bm25   xbench bench_ir.Okapi（k1=.9 b=.4，拉丁小写整词 + 汉字二元组，T.seq_tokens(cjk="bigram")），文档/轮级
  zh     zh.ZhMemory()（默认：ra=True、rm3=False），zh 打分、不扩散；检索集 = bench_ir 的 "zh" 臂；记忆集 = 块分→轮（bench_cc "/单" 用法）
  ra_zh  可选：zh 打分 + RA-AGM 扩散（检索集 = bench_ir "ra_zh"；记忆集 = bench_zh 路径 dedup(rank_agm)）
指标：检索集 bench_ir.metrics；LME/LoCoMo lme_zerokey.score；hive = bench_cc 口径（8000 字上下文证据句完整出现比例记为 r@10）。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":           # 固定字符串哈希 ⇒ 集合迭代序/同分并列序可复现
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)

import argparse, collections, hashlib, json, pathlib, resource, subprocess, time

UMB = pathlib.Path(__file__).resolve().parent         # 冻结题表（入库）
AGM = UMB.parent
sys.path.insert(0, str(UMB))
import build_umb as B  # noqa: E402
sys.path[:0] = [str(AGM / d) for d in ("xbench", "bench", "lex", "zh", "tricue")]
RUNS = B.OUT / "runs"
ARMS_OK = ("bm25", "zh", "ra_zh", "te", "dgc3a", "fm8b")
TE_ARMS = ("te", "dgc3a", "fm8b")   # 拉丁管线 Lex→RA→FD→TE（LEX_RM3=0），DGC3a=dist.ARMS2，FM8b=fdm.ARMS；PREREG_dist2/fdm 原实现
MEM = ("lme", "locomo", "hive")
SAVE_EVERY = 30.0
STORE = "compact"   # 块打分器存储：compact = lex/compact.py 紧凑倒排（打分逐位相同，守卫 test_compact.py）；dict = 原 LexScorer


def sha_file(p):
    x = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            x.update(b)
    return x.hexdigest()


def manifest():
    return json.loads((UMB / "manifest.json").read_text(encoding="utf-8"))


def qids_for(name, split, limit):
    sp = json.loads((UMB / name / "split.json").read_text(encoding="utf-8"))
    q = sp[split]
    return q[:limit] if limit else q


def read_queries(name):
    out = {}
    with open(UMB / name / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line); out[o["_id"]] = o
    return out


def read_qrels(name):
    r = collections.defaultdict(dict)
    with open(UMB / name / "qrels.tsv", encoding="utf-8") as f:
        for line in f:
            q, d, s = line.rstrip("\n").split("\t"); r[q][d] = int(s)
    return r


class Cache:
    def __init__(self, split, name, arm):
        self.p = RUNS / split / name / f"{arm}.json"
        self.p.parent.mkdir(parents=True, exist_ok=True)
        self.d = json.loads(self.p.read_text(encoding="utf-8")) if self.p.exists() else {"meta": {"set": name, "arm": arm, "split": split, "runs": []}, "per": {}}
        self.dirty = False

    def has(self, q):
        return q in self.d["per"]

    def put(self, q, row):
        self.d["per"][q] = row; self.dirty = True

    def save(self):
        tmp = self.p.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.p); self.dirty = False


# ---------------------------------------------------------------- 子进程：跑一集
def run_one(name, arms, split, limit, budget):
    import bench_ir as BI
    import tricue as T
    import zh
    import compact
    from bench_lex import dedup
    from lme_zerokey import score
    t_start = time.time()
    man = manifest()["sets"][name]
    if man.get("status") != "ok":
        print(name, "存疑：manifest 状态", man.get("status")); return
    for p, s in man["sources"].items():                    # 源文件指纹核对（记忆集不复制语料）
        if p == "commit" or man["kind"] != "memory":
            continue
        rp = B.resolve(p)
        if not rp.exists():
            print(name, "存疑：源文件不存在（lme 可回退官方原始文件，以逐题断言核对）", p, flush=True)
        elif sha_file(rp) != s:
            print(name, "存疑：源文件 sha256 不符", p); return
    if man["kind"] == "retrieval" and not (B.OUT / name / "corpus.jsonl").exists():
        print(name, "存疑：缺 $UMB_OUT/%s/corpus.jsonl，先跑 build_umb.py" % name); return
    splits = ("dev", "test") if split == "all" else (split,)
    todo = {sp: qids_for(name, sp, limit) for sp in splits}
    caches = {(sp, a): Cache(sp, name, a) for sp in splits for a in arms}
    need = {a: [(sp, q) for sp in splits for q in todo[sp] if not caches[(sp, a)].has(q)] for a in arms}
    n_new = collections.Counter()
    if not any(need.values()):
        print(name, "全部已缓存"); return
    cjk = zh.ZhMemory().cjk
    queries, qrels = read_queries(name), read_qrels(name)
    need_q = [q for sp in splits for q in todo[sp] if any(not caches[(sp, a)].has(q) for a in arms)]
    spl = {q: sp for sp in splits for q in todo[sp]}
    last = [time.time()]
    stop = [False]

    def flush(force=False):
        if force or time.time() - last[0] > SAVE_EVERY:
            for c in caches.values():
                if c.dirty:
                    c.save()
            last[0] = time.time()
        if budget and time.time() - t_start > budget:
            stop[0] = True

    def rec(q, a, row, t):
        row["t"] = round(t, 4)
        caches[(spl[q], a)].put(q, row); n_new[a] += 1

    def okapi_rank(texts, q):
        ok = BI.Okapi()
        for t in texts:
            ok.add(T.seq_tokens(t, cjk))
        o = [d for d, _ in sorted(ok.score(T.seq_tokens(q, cjk)).items(), key=lambda x: -x[1])]
        s = set(o)
        return o + [i for i in range(len(texts)) if i not in s]

    def new_zh():
        m = zh.ZhMemory()
        return compact.compact(m) if STORE == "compact" else m

    def zh_build(texts):
        m = new_zh()
        for t in texts:
            m.add_turn("user", t)
        return m

    def zh_ranks(m, q, n, which):
        sc = m.bm25(q)
        out = {}
        if "zh" in which:
            out["zh"] = dedup(sorted(sc, key=lambda c: (-sc[c], c)), m.turn_of, n)
        if "ra_zh" in which:
            out["ra_zh"] = dedup(m.rank_agm(sc), m.turn_of, n)
        return out

    def te_build(texts, roles=None, sess=None):
        os.environ["LEX_RM3"] = "0"
        import bench_cc as BC
        BC.ARMS = ["role", "fd2", "tree", "dist", "dist2", "fdm"]
        m = BC.build(texts, roles, sess if sess is not None else list(range(len(texts))))
        import tree as TR
        m._tg["TE"] = TR.build(m, m._sess, speakers=m._spk, **TR.ARMS["TE"])
        return m

    def te_ranks(m, q, n, which):
        import lex as LX, tree as TR, dist as DI, fdm as FM
        if not DI.TABLE:
            DI.load()
        base = LX.LexMemory.bm25(m, q); g = m._tg["TE"]; out = {}
        if "te" in which:
            out["te"] = TR.rank(g, base)
        if "dgc3a" in which:
            out["dgc3a"] = TR.rank(g, DI.score(m, base, q, **DI.ARMS2["DGC3a"]))
        if "fm8b" in which:
            out["fm8b"] = TR.rank(g, FM.score(m, base, q, **FM.ARMS["FM8b"]))
        return {k: dedup(v, m.turn_of, n) for k, v in out.items()}

    def ranks(m, mt, texts, q, n, a):
        if a == "bm25":
            return okapi_rank(texts, q)
        if a in TE_ARMS:
            return te_ranks(mt, q, n, (a,))[a]
        return zh_ranks(m, q, n, (a,))[a]

    t_idx = 0.0
    want = lambda q: [a for a in arms if not caches[(spl[q], a)].has(q)]
    if man["kind"] == "retrieval":
        ti = time.time()
        docs = []
        with open(B.OUT / name / "corpus.jsonl", encoding="utf-8") as f:
            for line in f:
                o = json.loads(line)
                docs.append((o["_id"], ((o.get("title") or "") + "\n" + (o.get("text") or "")).strip()))   # 同 bench_ir.load
        ids = [d for d, _ in docs]
        m = ok = None
        if any(need[a] for a in ("zh", "ra_zh") if a in arms):
            m = new_zh()
        if need.get("bm25"):
            ok = BI.Okapi()
        mt = te_build([t for _, t in docs]) if any(need.get(a) for a in TE_ARMS) else None
        for _, t in docs:
            if m is not None:
                m._last_chunk = None          # 同 bench_ir：每篇文档独立
                m.add_turn("user", t)
            if ok is not None:
                ok.add(T.seq_tokens(t, cjk))
        del docs
        t_idx = time.time() - ti
        print(f"{name} index {len(ids)} docs {t_idx:.1f}s maxrss {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f}MB", flush=True)
        for q in need_q:
            text, rel = queries[q]["text"], qrels[q]
            for a in want(q):
                t0 = time.time()
                if a == "bm25":
                    r = [ids[d] for d, _ in sorted(ok.score(T.seq_tokens(text, cjk)).items(), key=lambda x: -x[1])[:1000]]
                elif a == "zh":
                    s = m.bm25(text); r = [ids[d] for d in BI.doc_order(m, sorted(s, key=lambda c: -s[c]))[:1000]]
                elif a in TE_ARMS:
                    r = [ids[d] for d in te_ranks(mt, text, len(ids), (a,))[a][:1000]]
                else:
                    s = m.bm25(text); r = [ids[d] for d in BI.doc_order(m, m.rank_agm(s))[:1000]]
                r = [d for d in r if d != q]       # BEIR 惯例（ArguAna）
                row = BI.metrics(r, rel); row["top10"] = r[:10]
                rec(q, a, row, time.time() - t0)
            flush()
            if stop[0]:
                break
    elif name == "hive":
        import hive_retrieval as HR
        HIVE = B.resolve(json.loads((UMB / "hive" / "source.json").read_text(encoding="utf-8"))["repo"])
        ti = time.time()
        chunks = HR.load_chunks(HIVE)
        texts = [c["text"] for c in chunks]
        gq = json.loads((UMB / "hive" / "gold_quotes.json").read_text(encoding="utf-8"))
        m = zh_build(texts) if any(a in arms for a in ("zh", "ra_zh")) else None
        mt = te_build(texts) if any(a in arms for a in TE_ARMS) else None
        t_idx = time.time() - ti
        for q in need_q:
            ps = list(gq[q].values()); text = queries[q]["text"]
            for a in want(q):
                t0 = time.time()
                o = ranks(m, mt, texts, text, len(chunks), a)
                row = {}
                for b in (2000, 4000, 8000):
                    row[f"@{b}"] = sum(x in HR.take(o, chunks, b) for x in ps) / len(ps)
                row["r@10"] = row["@8000"]            # bench_cc：hive 的 r@k 均记 8000 字预算下的证据完整率
                row["top10"] = o[:10]
                rec(q, a, row, time.time() - t0)
            flush()
            if stop[0]:
                break
    elif name == "locomo":
        from build_umb import locomo_conv_items, locomo_gold
        by = collections.defaultdict(list)
        for q in need_q:
            by[queries[q]["sid"]].append(q)
        for it in locomo_conv_items():
            if it["sid"] not in by:
                continue
            ti = time.time()
            n = len(it["turns"]); idx = {d: i for i, d in enumerate(it["ids"])}
            m = zh_build(it["turns"]) if any(a in arms for a in ("zh", "ra_zh")) else None
            mt = te_build(it["turns"], None, [int(str(d).split(":")[0].lstrip("D") or 0) for d in it["ids"]]) if any(a in arms for a in TE_ARMS) else None
            t_idx += time.time() - ti
            for q in by[it["sid"]]:
                qa = it["qa"][queries[q]["qi"]]
                gold = {idx[e] for e in locomo_gold(it, qa)}
                assert {it["ids"][g] for g in gold} == set(qrels[q]), q
                for a in want(q):
                    t0 = time.time()
                    o = ranks(m, mt, it["turns"], qa["question"], n, a)
                    row = score(o, gold); row["top10"] = o[:10]
                    rec(q, a, row, time.time() - t0)
                flush()
                if stop[0]:
                    break
            if stop[0]:
                break
    elif name == "lme":
        by = collections.defaultdict(list)
        for q in need_q:
            by[queries[q]["src"]].append(q)
        for fn in sorted(by):
            data = B.lme_part(int(fn[len("part"):-len(".json")]))   # partK.json
            for q in by[fn]:
                it = data[queries[q]["idx"]]
                assert it["question_id"] == q
                texts, gold, roles, sids = [], set(), [], []
                for si, sess in enumerate(it["haystack_sessions"]):       # 同 lme_zerokey
                    for t in sess:
                        roles.append(t["role"]); sids.append(si)
                        if t.get("has_answer"):
                            gold.add(len(texts))
                        texts.append(f"{t['role']}: {t['content']}")
                assert {str(g) for g in gold} == set(qrels[q]), q
                w = want(q)
                ti = time.time()
                m = zh_build(texts) if any(a in w for a in ("zh", "ra_zh")) else None
                mt = te_build(texts, roles, sids) if any(a in w for a in TE_ARMS) else None
                tb = time.time() - ti; t_idx += tb
                for a in w:
                    t0 = time.time()
                    o = ranks(m, mt, texts, it["question"], len(texts), a)
                    row = score(o, gold); row["top10"] = o[:10]
                    rec(q, a, row, time.time() - t0 + (tb if a != "bm25" else 0))   # 记忆集每题建索引，计入该题耗时
                del m, mt
                flush()
                if stop[0]:
                    break
            del data
            if stop[0]:
                break
    flush(force=True)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    for c in caches.values():
        c.d["meta"]["runs"].append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "n_new": n_new[c.d["meta"]["arm"]], "secs_total": round(time.time() - t_start, 1),
                                    "secs_index": round(t_idx, 1), "maxrss_mb": round(rss), "limit": limit, "stopped_by_budget": stop[0]})
        c.save()
    print(f"{name} done new={dict(n_new)} secs={time.time()-t_start:.1f} index={t_idx:.1f}s maxrss={rss:.0f}MB stop={stop[0]}", flush=True)


# ---------------------------------------------------------------- 汇总
def summarize(arms, split, sets, limit):
    from agg_ir import sign_p
    man = manifest()
    splits = ("dev", "test") if split == "all" else (split,)
    res, pooled = {}, collections.defaultdict(lambda: [0, 0])
    for name in sets:
        info = man["sets"].get(name, {})
        if info.get("status") != "ok":
            res[name] = {"status": "存疑/缺失"}; continue
        met = info["metric"]
        qs = [q for sp in splits for q in qids_for(name, sp, limit)]
        per = {}
        for a in arms:
            d = {}
            for sp in splits:
                p = RUNS / sp / name / f"{a}.json"
                if p.exists():
                    d.update(json.loads(p.read_text(encoding="utf-8"))["per"])
            per[a] = d
        done = [q for q in qs if all(q in per[a] for a in arms)]
        if not done:
            res[name] = {"status": "未跑", "n_target": len(qs)}; continue
        row = {"status": "ok" if len(done) == len(qs) else "部分", "metric": met, "n": len(done), "n_target": len(qs), "group": info["group"],
               "score": {a: sum(per[a][q][met] for q in done) / len(done) for a in arms},
               "secs_per_q": {a: sum(per[a][q]["t"] for q in done) / len(done) for a in arms}, "sign_vs_bm25": {}}
        for a in arms:
            if a == "bm25" or "bm25" not in arms:
                continue
            w = sum(per[a][q][met] > per["bm25"][q][met] + 1e-12 for q in done)
            l = sum(per[a][q][met] < per["bm25"][q][met] - 1e-12 for q in done)
            row["sign_vs_bm25"][a] = {"win": w, "loss": l, "tie": len(done) - w - l, "p": sign_p(w, l)}
            pooled[a][0] += w; pooled[a][1] += l
        res[name] = row
    ok = {k: v for k, v in res.items() if v.get("status") in ("ok", "部分")}
    macro = lambda ks: {a: sum(ok[k]["score"][a] for k in ks) / len(ks) for a in arms} if ks else None
    groups = {g: [k for k in ok if ok[k]["group"] == g] for g in ("mem", "en", "zh")}
    out = {"split": split, "limit": limit, "arms": arms, "n_sets": len(ok), "sets_missing": [k for k in sets if k not in ok],
           "per_set": res, "macro_all": macro(list(ok)), "macro_group": {g: macro(ks) for g, ks in groups.items()},
           "macro_note": "等权宏平均（检索集 nDCG@10 与记忆集 r@10 混合，跨集只作相对比较）",
           "sign_pooled_vs_bm25": {a: {"win": w, "loss": l, "p": sign_p(w, l)} for a, (w, l) in pooled.items()}}
    tag = f"summary_{split}" + (f"_lim{limit}" if limit else "")
    RUNS.mkdir(exist_ok=True)
    (RUNS / f"{tag}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    f3 = lambda x: f"{x:.3f}"
    md = [f"# UMB v0.1 · split={split}" + (f" · 每集前 {limit} 题" if limit else ""), "",
          "| 集 | 组 | 指标 | 题数 | " + " | ".join(arms) + " | " + " | ".join(f"{a} vs bm25 胜/负/平 p" for a in arms if a != "bm25") + " |",
          "|---|---|---|---:|" + "---:|" * len(arms) + "---|" * (len(arms) - 1)]
    for k, v in res.items():
        if v.get("status") not in ("ok", "部分"):
            md.append(f"| {k} | | {v.get('status')} | | " + " | " * (2 * len(arms) - 1)); continue
        sg = " | ".join(f"{s['win']}/{s['loss']}/{s['tie']} p={s['p']:.2g}" for s in v["sign_vs_bm25"].values())
        md.append(f"| {k} | {v['group']} | {v['metric']} | {v['n']} | " + " | ".join(f3(v["score"][a]) for a in arms) + f" | {sg} |")
    if out["macro_all"]:
        md += ["", f"宏平均（{len(ok)} 集等权）：" + "，".join(f"{a} {f3(x)}" for a, x in out["macro_all"].items())]
        for g, mm in out["macro_group"].items():
            if mm:
                md.append(f"- {g}：" + "，".join(f"{a} {f3(x)}" for a, x in mm.items()))
        md.append("合并符号检验 vs bm25：" + "；".join(f"{a} {s['win']}/{s['loss']} p={s['p']:.2g}" for a, s in out["sign_pooled_vs_bm25"].items()))
    (RUNS / f"{tag}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="bm25,zh"); ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--sets"); ap.add_argument("--limit", type=int); ap.add_argument("--budget-secs", type=float)
    ap.add_argument("--one", help=argparse.SUPPRESS); ap.add_argument("--no-summary", action="store_true")
    ap.add_argument("--store", default="compact", choices=["compact", "dict"], help="块打分器存储（结果逐位相同，compact 省内存）")
    a = ap.parse_args()
    arms = a.arms.split(",")
    assert all(x in ARMS_OK for x in arms), arms
    if a.one:
        global STORE
        STORE = a.store
        run_one(a.one, arms, a.split, a.limit, a.budget_secs); return
    man = manifest()
    sets = a.sets.split(",") if a.sets else list(man["sets"])
    order = man["groups"]["mem"] + man["groups"]["en"] + man["groups"]["zh"]
    sets = sorted(sets, key=lambda s: order.index(s) if s in order else 99)
    t0 = time.time()
    for s in sets:
        if a.budget_secs and time.time() - t0 > a.budget_secs:
            print("预算用尽，余下集下次续跑"); break
        cmd = [sys.executable, "-X", "utf8", __file__, "--one", s, "--arms", a.arms, "--split", a.split, "--store", a.store]
        if a.limit:
            cmd += ["--limit", str(a.limit)]
        if a.budget_secs:
            cmd += ["--budget-secs", str(max(30.0, a.budget_secs - (time.time() - t0)))]
        r = subprocess.run(cmd)
        if r.returncode:
            print(s, "子进程失败 returncode", r.returncode, flush=True)
    if not a.no_summary:
        summarize(arms, a.split, sets, a.limit)


if __name__ == "__main__":
    main()
