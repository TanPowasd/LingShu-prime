#!/bin/bash
# zh-v12b：m3 已在 250 题处停（门槛已数学上不可达），续跑 v2m3 全 400，再跑 base（基线参照）
cd /workspace/work/ls/wt-zh/bench_zh
export LINGSHU_NG_SEM=/workspace/work/ls/_shared/models LINGSHU_NG_SEM_THREADS=2
L=runs/t2r2/v12
LINGSHU_NG_SEM_MODEL=bge-reranker-v2-m3 python3 v12/score_cross.py >> $L/sc_v2m3.log 2>&1
LINGSHU_NG_SEM_MODEL=bge-reranker-base python3 v12/score_cross.py > $L/sc_base.log 2>&1
touch $L/score3.done
