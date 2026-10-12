#!/bin/bash
# H12 + R16 单次评测（预登记 PREREG_R16.md；v16 冻结＝冻结提交代码）。全串行，单打分进程。四臂：v15（上次推送版）、v16、v16+B、v9。
# 口径：LC_ML=1（多行改写句按行归并，各臂一致）。断点续跑：已有输出的步骤跳过。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h12; R=/workspace/work/ls
V9=$R/chain_v9_snap; V15=$R/chain_v15_snap; V131=$R/chain_v131_snap
export LINGSHU_LLM_CACHE=$R/_shared/llm_cache LC_ML=1
cd /tmp
step() { local out=$1; shift; [ -s "$out" ] && grep -q '"tag"' "$out" && return 0; "$@" > "$out.tmp" && mv "$out.tmp" "$out"; }
step $D/cov_v16.json   timeout 900 python3 $B/r16_h12.py cov v16
step $D/cov_v15.json   timeout 900 env FP_ROOT=$V15 python3 $B/r16_h12.py cov v15
step $D/cov_v16B.json  timeout 900 env LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_v16B.jsonl python3 $B/r16_h12.py cov v16B
step $D/cov_v9.json    timeout 900 env FP_ROOT=$V9 python3 $B/r16_h12.py cov v9
for x in "v16 v15" "v16 v9" "v15 v9" "v16B v16" "v16B v15"; do python3 $B/r16_h12.py sign $x; done > $D/sign.jsonl
step $D/fp_r16_v16.json  timeout 1100 python3 $B/r16_h12.py fp v16
step $D/fp_r16_v15.json  timeout 1100 env FP_ROOT=$V15 python3 $B/r16_h12.py fp v15
step $D/fp_r16_v9.json   timeout 1100 env FP_ROOT=$V9 python3 $B/r16_h12.py fp v9
step $D/fp_r16_v16B.json timeout 1100 env LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_v16B_fp.jsonl python3 $B/r16_h12.py fp v16B
if [ ! -s $D/time_v16.jsonl ]; then
  for i in 1 2 3; do python3 $B/r10_tools.py time $V15 >> $D/time_v15.jsonl; python3 $B/r10_tools.py time $R/wt-chain >> $D/time_v16.jsonl; done
fi
if [ ! -s $D/ptime_v16.jsonl ]; then
  for i in 1 2 3; do python3 $B/r16_time.py $V131 0 16 >> $D/ptime_v131.jsonl; python3 $B/r16_time.py $R/wt-chain 0 16 >> $D/ptime_v16.jsonl; done
fi
echo ALLDONE
