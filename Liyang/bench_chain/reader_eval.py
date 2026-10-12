# -*- coding: utf-8 -*-
"""机械读者（lingshu_ng.chain.read_material，零 LLM，各臂同一读者）× 两档预算 → 官方 probe_judge.judge_arm。
  python reader_eval.py <split: dev|test|all> [arms 逗号分隔]
臂（材料来源）：
  ng       K: item5/ranked_ng.json（ng@875d838，6/60）        C: item5/ranked_ngB.json（60/270 长榜）
  bm25     K: item5/ranked_bm25@titans.json（hmb_lib.BM25）   C: out/ranked_bm25L.json（同实现 k=270）
  tc11     K/C: item5/ranked_tc11.json（TriCue v1.1 已落盘排序，270 长榜）
  tc2      K/C: item5/ranked_tc2.json（TriCue v2，参考）
  ngchain  K: out/ranked_ngchain.json（6/60）               C: out/ranked_ngchainB.json（60/270）
  native   ng+chain 原生结构化答案（全账本作答；材料＝ngchain K 档前 6/60 段，依据轴按该材料判）
写 out/reader/<split>/runs/chain_<arm>_<K|C>/…，读数 out/reader_<split>.json。"""
import json, os, shutil, sys
from pathlib import Path
from cb_common import *  # noqa
sys.path.insert(0, os.path.join(CH, "tools"))
import probe_judge as J  # noqa: E402
from lingshu_ng.chain import read_material  # noqa: E402

SRC = {"ng": (os.path.join(ITEM5, "ranked_ng.json"), os.path.join(ITEM5, "ranked_ngB.json")),
       "bm25": (os.path.join(ITEM5, "ranked_bm25@titans.json"), os.path.join(OUT, "ranked_bm25L.json")),
       "tc11": (os.path.join(ITEM5, "ranked_tc11.json"),) * 2,
       "tc2": (os.path.join(ITEM5, "ranked_tc2.json"),) * 2,
       "ngchain": (os.path.join(OUT, "ranked_ngchain.json"), os.path.join(OUT, "ranked_ngchainB.json"))}
FIELDS = ("present", "history", "chain", "chain_row_recall", "four_state", "reason", "stale", "future",
          "subject_confusion", "verbatim", "n")


def setup(base):
    data = Path(base) / "data"; data.mkdir(parents=True, exist_ok=True)
    for src in ("corpus/corpus.json", "keys/keys.json", "keys/synth_log.json"):
        shutil.copy(os.path.join(CH, src), data / os.path.basename(src))
    J.OUT, J.RUNS = data, Path(base) / "runs"


def run_arm(tag, keys, by_cid, ranked, mode, native=None):
    d = J.RUNS / f"chain_{tag}"
    shutil.rmtree(d, ignore_errors=True); (d / "sut" / "out").mkdir(parents=True); (d / "retrieval").mkdir()
    for q in keys:
        if q.get("reconstructible"):
            continue
        chq = q["type"] == "变更"
        mat = material(ranked.get(q["qid"], []), by_cid, chq, mode)
        a = dict(native[q["qid"]]) if native is not None else read_material(q["question"], mat)
        a["qid"] = q["qid"]
        (d / "sut" / "out" / f"{q['qid']}.json").write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
        (d / "retrieval" / f"{q['qid']}.json").write_text(json.dumps({"qid": q["qid"], "material": mat}, ensure_ascii=False), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps(dict(arm=tag, keys_fp=J.keys_fp(keys_all()), limit=0, llm_calls=0)))
    _, doc_norms, decoys = J._corpus_index()
    return J.judge_arm(tag, keys, doc_norms, decoys)


def main(sp, arms):
    base = os.path.join(OUT, "reader", sp); setup(base)
    keys = split(keys_all(), sp)
    by_cid = {c["cid"]: c for c in corpus()}
    rows = {}
    for arm in arms:
        if arm == "native":
            R = load(os.path.join(OUT, "ranked_ngchain.json"))
            rows["native_K"] = run_arm("native_K", keys, by_cid, R["ranked"], "K", native=R["native"])
            continue
        for mi, mode in enumerate("KC"):
            R = load(SRC[arm][mi])["ranked"]
            rows[f"{arm}_{mode}"] = run_arm(f"{arm}_{mode}", keys, by_cid, R, mode)
    for t, r in rows.items():
        print(f"{t:11s} " + " ".join(f"{f}={r[f]}" for f in FIELDS), flush=True)
    prev = load(os.path.join(OUT, f"reader_{sp}.json"), {})
    prev.update({t: {f: r[f] for f in FIELDS + ("counts", "bucket_main")} for t, r in rows.items()})
    dump(os.path.join(OUT, f"reader_{sp}.json"), prev, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "ng,bm25,tc11,tc2,ngchain,native").split(","))
