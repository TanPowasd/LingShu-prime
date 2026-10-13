#!/bin/bash
cd /workspace/work/ls/wt-zh/bench_zh
export LINGSHU_NG_SEM=/workspace/work/ls/_shared/models LINGSHU_NG_SEM_THREADS=2
L=runs/t2r2/v12
while pgrep -f m3enc.py > /dev/null; do sleep 15; done
[ -f $L/sc_m3.json ] && python3 -c "import json;assert len(json.load(open('$L/sc_m3.json')))==400" || python3 v12/m3enc.py >> $L/m3.log 2>&1
LINGSHU_NG_SEM_MODEL=bge-reranker-base python3 v12/score_cross.py > $L/sc_base.log 2>&1
LINGSHU_NG_SEM_MODEL=bge-reranker-v2-m3 python3 v12/score_cross.py > $L/sc_v2m3.log 2>&1
touch $L/score2.done
