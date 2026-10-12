# -*- coding: utf-8 -*-
"""gen-v3 r9（PREREG_GEN_v3 修订 10）：新的未暴露 ConvoMem 轮级金标保留集 H-CM9（≥800 题），两种写入口径。

来源：HF Salesforce/ConvoMem core_benchmark/pre_mixed_testcases 同五个类别目录（同 mk_cm_r5.py / mk_cm_r8.py），
  H-CM9 = batched_039（每文件 40 例）+ batched_038（每文件 40 例），合并为 cm9_hold / cm9s_hold。
本地副本 /workspace/work/ls/_shared/convomem/<tag>_{038,039}.json（v3/r9/dl_cm9.sh 下载）。
口径、证据逐字对齐、去重规则、抽样 Random(5) 与 mk_cm_r5.build 完全相同（直接调用，不改）：
  排除集 = cm_hold、cm4_dev、cm4_hold、cm5_hold、cm5_dev、cm6_hold、cm8_hold、cm8_dev 全部题面 + 证据文本组；
  先建 039 部分、再建 038 部分（后者另排除前者）。
W0 cm9_hold（消息原文） / W1 cm9s_hold（"{speaker}: {text}"）。打印计数与 sha1，md5 写 v3/r9/cm9_md5.json。"""
import hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import mk_cm_r5 as R5  # noqa: E402
import gen_eval as G  # noqa: E402

R5.PRIOR = ("cm_hold", "cm4_dev", "cm4_hold", "cm5_hold", "cm5_dev", "cm6_hold", "cm8_hold", "cm8_dev")
PARTS = (("cm9a_hold", "039", 40), ("cm9b_hold", "038", 40))


def merge():
    J = G.JOBS
    for w, parts in (("cm9_hold", ("cm9a_hold", "cm9b_hold")), ("cm9s_hold", ("cm9as_hold", "cm9bs_hold"))):
        with open(os.path.join(J, f"{w}.jsonl"), "w", encoding="utf-8") as f:
            for p in parts:
                f.write(open(os.path.join(J, f"{p}.jsonl"), encoding="utf-8").read())
        for kind in ("meta", "ids"):
            d = {}
            for p in parts:
                x = json.load(open(os.path.join(J, f"{kind}_{p}.json"), encoding="utf-8"))
                assert not set(x) & set(d)
                d.update(x)
            G.dump(os.path.join(J, f"{kind}_{w}.json"), d)
    meta = json.load(open(os.path.join(J, "meta_cm9_hold.json"), encoding="utf-8"))
    cats = {}
    for v in meta.values():
        for m in v.values():
            cats[m["cat"]] = cats.get(m["cat"], 0) + 1
    nd = sorted(len(json.loads(l)["docs"]) for l in open(os.path.join(J, "cm9_hold.jsonl"), encoding="utf-8") if l.strip())
    return {"jobs": len(meta), "q_total": sum(len(v) for v in meta.values()), "by_cat": cats,
            "multi_ev": sum(1 for v in meta.values() for m in v.values() if len(m["ev"]) > 1),
            "turns_min_med_max": [nd[0], nd[len(nd) // 2], nd[-1]],
            "sha1": {n: R5.sha(n) for n in ("cm9_hold.jsonl", "cm9s_hold.jsonl", "meta_cm9_hold.json", "ids_cm9_hold.json")}}


def main():
    seen_q, seen_ev = R5.excluded()
    md5, out = {}, {"excluded_prior_q_ev": (len(seen_q), len(seen_ev))}
    for sset, batch, per in PARTS:
        out[sset] = R5.build(sset, batch, per, seen_q, seen_ev, md5)
    out["cm9_hold"] = merge()
    out["md5"] = md5
    json.dump(md5, open(os.path.join(HERE, "cm9_md5.json"), "w"), indent=1, sort_keys=True)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
