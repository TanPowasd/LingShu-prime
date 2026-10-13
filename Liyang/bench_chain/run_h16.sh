#!/bin/bash
# H16 + R20 单次评测（PREREG_R20.md；v20 冻结代码 98cc7922）。全串行，单打分进程。三臂：v19r（判据基准）、v20（缺省）、v9（参照）。零 LLM。口径 LC_ML=1。断点续跑。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h16; R=/workspace/work/ls
V9=$R/chain_v9_snap; V19R=$R/chain_v19r_snap
export LC_ML=1 LINGSHU_NG_CHAIN_LLM=0
cd /tmp
step() { local out=$1; shift; [ -s "$out" ] && grep -q '"tag"' "$out" && return 0; "$@" > "$out.tmp" && mv "$out.tmp" "$out"; }
step $D/cov_v20.json   timeout 900 python3 $B/r20_h16.py cov v20
step $D/cov_v19r.json  timeout 900 env FP_ROOT=$V19R python3 $B/r20_h16.py cov v19r
step $D/cov_v9.json    timeout 900 env FP_ROOT=$V9 python3 $B/r20_h16.py cov v9
for x in "v20 v19r" "v20 v9" "v19r v9"; do python3 $B/r20_h16.py sign $x; done > $D/sign.jsonl
for t in 1 2 3; do step $D/fp_r20_v20.json  timeout 1100 python3 $B/r20_h16.py fp v20; done
for t in 1 2 3; do step $D/fp_r20_v19r.json timeout 1100 env FP_ROOT=$V19R python3 $B/r20_h16.py fp v19r; done
for t in 1 2 3; do step $D/fp_r20_v9.json   timeout 1100 env FP_ROOT=$V9 python3 $B/r20_h16.py fp v9; done
if ! grep -q DONE $D/time_abba.jsonl 2>/dev/null; then
  rm -f $D/time_abba.jsonl
  for i in 1 2 3 4 5 6 7 8 9; do
    if [ $((i % 2)) -eq 1 ]; then o="$V19R $R/wt-chain"; else o="$R/wt-chain $V19R"; fi
    for r in $o; do python3 $B/r10_tools.py time $r | sed "s/^{/{\"round\": $i, /" >> $D/time_abba.jsonl; done
  done
  echo DONE >> $D/time_abba.jsonl
fi
echo ALLDONE
