#!/bin/bash
# zh-v12 打分队列（可重复执行续跑）
cd /workspace/work/ls/wt-zh/bench_zh
export LINGSHU_NG_SEM=/workspace/work/ls/_shared/models LINGSHU_NG_SEM_THREADS=2
L=runs/t2r2/v12
LINGSHU_NG_SEM_MODEL=bge-reranker-base python3 v12/score_cross.py > $L/sc_base.log 2>&1
LINGSHU_NG_SEM_MODEL=bge-reranker-v2-m3 python3 v12/score_cross.py > $L/sc_v2m3.log 2>&1
while [ ! -f /workspace/work/ls/_shared/models/bge-m3-int8/model_quantized.onnx ]; do sleep 20; done
python3 v12/m3enc.py > $L/m3.log 2>&1
touch $L/score.done
