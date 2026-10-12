#!/bin/bash
cd /workspace/work/ls/wt-chain/bench_chain
for i in 1 2 3 4 5 6 7 8; do
  FP_ROOT=/workspace/work/ls/chain_v9_snap SEL_BUDGET=900 timeout 1100 python3 r18_h14.py sel >> out/heldout_h14/sel.log 2>&1
  tail -1 out/heldout_h14/sel.log | grep -q '"done": true' && break
  python3 -c "import json;import r18_h14 as M;s=json.load(open('out/heldout_h14/r18_sel.json'));import sys;sys.exit(0 if len(s['windows'])>=len(M.windows()) else 1)" && break
done
echo SELDONE >> out/heldout_h14/sel.log
