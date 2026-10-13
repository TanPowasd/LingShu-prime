#!/bin/bash
# chain-r21 生成（PREREG_R21 §1–§3）：H17 → D6 → R21adv，串行，断点续跑
cd /workspace/work/ls/wt-chain/bench_chain
export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
for v in h17:0.9981 d6:1.0481; do
  V=${v%%:*}; B=${v##*:}
  for i in 1 2 3 4 5 6; do
    HO_VARIANT=$V HO_BUDGET=$B timeout 1100 python3 heldout_gen.py run 1000 >> out/heldout_$V/gen.log 2>&1
    grep -q "segs \([0-9]*\)/\1 " out/heldout_$V/gen.log && break
  done
  HO_VARIANT=$V python3 heldout_gen.py build >> out/heldout_$V/gen.log 2>&1
done
ADV_BUDGET=1.1281 timeout 1100 python3 r21_adv.py gen >> out/r21_adv/gen.log 2>&1
echo GENDONE >> out/r21_adv/gen.log
