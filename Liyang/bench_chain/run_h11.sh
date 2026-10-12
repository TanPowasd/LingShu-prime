#!/bin/bash
# H11 + R15 单次评测（预登记 PREREG_R15.md；v15 冻结＝e805a7d 代码）。全串行，单打分进程。四臂：v13.1、v15、v15+B、v9。断点续跑：已有输出的步骤跳过。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h11; R=/workspace/work/ls/chainrun
V9=/workspace/work/ls/chain_v9_snap; V131=/workspace/work/ls/chain_v131_snap
export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
cd /tmp
step() { local out=$1; shift; [ -s "$out" ] && grep -q '"tag"' "$out" && return 0; "$@" > "$out.tmp" && mv "$out.tmp" "$out"; }
step $D/cov_v15.json   timeout 900 python3 $B/r15_h11.py cov v15
step $D/cov_v131.json  timeout 900 env FP_ROOT=$V131 python3 $B/r15_h11.py cov v131
step $D/cov_v15B.json  timeout 900 env LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_v15B.jsonl python3 $B/r15_h11.py cov v15B
step $D/cov_v9.json    timeout 900 env FP_ROOT=$V9 python3 $B/r15_h11.py cov v9
for x in "v15 v131" "v15 v9" "v131 v9" "v15B v15" "v15B v131"; do python3 $B/r15_h11.py sign $x; done > $D/sign.jsonl
step $D/fp_r15_v15.json  timeout 1100 python3 $B/r15_h11.py fp v15
step $D/fp_r15_v131.json timeout 1100 env FP_ROOT=$V131 python3 $B/r15_h11.py fp v131
step $D/fp_r15_v9.json   timeout 1100 env FP_ROOT=$V9 python3 $B/r15_h11.py fp v9
step $D/fp_r15_v15B.json timeout 1100 env LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_v15B_fp.jsonl python3 $B/r15_h11.py fp v15B
if [ ! -s $D/time_v15.jsonl ]; then
  for i in 1 2 3; do python3 $B/r10_tools.py time $V131 >> $D/time_v131.jsonl; python3 $B/r10_tools.py time /workspace/work/ls/wt-chain >> $D/time_v15.jsonl; done
fi
echo ALLDONE
