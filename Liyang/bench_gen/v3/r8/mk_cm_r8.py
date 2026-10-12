# -*- coding: utf-8 -*-
"""gen-v3 r8（PREREG_GEN_v3 修订 9）：新的未暴露 ConvoMem 轮级金标集，两种写入口径。

来源：HF Salesforce/ConvoMem core_benchmark/pre_mixed_testcases 同五个类别目录（同 mk_cm_r5.py），
  H-CM8  (cm8_hold) = batched_041   判定集（冻结后只跑一次），每文件 40 例
  CM8-dev (cm8_dev) = batched_040   dev（只在它上面调参），每文件 20 例
本地副本 /workspace/work/ls/_shared/convomem/<tag>_{040,041}.json（v3/r8/dl_cm8.sh 下载）。
口径、证据对齐、去重规则与 mk_cm_r5.build 完全相同（直接调用，不改）：
  排除集 = cm_hold、cm4_dev、cm4_hold、cm5_hold、cm5_dev、cm6_hold 全部题面 + 证据文本组（须先跑 mk_holdout_cm / mk_cm_r4 / mk_cm_r5 重建 /tmp/gen_jobs）；
  先建 cm8_hold、再建 cm8_dev（后者另排除前者）。抽样 random.Random(5)（build 内固定）。
W0 cm8_<split>（消息原文） / W1 cm8s_<split>（"{speaker}: {text}"）。打印计数与 sha1，md5 写 v3/r8/cm8_md5.json。"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import mk_cm_r5 as R5  # noqa: E402

R5.PRIOR = ("cm_hold", "cm4_dev", "cm4_hold", "cm5_hold", "cm5_dev", "cm6_hold")
SPLITS = (("cm8_hold", "041", 40), ("cm8_dev", "040", 20))


def main():
    seen_q, seen_ev = R5.excluded()
    md5, out = {}, {"excluded_prior_q_ev": (len(seen_q), len(seen_ev))}
    for sset, batch, per in SPLITS:
        out[sset] = R5.build(sset, batch, per, seen_q, seen_ev, md5)
    out["md5"] = md5
    json.dump(md5, open(os.path.join(HERE, "cm8_md5.json"), "w"), indent=1, sort_keys=True)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
