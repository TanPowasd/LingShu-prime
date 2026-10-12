#!/bin/bash
# r7 第 1 次迭代 dev：sweep（含 LDD 对照）两口径；v3.2 快照（无语义）两口径；对手两口径
cd /workspace/work/ls/wt-gen/bench_gen
export G1_FROZEN_CLOCK=1
[ -s /tmp/gen_jobs/lmelp_dev.jsonl ] || python3 v3/r7/mk_lp.py
[ -s /tmp/gen_jobs/lme_dev.jsonl ] || python3 gen_eval.py prep
R=$(python3 gen_eval.py snap 8afd54e | tail -1)
for s in lmelp_dev lmelps_dev; do
  python3 gen_eval.py run r7_v32 $s --root $R --np 2
  echo "$(date +%T) v32 $s"
done
for s in lmelp_dev lmelps_dev; do
  GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5 python3 gen_eval.py run r7_it1 $s --np 2 --sweep v3/r7/r7_sweep1.json
  echo "$(date +%T) it1 $s"
done
for s in lmelp_dev lmelps_dev; do
  PYTHONHASHSEED=0 python3 v3/cf_holdjobs.py $s 0 2 > runs/cf_$s.0.log 2>&1 &
  PYTHONHASHSEED=0 python3 v3/cf_holdjobs.py $s 1 2 > runs/cf_$s.1.log 2>&1
  wait
  echo "$(date +%T) cf $s"
done
echo R7DEV1DONE
