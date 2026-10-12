#!/bin/bash
# H6 单次评测（预登记 4983b3e；v11 冻结提交见结果提交说明）。打分进程同时 ≤2。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h6; R=/workspace/work/ls/chainrun
cd $B
timeout 300 env LC_DUMP=$D/lc_sent_v11.json python3 ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v11.json 2>$R/h6_lc11.err
timeout 300 env LC_DUMP=$D/lc_sent_noshort.json LINGSHU_NG_CHAIN_SHORT=0 python3 ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_noshort.json 2>$R/h6_lcns.err
(cd /tmp && FP_ROOT=/workspace/work/ls/chain_v9_snap LC_DUMP=$D/lc_sent_v9.json timeout 300 python3 $B/ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v9.json 2>$R/h6_lc9.err)
(cd /tmp && FP_ROOT=/workspace/work/ls/chain_v8_snap LC_DUMP=$D/lc_sent_v8.json timeout 300 python3 $B/ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v8.json 2>$R/h6_lc8.err)
HO_DIR=$D timeout 300 python3 heldout_eval.py cov > $R/h6_cov_sent.log 2>&1
(cd /tmp && for i in 1 2 3; do python3 $B/r10_tools.py time /workspace/work/ls/chain_v9_snap >> $D/time_v9.jsonl; python3 $B/r10_tools.py time /workspace/work/ls/wt-chain >> $D/time_v11.jsonl; done)
for c in h100 h50; do
  for pair in "ng ngchain" "ngchain_v9 ngchain_noshort" "bm25"; do
    for a in $pair; do HO_DIR=$D timeout 300 python3 heldout_eval.py rank $c $a > $R/h6_rank_${c}_$a.log 2>&1 & done
    wait
  done
done
FP_OFF=600000 timeout 300 python3 ledger_cov.py fp held > $D/fp_held_v11.json 2>$R/h6_fp11.err &
(cd /tmp && FP_OFF=600000 FP_ROOT=/workspace/work/ls/chain_v9_snap timeout 300 python3 $B/ledger_cov.py fp held > $D/fp_held_v9.json 2>$R/h6_fp9.err) &
wait
for c in h100 h50; do HO_DIR=$D timeout 1100 python3 heldout_eval.py score $c > $R/h6_score_$c.log 2>&1 & done
wait
echo ALLDONE
