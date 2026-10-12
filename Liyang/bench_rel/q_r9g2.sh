#!/bin/bash
# gen-r9 补充：(1) loc_dev 无模型 rel-v1.4 代码 --np 1 复跑（tag rel14np1，root=wt-r9port@6022990），查 conv-30/9 差异来源；(2) 带模型 lmelp(s)_dev（tag rel15emb）
L=/workspace/work/ls/wt-rel/bench_rel/logs
cd /workspace/work/ls/wt-gen/bench_gen
[ -s /tmp/gen_jobs/lmelp_dev.jsonl ] || python3 v3/r7/mk_lp.py > /dev/null
G1_FROZEN_CLOCK=1 GEN_DB_CACHE=/tmp/ls_cache/rel14np1 python3 gen_eval.py run rel14np1 loc_dev --root /workspace/work/ls/wt-r9port --np 1 >> $L/gen_r9g2.log 2>&1; python3 gen_eval.py score rel14np1 loc_dev >> $L/gen_r9g2.log 2>&1
export G1_FROZEN_CLOCK=1 GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5
for s in lmelp_dev lmelps_dev; do python3 gen_eval.py run rel15emb $s --root /workspace/work/ls/wt-rel --np 1 >> $L/gen_rel15emb.log 2>&1; done
echo R9G2_DONE >> $L/gen_r9g2.log
