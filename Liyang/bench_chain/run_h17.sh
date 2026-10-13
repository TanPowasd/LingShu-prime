#!/bin/bash
# H17 单次评测（PREREG_R21.md；v21 冻结代码）。全串行，单打分进程。三臂：v19r（判据基准）、v21（缺省）、v9（参照）。零 LLM。LC_ML=1。断点续跑。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h17; R=/workspace/work/ls
V9=$R/chain_v9_snap; V19R=$R/chain_v19r_snap; V16=$R/chain_v16_snap
export LC_ML=1 LINGSHU_NG_CHAIN_LLM=0
unset LINGSHU_NG_CHAIN_V21_FAM LINGSHU_NG_CHAIN_V21_BGATE
cd /tmp
step() { local out=$1; shift; [ -s "$out" ] && grep -q '"tag"' "$out" && return 0; "$@" > "$out.tmp" && mv "$out.tmp" "$out"; }
step $D/cov_v21.json   timeout 900 python3 $B/r21_h17.py cov v21
step $D/cov_v19r.json  timeout 900 env FP_ROOT=$V19R python3 $B/r21_h17.py cov v19r
step $D/cov_v9.json    timeout 900 env FP_ROOT=$V9 python3 $B/r21_h17.py cov v9
for x in "v21 v19r" "v21 v9" "v19r v9"; do python3 $B/r21_h17.py sign $x; done > $D/sign.jsonl
for t in 1 2 3; do grep -q '"done": true' $R/_r21/fp_h17_v21.json 2>/dev/null || timeout 1100 env FP_BUDGET=1000 python3 $B/r21_fp.py h17_v21 adv,novel,r20 > $D/fp_v21.out 2>&1; done
for t in 1 2 3; do grep -q '"done": true' $R/_r21/fp_h17_v19r.json 2>/dev/null || timeout 1100 env FP_ROOT=$V19R FP_BUDGET=1000 python3 $B/r21_fp.py h17_v19r adv,novel,r20 > $D/fp_v19r.out 2>&1; done
for t in 1 2 3; do grep -q '"done": true' $R/_r21/fp_h17_v16.json 2>/dev/null || timeout 1100 env FP_ROOT=$V16 FP_BUDGET=1000 python3 $B/r21_fp.py h17_v16 adv,novel,r20 > $D/fp_v16.out 2>&1; done
for t in 1 2 3; do grep -q '"done": true' $R/_r21/fp_h17_v9.json 2>/dev/null || timeout 1100 env FP_ROOT=$V9 FP_BUDGET=1000 python3 $B/r21_fp.py h17_v9 adv,novel,r20 > $D/fp_v9.out 2>&1; done
if ! grep -q DONE $D/time_abba.jsonl 2>/dev/null; then
  rm -f $D/time_abba.jsonl
  for i in 1 2 3 4 5 6 7 8 9; do
    if [ $((i % 2)) -eq 1 ]; then o="$V19R $R/wt-chain"; else o="$R/wt-chain $V19R"; fi
    for r in $o; do python3 $B/r10_tools.py time $r | sed "s/^{/{\"round\": $i, /" >> $D/time_abba.jsonl; done
  done
  echo DONE >> $D/time_abba.jsonl
fi
echo ALLDONE
