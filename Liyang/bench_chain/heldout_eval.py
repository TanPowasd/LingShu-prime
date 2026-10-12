# -*- coding: utf-8 -*-
"""保留扰动集 H1 评测（见 PREREG_HELDOUT.md；每个条件只跑一次）。
  python heldout_eval.py cov                 抽取覆盖（逐改写句单独过抽取器，对照原句解析）
  python heldout_eval.py rank <cond>         cond∈h100|h50：ng / ngchain 工人 + BM25(k=60) → out/heldout/ranked_<cond>_<arm>.json
  python heldout_eval.py score <cond>        代理（chain_metrics）+ 机械读者 K 档（probe_judge）+ 逐题符号检验 → out/heldout/result_<cond>.json"""
import hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from cb_common import *  # noqa
from lingshu_ng.chain import read_material  # noqa: E402   先占住本 worktree 的 lingshu_ng
from lingshu_ng.chain.extract import extract  # noqa: E402
import importlib as _il  # noqa: E402
import extract_cache as _XC  # noqa: E402   2026-10-12：抽取结果按 (文本 sha1, 抽取器版本) 落盘缓存
extract = _XC.wrap(_il.import_module("lingshu_ng.chain.extract"))
sys.path[1:1] = [TIT, os.path.join(CH, "tools"), HMBD]
import chain_metrics as CM  # noqa: E402
import probe_judge as J  # noqa: E402
from paired import sign  # noqa: E402

D = os.environ.get("HO_DIR") or os.path.join(OUT, "heldout")
SPLIT = re.compile(r"(?<=[。])")


def cond_corpus(cond):
    rw = load(os.path.join(D, "rewrite_map.json"))
    frac = {"h100": 1.0, "h50": 0.5}[cond]
    out, n = [], 0
    for c in corpus():
        sents = SPLIT.split(c["text"])
        for i in range(len(sents)):
            r = rw.get(f"{c['cid']}|{i}")
            if not r or not r["new"]:
                continue
            h = int(hashlib.md5(f"h1|{c['cid']}|{i}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
            if h < frac:
                sents[i] = r["new"]; n += 1
        out.append(dict(c, text="".join(sents)))
    return out, n


def cov():
    out = {m: _cov(m) for m in ("loose", "strict")}
    dump(os.path.join(D, "coverage.json"), out, indent=1); print(out)


def _cov(mode):
    rw = load(os.path.join(D, "rewrite_map.json")); st = {"parsed_exact": 0, "parsed_wrong": 0, "mention": 0, "missed": 0, "fallback_orig": 0}
    lz = mode == "loose"
    for r in rw.values():
        if not r["new"]:
            st["fallback_orig"] += 1; continue
        o = [e for e in extract(r["orig"], loose=False) if e.op != "mention"][0]
        ev = extract(r["new"], loose=lz)
        real = [e for e in ev if e.op != "mention"]
        if real:
            e = real[0]
            st["parsed_exact" if (e.op, e.entity, e.attr, e.value, e.alt) == (o.op, o.entity, o.attr, o.value, o.alt) else "parsed_wrong"] += 1
        elif ev:
            st["mention"] += 1
        else:
            st["missed"] += 1
    st["n"] = len(rw)
    return st


V7_ROOT = "/workspace/work/ls/chain_v7_snap"     # v7（43e8b3b）lingshu_ng 快照，供 H3 的 v7 对照臂
V8_ROOT = "/workspace/work/ls/chain_v8_snap"
V9_ROOT = "/workspace/work/ls/chain_v9_snap"     # v9（c8798fb）快照，供 H5 的 v9 对照臂（chain-r10）


def worker(chain, C, of, extra_env=None, root=None):
    cf = of + ".corpus.json"; json.dump(C, open(cf, "w", encoding="utf-8"), ensure_ascii=False)
    env = dict(os.environ, PYTHONPATH=root or WT, PYTHONHASHSEED="0", CB_CORPUS=cf, **(extra_env or {}))
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "ng_worker.py"), "1" if chain else "0", of, "6", "60"],
                       env=env, cwd="/tmp", capture_output=True, text=True, timeout=110)
    os.remove(cf)
    if r.returncode:
        print(r.stderr[-2000:])


def rank(cond, arm):
    C, n = cond_corpus(cond); of = os.path.join(D, f"ranked_{cond}_{arm}.json")
    if arm == "bm25":
        import hmb_lib as H
        bm = H.BM25([c["text"] for c in C])
        dump(of, {"impl": "bm25", "ranked": {q["qid"]: [C[i]["cid"] for i, _ in bm.search(q["question"], 60)] for q in keys_main()}})
    elif arm == "ngchain_noloose":
        worker(True, C, of, {"LINGSHU_NG_CHAIN_LOOSE": "0"})
    elif arm == "ngchain_v7":
        worker(True, C, of, root=V7_ROOT)
    elif arm == "ngchain_v8":
        worker(True, C, of, root=V8_ROOT)
    elif arm == "ngchain_v9":
        worker(True, C, of, root=V9_ROOT)
    elif arm == "ngchain_noshort":
        worker(True, C, of, {"LINGSHU_NG_CHAIN_SHORT": "0"})
    else:
        worker(arm == "ngchain", C, of)
    print(cond, arm, "rewritten", n, "ok", os.path.exists(of))


