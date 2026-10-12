#!/bin/bash
# zh-v11 修订 9b 冻结后一次判定：DuRT hold2 → T2R2 r1test → Covr dev（链路核对）→ Covr hold → 四臂（报告）。单进程顺序，已有输出跳过（断点续跑）
cd /workspace/work/ls/wt-zh/bench_zh
export T2R_NP=1 T2R_PART=1
W=/workspace/work/ls/wt-zh
C='LINGSHU_NG_ASSOC={"sem_dense":20,"sem_dense_m":5,"sem_dense_cap":2,"sem_dense_tau":0.0}'
run() { set_=$1; tag=$2; sp=$3; shift 3; [ -f runs/$set_/${tag}_$sp.json ] || T2R_SET=$set_ python3 t2r_eval.py ng $tag $sp "$@" > runs/$set_/${tag}_$sp.log 2>&1; }
mkdir -p runs/covr/v11 runs/durt/v11 runs/t2r2/v11
run durt v71 hold2
run durt v11c hold2 $W "$C"
run t2r2 v11c r1test $W "$C"
run covr v71 dev
run covr v11c dev $W "$C"
run covr v71 hold
run covr v11c hold $W "$C"
echo done > runs/durt/v11/core.done
run durt v4 hold2 $W LINGSHU_NG_SEM=off
run covr v4 hold $W LINGSHU_NG_SEM=off
[ -f runs/durt/arms_hold2.json ] || T2R_SET=durt PYTHONHASHSEED=0 python3 t2r_eval.py arms hold2 > runs/durt/arms_hold2.log 2>&1
[ -f runs/covr/arms_hold.json ] || T2R_SET=covr PYTHONHASHSEED=0 python3 t2r_eval.py arms hold > runs/covr/arms_hold.log 2>&1
echo done > runs/durt/v11/all.done
