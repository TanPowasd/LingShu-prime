#!/bin/bash
# H4 单次评测（预登记 009ede8；v9 冻结 ced877c）
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h4; R=/workspace/work/ls/chainrun
cd $B
HO_DIR=$D timeout 300 python3 heldout_eval.py cov > $R/h4_cov_v9_sent.log 2>&1
timeout 300 python3 ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v9.json 2>$R/h4_lc9.err
(cd /tmp && FP_ROOT=/workspace/work/ls/chain_v8_snap timeout 300 python3 $B/ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v8.json 2>$R/h4_lc8.err)
(cd /tmp && FP_ROOT=/workspace/work/ls/chain_v7_snap timeout 300 python3 $B/ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v7.json 2>$R/h4_lc7.err)
for c in h100 h50; do
  for a in ng ngchain ngchain_v8 ngchain_v7 ngchain_noloose bm25; do
    HO_DIR=$D timeout 300 python3 heldout_eval.py rank $c $a > $R/h4_rank_${c}_$a.log 2>&1 &
  done
  wait
done
for c in h100 h50; do HO_DIR=$D timeout 1200 python3 heldout_eval.py score $c > $R/h4_score_$c.log 2>&1 & done
FP_OFF=200000 timeout 300 python3 ledger_cov.py fp held > $D/fp_held_v9.json 2>$R/h4_fp9.err &
(cd /tmp && FP_OFF=200000 FP_ROOT=/workspace/work/ls/chain_v8_snap timeout 300 python3 $B/ledger_cov.py fp held > $D/fp_held_v8.json 2>$R/h4_fp8.err) &
wait
echo ALLDONE
