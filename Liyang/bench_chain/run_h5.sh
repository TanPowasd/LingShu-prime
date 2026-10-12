#!/bin/bash
# H5 单次评测（预登记 7648499；v10 冻结提交见结果提交说明）。打分进程同时 ≤2。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h5; R=/workspace/work/ls/chainrun
cd $B
timeout 300 env LC_DUMP=$D/lc_sent_v10.json python3 ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v10.json 2>$R/h5_lc10.err
timeout 300 env LC_DUMP=$D/lc_sent_noshort.json LINGSHU_NG_CHAIN_SHORT=0 python3 ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_noshort.json 2>$R/h5_lcns.err
(cd /tmp && FP_ROOT=/workspace/work/ls/chain_v9_snap LC_DUMP=$D/lc_sent_v9.json timeout 300 python3 $B/ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v9.json 2>$R/h5_lc9.err)
(cd /tmp && FP_ROOT=/workspace/work/ls/chain_v8_snap LC_DUMP=$D/lc_sent_v8.json timeout 300 python3 $B/ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v8.json 2>$R/h5_lc8.err)
HO_DIR=$D timeout 300 python3 heldout_eval.py cov > $R/h5_cov_sent.log 2>&1
(cd /tmp && python3 $R/r10_time.py /workspace/work/ls/wt-chain > $D/time_v10.json; python3 $R/r10_time.py /workspace/work/ls/chain_v9_snap > $D/time_v9.json)
for c in h100 h50; do
  for pair in "ng ngchain" "ngchain_v9 ngchain_v8" "ngchain_noshort bm25"; do
    set -- $pair
    HO_DIR=$D timeout 300 python3 heldout_eval.py rank $c $1 > $R/h5_rank_${c}_$1.log 2>&1 &
    HO_DIR=$D timeout 300 python3 heldout_eval.py rank $c $2 > $R/h5_rank_${c}_$2.log 2>&1 &
    wait
  done
done
FP_OFF=400000 timeout 300 python3 ledger_cov.py fp held > $D/fp_held_v10.json 2>$R/h5_fp10.err &
(cd /tmp && FP_OFF=400000 FP_ROOT=/workspace/work/ls/chain_v9_snap timeout 300 python3 $B/ledger_cov.py fp held > $D/fp_held_v9.json 2>$R/h5_fp9.err) &
wait
for c in h100 h50; do HO_DIR=$D timeout 1100 python3 heldout_eval.py score $c > $R/h5_score_$c.log 2>&1 & done
wait
echo ALLDONE
