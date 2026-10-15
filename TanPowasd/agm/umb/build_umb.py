# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""UMB v0.1「大一统检索测试集」构建（零模型、零 key、单进程）。
用法：python -X utf8 build_umb.py [--sets a,b,...] [--freeze]
  默认全部 12 集；产物写到 $UMB_OUT（默认 <仓根>/TanPowasd/agm/umb/data，不入库），含检索集 corpus.jsonl。
  每集建完逐文件与仓内冻结清单 manifest.json 的 sha256 比对并打印「一致/不一致」（重建即校验）。
  --freeze：把本次产物（除 corpus.jsonl）与 manifest 写回本目录——只在发新版本时用，v0.1 冻结后不要用。
外部数据（环境变量，见 README）：UMB_BEIR、UMB_CMTEB、UMB_LME、UMB_HIVE、UMB_LOCOMO；只有建到对应集时才要求设置。
规则：
  1. 每集 ≤500 题：只取有正相关金标的题，按 sha256("umb-v0.1|"+集名+"|"+qid) 升序取前 500。
  2. 检索集语料：500 题的全部金标文档 + 其余文档按 sha256("umb-v0.1|"+集名+"|"+docid) 升序补入，
     补到下一篇会让总字符数（len(title)+len(text)）超过 6,000,000 即停；原语料不足则全保留。
     corpus.jsonl 按原语料顺序写出；doc_ids.txt 为同序文档号（入库，corpus.jsonl 不入库、由本脚本重建）。
  3. split：sha256("umb-split|"+qid) 首字节偶数 → dev，奇数 → test。
  4. 记忆集不复制语料：source.json 记源文件（${变量}/相对路径）+ sha256 + 题号；queries.jsonl / qrels.tsv / split.json 照常写。
