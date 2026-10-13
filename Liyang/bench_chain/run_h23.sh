#!/bin/bash
# H23 单次评测（PREREG_R27 §5；v27 冻结代码见 PREREG_R27 §4 裁定）。全串行，单打分进程。两臂：v26（判据基准，chain_v26_snap）、v27（缺省）。零 LLM。LC_ML=1。断点续跑。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h23; R=/workspace/work/ls
V26=$R/chain_v26_snap
export LC_ML=1 LINGSHU_NG_CHAIN_LLM=0
unset LINGSHU_NG_CHAIN_V21_FAM LINGSHU_NG_CHAIN_V21_BGATE LINGSHU_NG_CHAIN_V22_FAM LINGSHU_NG_CHAIN_V23_FAM LINGSHU_NG_CHAIN_V24_FAM LINGSHU_NG_CHAIN_V25_FAM LINGSHU_NG_CHAIN_V26_FAM LINGSHU_NG_CHAIN_V27_FAM
cd /tmp
step() { local out=$1; shift; [ -s "$out" ] && grep -q '"tag"' "$out" && return 0; "$@" > "$out.tmp" && mv "$out.tmp" "$out"; }
step $D/cov_v27.json   timeout 900 python3 $B/r27_h23.py cov v27
step $D/cov_v26.json   timeout 900 env FP_ROOT=$V26 python3 $B/r27_h23.py cov v26
python3 $B/r27_h23.py sign v27 v26 > $D/sign.jsonl
for t in 1 2 3; do grep -q '"done": true' $R/_r21/fp_h23_v27.json 2>/dev/null || timeout 1100 env FP_BUDGET=1000 python3 $B/r21_fp.py h23_v27 > $D/fp_v27.out 2>&1; done
if ! grep -q DONE $D/time_abba.jsonl 2>/dev/null; then
  rm -f $D/time_abba.jsonl
  for i in 1 2 3 4 5 6 7 8 9; do
    if [ $((i % 2)) -eq 1 ]; then o="$V26 $R/wt-chain"; else o="$R/wt-chain $V26"; fi
    for r in $o; do python3 $B/r10_tools.py time $r | sed "s/^{/{\"round\": $i, /" >> $D/time_abba.jsonl; done
  done
  echo DONE >> $D/time_abba.jsonl
fi
echo ALLDONE