def judge_setup(base, C):
    data = Path(base) / "data"; data.mkdir(parents=True, exist_ok=True)
    for src in ("keys/keys.json", "keys/synth_log.json"):
        shutil.copy(os.path.join(CH, src), data / os.path.basename(src))
    (data / "corpus.json").write_text(json.dumps(C, ensure_ascii=False), encoding="utf-8")
    J.OUT, J.RUNS = data, Path(base) / "runs"


def reader_arm(tag, keys, by_cid, ranked):
    d = J.RUNS / f"chain_{tag}"
    shutil.rmtree(d, ignore_errors=True); (d / "sut" / "out").mkdir(parents=True); (d / "retrieval").mkdir()
    for q in keys:
        mat = material(ranked.get(q["qid"], []), by_cid, q["type"] == "变更", "K")
        a = read_material(q["question"], mat); a["qid"] = q["qid"]
        (d / "sut" / "out" / f"{q['qid']}.json").write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
        (d / "retrieval" / f"{q['qid']}.json").write_text(json.dumps({"qid": q["qid"], "material": mat}, ensure_ascii=False), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps(dict(arm=tag, keys_fp=J.keys_fp(keys_all()), limit=0, llm_calls=0)))
    _, doc_norms, decoys = J._corpus_index()
    return J.judge_arm(tag, keys, doc_norms, decoys)


def reader_perq(base, arm, keys):
    import paired
    return paired.perq(base, arm, keys)


SHOWP = ("gold6_all", "gold6_现值", "gold_first_现值", "stale_first_现值", "future_first_历史时点", "chain_cov", "chain_full")
SHOWR = ("present", "history", "chain", "four_state", "reason", "stale", "verbatim")


def score(cond):
    C, n = cond_corpus(cond); by_cid = {c["cid"]: c for c in C}
    K = keys_main(); cidx = CM.chain_index()
    arms = tuple(a for a in ("ng", "ngchain", "bm25", "ngchain_noloose", "ngchain_v7", "ngchain_v8", "ngchain_v9", "ngchain_noshort") if os.path.exists(os.path.join(D, f"ranked_{cond}_{a}.json")))
    R = {a: load(os.path.join(D, f"ranked_{cond}_{a}.json")) for a in arms}
    res = {"cond": cond, "rewritten": n, "proxy": {}, "reader": {}, "paired": {}}
    pp = {}
    for a in arms:
        Ra = dict(R[a], ranked={q: v[:CHAIN_K] for q, v in R[a]["ranked"].items()})
        pp[a] = CM.perq(Ra, K, cidx)
        res["proxy"][a] = {sp: {k: CM.agg({q["qid"]: pp[a][q["qid"]] for q in split(K, sp)})[k] for k in SHOWP} for sp in ("dev", "test")}
    base = os.path.join(D, "reader", cond); judge_setup(base, C)
    rp = {}
    for sp in ("dev", "test"):
        ks = split(K, sp)
        for a in arms:
            r = reader_arm(f"{a}_{sp}", ks, by_cid, R[a]["ranked"])
            res["reader"].setdefault(a, {})[sp] = {f: r[f] for f in SHOWR}
            rp[(a, sp)] = reader_perq(base, f"{a}_{sp}", ks)
    for sp in ("dev", "test"):
        ks = [q["qid"] for q in split(K, sp)]
        for b in [x for x in ("ng", "bm25", "ngchain_noloose", "ngchain_v7", "ngchain_v8", "ngchain_v9", "ngchain_noshort") if x in arms]:
            for f in ("gold6", "gold_first", "chain_full"):
                qs = [q for q in ks if f in pp["ngchain"][q] and f in pp[b][q]]
                res["paired"][f"{sp}.proxy.{f}.ngchain-{b}"] = sign([pp["ngchain"][q][f] for q in qs], [pp[b][q][f] for q in qs])
            A, B = rp[("ngchain", sp)], rp[(b, sp)]
            for t, f in (("现值", "value_ok"), ("历史", "value_ok"), ("变更", "chain_ok"), (None, "state_ok")):
                qs = [q for q in A if (t is None or A[q]["type"] == t) and f in A[q] and f in B[q]]
                res["paired"][f"{sp}.reader.{t or '全部'}.{f}.ngchain-{b}"] = sign([A[q][f] for q in qs], [B[q][f] for q in qs])
    dump(os.path.join(D, f"result_{cond}.json"), res, indent=1)
    for a in arms:
        print(cond, a, "proxy test", res["proxy"][a]["test"], "\n   reader test", res["reader"][a]["test"])
    for k, v in res["paired"].items():
        if k.startswith("test"):
            print(k, v)


if __name__ == "__main__":
    if sys.argv[1] == "cov":
        cov()
    elif sys.argv[1] == "rank":
        rank(sys.argv[2], sys.argv[3])
    else:
        score(sys.argv[2])