"""
import argparse, collections, glob, hashlib, json, os, pathlib, shutil, subprocess, sys, time

UMB = pathlib.Path(__file__).resolve().parent          # <仓根>/TanPowasd/agm/umb
AGM = UMB.parent                                        # <仓根>/TanPowasd/agm
OUT = pathlib.Path(os.environ.get("UMB_OUT") or (UMB / "data"))
MAXQ, MAXCH = 500, 6_000_000
HIVE_COMMIT = "f4509d7282f82982af5de9c8fe71863fc95b38cb"
REPO_EXCLUDES = ("corpus.jsonl",)                       # 不入库、由 build 重建的产物
PATH_VARS = {
    "UMB_BEIR": "BEIR 官方 zip 解压目录（含 scifact/ nfcorpus/ arguana/ scidocs/）",
    "UMB_CMTEB": "C-MTEB 检索集转 BEIR 格式后的目录（含 EcomRetrieval/ 等，见 xbench/fetch.py）",
    "UMB_LME": "LongMemEval-S 目录：part0-2.json，或官方 longmemeval_s_cleaned.json（自动按 n%3 拆）",
    "UMB_HIVE": "hive-memory-bench 克隆（commit f4509d7）",
    "UMB_LOCOMO": "locomo10.json 文件路径",
}

RETR = {  # 集名 → (环境变量, 子目录, qrels split, 组)
    "scifact": ("UMB_BEIR", "scifact", "test", "en"), "nfcorpus": ("UMB_BEIR", "nfcorpus", "test", "en"),
    "arguana": ("UMB_BEIR", "arguana", "test", "en"), "scidocs": ("UMB_BEIR", "scidocs", "test", "en"),
    "EcomRetrieval": ("UMB_CMTEB", "EcomRetrieval", "dev", "zh"), "VideoRetrieval": ("UMB_CMTEB", "VideoRetrieval", "dev", "zh"),
    "MedicalRetrieval": ("UMB_CMTEB", "MedicalRetrieval", "dev", "zh"), "DuRetrieval": ("UMB_CMTEB", "DuRetrieval", "dev", "zh"),
    "MMarcoRetrieval": ("UMB_CMTEB", "MMarcoRetrieval", "dev", "zh"),
}
MEM = ("lme", "locomo", "hive")
ALL = list(MEM) + list(RETR)


# ---------------- 路径：${变量}/相对路径 ----------------
def env_root(var):
    v = os.environ.get(var)
    if not v:
        raise SystemExit(f"需要环境变量 {var}：{PATH_VARS[var]}（见 README）")
    return pathlib.Path(v).expanduser()


def tok(var, rel=""):
    return "${" + var + "}" + (f"/{rel}" if rel else "")


def resolve(t):
    """'${UMB_BEIR}/scifact/corpus.jsonl' → 实际路径；变量未设 ⇒ SystemExit（不静默跳过）。"""
    if not t.startswith("${"):
        raise ValueError(f"非 ${{变量}} 形式路径：{t}")
    var, _, rel = t[2:].partition("}")
    root = env_root(var)
    return root / rel.lstrip("/") if rel else root


def h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha_file(p):
    x = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            x.update(b)
    return x.hexdigest()


def qkey(name, qid):
    return h(f"umb-v0.1|{name}|{qid}")


def split_of(qid):
    return "dev" if hashlib.sha256(f"umb-split|{qid}".encode("utf-8")).digest()[0] % 2 == 0 else "test"


def pick(name, qids):
    return sorted(qids, key=lambda q: qkey(name, q))[:MAXQ]


def write_common(d, name, queries, qrels, extra_q=None):
    """queries: {qid: text}; qrels: {qid: {docid: score}}；按哈希序写出。"""
    d.mkdir(parents=True, exist_ok=True)
    order = sorted(queries, key=lambda q: qkey(name, q))
    with open(d / "queries.jsonl", "w", encoding="utf-8") as f:
        for q in order:
            o = {"_id": q, "text": queries[q]}
            if extra_q:
                o.update(extra_q[q])
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    with open(d / "qrels.tsv", "w", encoding="utf-8") as f:
        for q in order:
            for doc, s in sorted(qrels[q].items()):
                f.write(f"{q}\t{doc}\t{s}\n")
    sp = {"dev": [q for q in order if split_of(q) == "dev"], "test": [q for q in order if split_of(q) == "test"],
          "rule": 'sha256("umb-split|"+qid)[0] % 2 == 0 -> dev'}
    (d / "split.json").write_text(json.dumps(sp, ensure_ascii=False, indent=0), encoding="utf-8")
    return len(sp["dev"]), len(sp["test"])


# ---------------- 检索集 ----------------
def retr_paths(name):
    var, sub, qsplit, _ = RETR[name]
    return {"corpus": tok(var, f"{sub}/corpus.jsonl"), "queries": tok(var, f"{sub}/queries.jsonl"),
            "qrels": tok(var, f"{sub}/qrels/{qsplit}.tsv")}


def retr_candidates(name):
    """有正相关金标的全部题：(qtext, qrels)。与 xbench bench_ir.load 同一解析。"""
    P = retr_paths(name)
    qrels = collections.defaultdict(dict)
    with open(resolve(P["qrels"]), encoding="utf-8") as f:
        for i, line in enumerate(f):
            p = line.rstrip("\n").split("\t")
            if len(p) < 3 or (i == 0 and not p[-1].lstrip("-").isdigit()):
                continue
            if int(p[-1]) > 0:
                qrels[p[0]][p[1]] = int(p[-1])
    qtext = {}
    with open(resolve(P["queries"]), encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            if str(o["_id"]) in qrels:
                qtext[str(o["_id"])] = o["text"]
    return qtext, qrels


def build_retr(name):
    _, _, qsplit, grp = RETR[name]
    P = retr_paths(name)
    corpus = resolve(P["corpus"])
    qtext, qrels = retr_candidates(name)
    sel = pick(name, list(qtext))
    gold = {d for q in sel for d in qrels[q]}
    # 第一遍：只记 id、字数、哈希
    meta, gold_chars, seen_gold = [], 0, set()
    with open(corpus, encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            did = str(o["_id"]); n = len(o.get("title") or "") + len(o.get("text") or "")
            if did in gold:
                gold_chars += n; seen_gold.add(did)
            else:
                meta.append((qkey(name, did), did, n))
    missing = gold - seen_gold
    full_docs, full_chars = len(meta) + len(seen_gold), gold_chars + sum(m[2] for m in meta)
    keep, tot = set(seen_gold), gold_chars
    meta.sort()
    for _, did, n in meta:
        if tot + n > MAXCH:
            break
        keep.add(did); tot += n
    del meta
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    nd = 0
    with open(corpus, encoding="utf-8") as f, open(d / "corpus.jsonl", "w", encoding="utf-8") as g, \
            open(d / "doc_ids.txt", "w", encoding="utf-8") as di:
        for line in f:
            o = json.loads(line)
            if str(o["_id"]) in keep:
                g.write(json.dumps({"_id": str(o["_id"]), "title": o.get("title") or "", "text": o.get("text") or ""},
                                   ensure_ascii=False) + "\n")
                di.write(str(o["_id"]) + "\n"); nd += 1
    ndev, ntest = write_common(d, name, {q: qtext[q] for q in sel}, {q: qrels[q] for q in sel})
    doubt = []
    if missing:
        doubt.append(f"存疑：{len(missing)} 篇金标文档原语料里就没有（上游缺陷，保留该题，该文档永远检索不到）：{sorted(missing)[:5]}")
    return {"group": grp, "kind": "retrieval", "metric": "ndcg@10",
            "metric_def": "xbench bench_ir.metrics：nDCG@10（分级 qrels，gain=2^rel-1），ArguAna 惯例去掉与问句同号文档",
            "n_queries": len(sel), "n_dev": ndev, "n_test": ntest, "n_docs": nd, "n_chars": tot,
            "n_gold_docs": len(gold), "source_full": {"docs": full_docs, "chars": full_chars, "queries_with_pos_qrels": len(qtext)},
            "sources": {P["corpus"]: sha_file(corpus), P["queries"]: sha_file(resolve(P["queries"])),
                        P["qrels"]: sha_file(resolve(P["qrels"]))},
            "source_qrels_split": qsplit, "gold_missing_upstream": sorted(missing), "doubt": doubt}


# ---------------- 记忆集 ----------------
LME_RAW_NAMES = ("longmemeval_s_cleaned.json", "longmemeval_s.json")
_lme_raw = [None]


def lme_part(k):
    """partK.json（= 官方 longmemeval_s_cleaned 中 n%3==K 的题，按 n 升序）。
    UMB_LME 下有 partK.json 就直接读；否则读官方原始文件按 n%3 拆（内容一致，但字节指纹只登记了 part 文件）。"""
    root = env_root("UMB_LME")
    p = root / f"part{k}.json"
    if p.exists():
        return json.load(open(p, encoding="utf-8"))
    if _lme_raw[0] is None:
        raw = next((root / n for n in LME_RAW_NAMES if (root / n).exists()), None)
        if raw is None:
            raise SystemExit(f"UMB_LME={root} 下既无 part{k}.json 也无 {' / '.join(LME_RAW_NAMES)}")
        print(f"lme: 用原始文件 {raw.name} 按 n%3 拆分（存疑：字节指纹不可比，逐题内容核对代替）", flush=True)
        _lme_raw[0] = json.load(open(raw, encoding="utf-8"))
    return [it for n, it in enumerate(_lme_raw[0]) if n % 3 == k]


def lme_part_token(k):
    return tok("UMB_LME", f"part{k}.json")


def build_lme():
    qtext, qrels, extra, nturn, nch = {}, {}, {}, {}, {}
    files = {}
    for pi in range(3):
        data = lme_part(pi)
        p = resolve(lme_part_token(pi))
        files[lme_part_token(pi)] = sha_file(p) if p.exists() else None
        for j, it in enumerate(data):
            n = 0; gold = set(); ch = 0
            for sess in it["haystack_sessions"]:
                for t in sess:
                    if t.get("has_answer"):
                        gold.add(n)
                    ch += len(f"{t['role']}: {t['content']}"); n += 1
            if not gold:          # 同 lme_zerokey：无 gold 的题（_abs 等）不计
                continue
            q = it["question_id"]
            qtext[q] = it["question"]; qrels[q] = {str(g): 1 for g in gold}
            extra[q] = {"src": f"part{pi}.json", "idx": j, "n": j * 3 + pi, "type": it["question_type"]}
            nturn[q] = n; nch[q] = ch
        del data
    _lme_raw[0] = None
    sel = pick("lme", list(qtext))
    d = OUT / "lme"
    ndev, ntest = write_common(d, "lme", {q: qtext[q] for q in sel}, {q: qrels[q] for q in sel}, {q: extra[q] for q in sel})
    src = {"kind": "per-question haystack", "files": files,
           "note": "partK.json = longmemeval_s_cleaned 第 n 题且 n%3==K（已核对与 data_gen/lme_s.json 逐题一致）；"
                   "检索单元 = 一轮，正文 '<role>: <content>'，docid = 本题 haystack 内轮序号（0 起）",
           "qids": sel}
    (d / "source.json").write_text(json.dumps(src, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"group": "mem", "kind": "memory", "metric": "r@10",
            "metric_def": "lme_zerokey.score：前 10 轮中 gold 轮占全部 gold 轮比例；每题只在本题 haystack 内检索",
            "n_queries": len(sel), "n_dev": ndev, "n_test": ntest, "n_docs": sum(nturn[q] for q in sel),
            "n_chars": sum(nch[q] for q in sel), "source_full": {"queries_with_gold": len(qtext), "instances": 500},
            "sources": src["files"], "doubt": []}


def locomo_conv_items():
    out = []   # 同 confluence/extract.items('all')
    for c in json.loads(resolve(tok("UMB_LOCOMO")).read_text(encoding="utf-8")):
        conv = c["conversation"]
        n = sorted(int(k.split("_")[1]) for k in conv if k.startswith("session_") and not k.endswith("date_time"))
        turns, ids = [], []
        for i in n:
            for t in conv[f"session_{i}"]:
                txt = f"{t['speaker']}: {t['text']}"
                if t.get("blip_caption"):
                    txt += f" [image: {t['blip_caption']}]"
                turns.append(txt); ids.append(t["dia_id"])
        out.append({"sid": c["sample_id"], "turns": turns, "ids": ids, "qa": [q for q in c["qa"] if q.get("category") != 5]})
    return out


def locomo_gold(it, q):
    idx = {d: i for i, d in enumerate(it["ids"])}   # 同 bench_cc 的 evidence 解析
    return {p.strip() for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}


def build_locomo():
    qtext, qrels, extra, conv = {}, {}, {}, {}
    for it in locomo_conv_items():
        conv[it["sid"]] = (len(it["turns"]), sum(len(t) for t in it["turns"]))
        for qi, q in enumerate(it["qa"]):
            ev = locomo_gold(it, q)
            if not ev:
                continue
            k = f"{it['sid']}_{qi}"
            qtext[k] = q["question"]; qrels[k] = {e: 1 for e in ev}
            extra[k] = {"sid": it["sid"], "qi": qi, "category": q.get("category")}
    sel = pick("locomo", list(qtext))
    d = OUT / "locomo"
    ndev, ntest = write_common(d, "locomo", {q: qtext[q] for q in sel}, {q: qrels[q] for q in sel}, {q: extra[q] for q in sel})
    sids = sorted({extra[q]["sid"] for q in sel})
    src = {"kind": "per-conversation", "files": {tok("UMB_LOCOMO"): sha_file(resolve(tok("UMB_LOCOMO")))},
           "note": "检索单元 = 一轮 '<speaker>: <text>[ [image: caption]]'；qid = <sample_id>_<qi>，qi 为去掉 category 5 后的 qa 序号；"
                   "docid = dia_id；同 confluence/extract.items + bench_cc 的 evidence 解析",
           "qids": sel}
    (d / "source.json").write_text(json.dumps(src, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"group": "mem", "kind": "memory", "metric": "r@10",
            "metric_def": "lme_zerokey.score：前 10 轮中 evidence 轮占比；每题在本会话全部轮内检索",
            "n_queries": len(sel), "n_dev": ndev, "n_test": ntest, "n_docs": sum(conv[s][0] for s in sids),
            "n_chars": sum(conv[s][1] for s in sids), "source_full": {"queries_with_evidence": len(qtext), "conversations": len(conv)},
            "sources": src["files"], "doubt": []}


def hive_mod():
    p = str(AGM / "bench")
    if p not in sys.path:
        sys.path.insert(0, p)
    import hive_retrieval as HR
    return HR


def hive_candidates():
    """(cards, qtext, qrels, gold_quotes, extra)：同 bench_zh.gold——有 supporting_evidence 用 primary，否则用 evidence_pool。"""
    HR = hive_mod()
    cards = HR.load_cards(env_root("UMB_HIVE"))
    qtext, qrels, gq, extra = {}, {}, {}, {}
    for c in cards:
        if c.get("supporting_evidence"):
            ps = [HR.norm(e["quote"]) for e in c["supporting_evidence"] if e.get("weight") == "primary"]
            kind = "primary"
        else:
            ps = [HR.norm(e["quote"]) for e in c.get("evidence_pool") or [] if e.get("quote")]
            kind = "evidence_pool"
        ps = [p for p in ps if p]
        if not ps:
            continue
        q = c["qid"]
        qtext[q] = c["question"]; extra[q] = {"gold_kind": kind}
        qrels[q] = {f"ev:{h(p)[:16]}": 1 for p in ps}
        gq[q] = {f"ev:{h(p)[:16]}": p for p in ps}
    return cards, qtext, qrels, gq, extra


def build_hive():
    HR = hive_mod()
    HIVE = env_root("UMB_HIVE")
    chunks = HR.load_chunks(HIVE)
    cards, qtext, qrels, gq, extra = hive_candidates()
    sel = pick("hive", list(qtext))
    d = OUT / "hive"
    ndev, ntest = write_common(d, "hive", {q: qtext[q] for q in sel}, {q: qrels[q] for q in sel}, {q: extra[q] for q in sel})
    (d / "gold_quotes.json").write_text(json.dumps({q: gq[q] for q in sel}, ensure_ascii=False, indent=1), encoding="utf-8")
    rels = [pathlib.Path(f).relative_to(HIVE).as_posix() for f in
            sorted(glob.glob(str(HIVE / "corpus/u*.json"))) + sorted(glob.glob(str(HIVE / "cards/*.yaml")))]
    try:
        commit = subprocess.run(["git", "-C", str(HIVE), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    if commit != HIVE_COMMIT:
        print(f"hive: 存疑——UMB_HIVE 的 commit={commit}，冻结版本为 {HIVE_COMMIT}；以源文件 sha256 为准", flush=True)
    src = {"kind": "single corpus", "repo": tok("UMB_HIVE"), "commit": commit,
           "files": {tok("UMB_HIVE", r): sha_file(HIVE / r) for r in rels},
           "note": "检索单元 = hive_retrieval.load_chunks 的 160 字句界块；指标 = 按排名装满 8000 字预算（HR.take）后，"
                   "金标证据句（HR.norm 归一）逐字出现的比例；docid 'ev:<sha256(norm quote)[:16]>'，原句见 gold_quotes.json",
           "qids": sel}
    (d / "source.json").write_text(json.dumps(src, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"group": "mem", "kind": "memory", "metric": "r@10",
            "metric_def": "bench_cc hive 口径：r@10 := 8000 字上下文中金标证据句完整出现比例（budget=8000）",
            "n_queries": len(sel), "n_dev": ndev, "n_test": ntest, "n_docs": len(chunks), "n_chars": sum(len(c["text"]) for c in chunks),
            "source_full": {"cards": len(cards), "cards_with_gold": len(qtext)}, "sources": {"commit": commit, **src["files"]},
            "doubt": ["gold 取 bench_zh 两口径并集：38 题 primary supporting_evidence + 54 道开放题 evidence_pool（bench_cc 只用前 38 题）"]}


def base_manifest():
    return {"name": "UMB", "version": "0.1",
            "rules": {"max_queries": MAXQ, "query_order": 'sha256("umb-v0.1|"+set+"|"+qid) asc, only queries with positive qrels',
                      "corpus": f'gold docs + others by sha256("umb-v0.1|"+set+"|"+docid) asc until next doc would exceed {MAXCH} chars (len(title)+len(text))',
                      "split": 'sha256("umb-split|"+qid)[0] even -> dev, odd -> test',
                      "memory_sets": "corpus not copied; source.json = source paths (${VAR}/relative) + sha256 + qid list",
                      "repo_excludes": list(REPO_EXCLUDES)},
            "path_vars": PATH_VARS,
            "groups": {"mem": list(MEM), "en": [k for k, v in RETR.items() if v[3] == "en"], "zh": [k for k, v in RETR.items() if v[3] == "zh"]}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--sets", default=",".join(ALL))
    ap.add_argument("--freeze", action="store_true", help="把产物（除 corpus.jsonl）与 manifest 写回本目录（仅发新版本时用）")
    a = ap.parse_args()
    frozen = json.loads((UMB / "manifest.json").read_text(encoding="utf-8")) if (UMB / "manifest.json").exists() else {"sets": {}}
    OUT.mkdir(parents=True, exist_ok=True)
    mf = OUT / "manifest.json"
    man = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    man.update(base_manifest()); man["built_at"] = time.strftime("%Y-%m-%d %H:%M:%S %z")
    man.setdefault("sets", {})
    bad = 0
    for name in a.sets.split(","):
        t0 = time.time()
        try:
            info = build_lme() if name == "lme" else build_locomo() if name == "locomo" else build_hive() if name == "hive" else build_retr(name)
        except (OSError, ValueError, KeyError) as e:   # 存疑：跳过该集并登记（不静默）
            man["sets"][name] = {"status": "存疑", "error": repr(e)}
            print(name, "存疑", repr(e), flush=True); bad += 1
            continue
        d = OUT / name
        info["files"] = {p.name: {"sha256": sha_file(p), "bytes": p.stat().st_size} for p in sorted(d.iterdir()) if p.is_file()}
        info["status"] = "ok"; info["build_secs"] = round(time.time() - t0, 1)
        man["sets"][name] = info
        ref = frozen["sets"].get(name, {}).get("files", {})
        diff = sorted(fn for fn in set(ref) | set(info["files"]) if ref.get(fn, {}).get("sha256") != info["files"].get(fn, {}).get("sha256"))
        verdict = "与冻结清单逐文件一致" if not diff else f"与冻结清单不一致：{diff}"
        bad += bool(diff)
        print(name, info["n_queries"], info["n_dev"], info["n_test"], info["n_docs"], info["n_chars"], f"{time.time()-t0:.0f}s", verdict, flush=True)
        mf.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    mf.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.freeze:
        for name in a.sets.split(","):
            if man["sets"].get(name, {}).get("status") != "ok":
                continue
            (UMB / name).mkdir(exist_ok=True)
            for fn in man["sets"][name]["files"]:
                if fn not in REPO_EXCLUDES:
                    shutil.copyfile(OUT / name / fn, UMB / name / fn)
        frozen.update({k: v for k, v in man.items() if k != "sets"}); frozen.setdefault("sets", {})
        frozen["sets"].update({k: man["sets"][k] for k in a.sets.split(",") if k in man["sets"]})
        (UMB / "manifest.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=1), encoding="utf-8")
        print("已冻结到", UMB.name)
    sys.exit(1 if bad and not a.freeze else 0)


if __name__ == "__main__":
    main()
