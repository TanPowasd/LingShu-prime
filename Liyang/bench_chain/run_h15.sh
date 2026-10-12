#!/bin/bash
# H15 + R19 单次评测（预登记 PREREG_R19.md；v19 冻结代码）。全串行，单打分进程。四臂：v16（判据基准）、v19（缺省）、v19x（只报告）、v9。零 LLM，不跑 B。
# 口径：LC_ML=1。断点续跑：已有输出的步骤跳过。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h15; R=/workspace/work/ls
V9=$R/chain_v9_snap; V16=$R/chain_v16_snap; V17=$R/chain_v17_snap
export LC_ML=1 LINGSHU_NG_CHAIN_LLM=0
cd /tmp
step() { local out=$1; shift; [ -s "$out" ] && grep -q '"tag"' "$out" && return 0; "$@" > "$out.tmp" && mv "$out.tmp" "$out"; }
step $D/cov_v19.json   timeout 900 python3 $B/r19_h15.py cov v19
step $D/cov_v16.json   timeout 900 env FP_ROOT=$V16 python3 $B/r19_h15.py cov v16
step $D/cov_v19x.json  timeout 900 env LINGSHU_NG_CHAIN_V18_FAM=L,U,C,E LINGSHU_NG_CHAIN_V19_FAM=S,P,A,V,K python3 $B/r19_h15.py cov v19x
step $D/cov_v9.json    timeout 900 env FP_ROOT=$V9 python3 $B/r19_h15.py cov v9
for x in "v19 v16" "v19x v16" "v19x v19" "v19 v9" "v16 v9"; do python3 $B/r19_h15.py sign $x; done > $D/sign.jsonl
for t in 1 2 3; do step $D/fp_r19_v19.json  timeout 1100 python3 $B/r19_h15.py fp v19; done
for t in 1 2 3; do step $D/fp_r19_v16.json  timeout 1100 env FP_ROOT=$V16 python3 $B/r19_h15.py fp v16; done
for t in 1 2 3; do step $D/fp_r19_v19x.json timeout 1100 env LINGSHU_NG_CHAIN_V18_FAM=L,U,C,E LINGSHU_NG_CHAIN_V19_FAM=S,P,A,V,K python3 $B/r19_h15.py fp v19x; done
for t in 1 2 3; do step $D/fp_r19_v9.json   timeout 1100 env FP_ROOT=$V9 python3 $B/r19_h15.py fp v9; done
if [ ! -s $D/time_v19.jsonl ]; then
  for i in 1 2 3; do python3 $B/r10_tools.py time $V16 >> $D/time_v16.jsonl; python3 $B/r10_tools.py time $R/wt-chain >> $D/time_v19.jsonl; done
fi
if [ ! -s $D/ptime_v19.jsonl ]; then
  for i in 1 2 3; do python3 $B/r16_time.py $V16 0 16 >> $D/ptime_v16.jsonl; python3 $B/r16_time.py $R/wt-chain 0 16 >> $D/ptime_v19.jsonl; done
fi
echo ALLDONE
