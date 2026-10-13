#!/bin/bash
# R20 选段（PREREG_R20 §3）：v19r 只计数，累计 ≥100 停；断点续跑
cd /workspace/work/ls/wt-chain/bench_chain; export LINGSHU_NG_CHAIN_LLM=0
for i in 1 2 3; do FP_ROOT=/workspace/work/ls/chain_v19r_snap SEL_BUDGET=900 timeout 1000 python3 r20_h16.py sel >> out/heldout_h16/sel.log 2>&1; grep -q '"done": true' out/heldout_h16/sel.log && break; grep -q '"n_win"' out/heldout_h16/sel.log && tail -1 out/heldout_h16/sel.log | grep -q '"done": false' && [ $(python3 -c "import json;d=json.load(open('out/heldout_h16/r20_sel.json'));print(len(d['windows']))") -ge 9999 ] && break; done
echo SELDONE >> out/heldout_h16/sel.log
