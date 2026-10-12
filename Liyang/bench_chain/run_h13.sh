#!/bin/bash
# H13 + R17 单次评测（预登记 PREREG_R17.md；v17 冻结＝冻结提交代码）。全串行，单打分进程。四臂：v16（上次推送版）、v17、v17+B、v9。
# 口径：LC_ML=1（多行改写句按行归并，各臂一致）。断点续跑：已有输出的步骤跳过。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h13; R=/workspace/work/ls
V9=$R/chain_v9_snap; V16=$R/chain_v16_snap
export LINGSHU_LLM_CACHE=$R/_shared/llm_cache LC_ML=1
cd /tmp
step() { local out=$1; shift; [ -s "$out" ] && grep -q '"tag"' "$out" && return 0; "$@" > "$out.tmp" && mv "$out.tmp" "$out"; }
step $D/cov_v17.json   timeout 900 python3 $B/r17_h13.py cov v17
step $D/cov_v16.json   timeout 900 env FP_ROOT=$V16 python3 $B/r17_h13.py cov v16
step $D/cov_v17B.json  timeout 900 env LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_v17B.jsonl python3 $B/r17_h13.py cov v17B
step $D/cov_v9.json    timeout 900 env FP_ROOT=$V9 python3 $B/r17_h13.py cov v9
for x in "v17 v16" "v17 v9" "v16 v9" "v17B v17" "v17B v16"; do python3 $B/r17_h13.py sign $x; done > $D/sign.jsonl
step $D/fp_r17_v17.json  timeout 1100 python3 $B/r17_h13.py fp v17
step $D/fp_r17_v16.json  timeout 1100 env FP_ROOT=$V16 python3 $B/r17_h13.py fp v16
step $D/fp_r17_v9.json   timeout 1100 env FP_ROOT=$V9 python3 $B/r17_h13.py fp v9
step $D/fp_r17_v17B.json timeout 1100 env LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_v17B_fp.jsonl python3 $B/r17_h13.py fp v17B
if [ ! -s $D/time_v17.jsonl ]; then
  for i in 1 2 3; do python3 $B/r10_tools.py time $V16 >> $D/time_v16.jsonl; python3 $B/r10_tools.py time $R/wt-chain >> $D/time_v17.jsonl; done
fi
if [ ! -s $D/ptime_v17.jsonl ]; then
  for i in 1 2 3; do python3 $B/r16_time.py $V16 0 16 >> $D/ptime_v16.jsonl; python3 $B/r16_time.py $R/wt-chain 0 16 >> $D/ptime_v17.jsonl; done
fi
echo ALLDONE
