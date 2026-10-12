#!/bin/bash
# zh-v11 冻结前：候选引擎在 DuRT dev 跑一遍（与离线模拟逐题核对，修订 9.2）
cd /workspace/work/ls/wt-zh/bench_zh
export T2R_SET=durt T2R_NP=1 T2R_PART=1
C='LINGSHU_NG_ASSOC={"sem_dense":20,"sem_dense_m":5,"sem_dense_cap":2,"sem_dense_tau":0.0}'
[ -f runs/durt/v11c_dev.json ] || python3 t2r_eval.py ng v11c dev /workspace/work/ls/wt-zh "$C" > runs/durt/v11c_dev.log 2>&1
echo done > runs/durt/v11/dev.done
