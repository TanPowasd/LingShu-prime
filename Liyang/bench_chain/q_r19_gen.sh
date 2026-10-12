#!/bin/bash
# H14 生成（断点续跑：gen_raw 逐段落盘）
cd /workspace/work/ls/wt-chain/bench_chain
export HO_VARIANT=h15 HO_BUDGET=0.94 LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
for i in 1 2 3 4 5 6; do
  timeout 1100 python3 heldout_gen.py run 1000 >> out/heldout_h15/gen.log 2>&1
  python3 -c "
import json,sys
sys.argv=['x']
" 
  grep -q "segs \([0-9]*\)/\1 " out/heldout_h15/gen.log && break
done
echo GENDONE >> out/heldout_h15/gen.log
