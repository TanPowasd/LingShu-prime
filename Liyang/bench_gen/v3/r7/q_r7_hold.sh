#!/bin/bash
# r7 冻结后 hold（只跑一次）：候选（新树+语义+冻结 cfg）、v3.2+LDD（新树 sf=0 + 语义）、v3.2（8afd54e 快照，无语义）、对手两臂；两口径
cd /workspace/work/ls/wt-gen/bench_gen
export G1_FROZEN_CLOCK=1
export GEN_EMBED_CACHE=/tmp/ls_cache/vec
mkdir -p /tmp/ls_cache/vec; [ -s /tmp/ls_cache/vec/vec.db ] || cp /workspace/work/ls/_shared/models/_vec_cache/vec.db /tmp/ls_cache/vec/
CFG="$1"
EMB=/workspace/work/ls/_shared/models/bge-small-en-v1.5
[ -s /tmp/gen_jobs/lmelp_hold.jsonl ] || python3 v3/r7/mk_lp.py
for s in lmelp_hold lmelps_hold; do
  GEN_EMBED=$EMB python3 gen_eval.py run r7_cand $s --np 2 --cfg "$CFG"; echo "$(date +%T) cand $s"
  GEN_EMBED=$EMB python3 gen_eval.py run r7_lddh $s --np 2 --cfg '{"sf":0}'; echo "$(date +%T) ldd $s"
done
echo R7HOLDDONE
