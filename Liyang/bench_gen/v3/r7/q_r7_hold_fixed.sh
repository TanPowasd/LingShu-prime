#!/bin/bash
# r7 hold 中与冻结无关的固定臂（先跑，不看读数）：v3.2（8afd54e 快照，无语义）、对手两臂；两口径
cd /workspace/work/ls/wt-gen/bench_gen
export G1_FROZEN_CLOCK=1
R=$(python3 gen_eval.py snap 8afd54e | tail -1)
for s in lmelp_hold lmelps_hold; do
  python3 gen_eval.py run r7_v32h $s --root $R --np 1; echo "$(date +%T) v32 $s"
  PYTHONHASHSEED=0 python3 v3/cf_holdjobs.py $s 0 1 > runs/cf_$s.0.log 2>&1; echo "$(date +%T) cf $s"
done
echo R7HOLDFIXDONE
