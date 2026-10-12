#!/bin/bash
# H14 + R18 单次评测（预登记 PREREG_R18.md；v18 冻结＝dc29734 代码）。全串行，单打分进程。四臂：v16（上次推送版）、v18、v17（只报告）、v9。零 LLM，不跑 B。
# 口径：LC_ML=1。断点续跑：已有输出的步骤跳过。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h14; R=/workspace/work/ls
V9=$R/chain_v9_snap; V16=$R/chain_v16_snap; V17=$R/chain_v17_snap
export LC_ML=1 LINGSHU_NG_CHAIN_LLM=0
cd /tmp
step() { local out=$1; shift; [ -s "$out" ] && grep -q '"tag"' "$out" && return 0; "$@" > "$out.tmp" && mv "$out.tmp" "$out"; }
step $D/cov_v18.json   timeout 900 python3 $B/r18_h14.py cov v18
step $D/cov_v16.json   timeout 900 env FP_ROOT=$V16 python3 $B/r18_h14.py cov v16
step $D/cov_v17.json   timeout 900 env FP_ROOT=$V17 python3 $B/r18_h14.py cov v17
step $D/cov_v9.json    timeout 900 env FP_ROOT=$V9 python3 $B/r18_h14.py cov v9
for x in "v18 v16" "v18 v17" "v17 v16" "v18 v9" "v16 v9"; do python3 $B/r18_h14.py sign $x; done > $D/sign.jsonl
step $D/fp_r18_v18.json  timeout 1100 python3 $B/r18_h14.py fp v18
step $D/fp_r18_v16.json  timeout 1100 env FP_ROOT=$V16 python3 $B/r18_h14.py fp v16
step $D/fp_r18_v17.json  timeout 1100 env FP_ROOT=$V17 python3 $B/r18_h14.py fp v17
step $D/fp_r18_v9.json   timeout 1100 env FP_ROOT=$V9 python3 $B/r18_h14.py fp v9
if [ ! -s $D/time_v18.jsonl ]; then
  for i in 1 2 3; do python3 $B/r10_tools.py time $V16 >> $D/time_v16.jsonl; python3 $B/r10_tools.py time $R/wt-chain >> $D/time_v18.jsonl; done
fi
if [ ! -s $D/ptime_v18.jsonl ]; then
  for i in 1 2 3; do python3 $B/r16_time.py $V16 0 16 >> $D/ptime_v16.jsonl; python3 $B/r16_time.py $R/wt-chain 0 16 >> $D/ptime_v18.jsonl; done
fi
echo ALLDONE
