#!/bin/bash
# H7 单次评测（预登记 ba33762；v12 冻结 74edd70）。机器 2 核且另有两条线在跑：打分进程同时只开 1 个（全部串行）。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h7; R=/workspace/work/ls/chainrun
cd $B
timeout 300 env LC_DUMP=$D/lc_sent_v12.json python3 ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v12.json 2>$R/h7_lc12.err
timeout 300 env LC_DUMP=$D/lc_sent_noshort.json LINGSHU_NG_CHAIN_SHORT=0 python3 ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_noshort.json 2>$R/h7_lcns.err
(cd /tmp && FP_ROOT=/workspace/work/ls/chain_v9_snap LC_DUMP=$D/lc_sent_v9.json timeout 300 python3 $B/ledger_cov.py set $D/rewrite_map.json > $D/ledger_cov_v9.json 2>$R/h7_lc9.err)
HO_DIR=$D timeout 300 python3 heldout_eval.py cov > $R/h7_cov_sent.log 2>&1
# 耗时：交替子进程（v9、v12 交替 3 轮，每次子进程内 5 次取中位）
(cd /tmp && for i in 1 2 3; do python3 $B/r10_tools.py time /workspace/work/ls/chain_v9_snap >> $D/time_v9.jsonl; python3 $B/r10_tools.py time /workspace/work/ls/wt-chain >> $D/time_v12.jsonl; done)
for c in h100 h50; do
  for a in ng ngchain ngchain_v9 ngchain_noshort bm25; do
    HO_DIR=$D timeout 300 python3 heldout_eval.py rank $c $a > $R/h7_rank_${c}_$a.log 2>&1
  done
done
FP_OFF=800000 timeout 300 python3 ledger_cov.py fp held > $D/fp_held_v12.json 2>$R/h7_fp12.err
(cd /tmp && FP_OFF=800000 FP_ROOT=/workspace/work/ls/chain_v9_snap timeout 300 python3 $B/ledger_cov.py fp held > $D/fp_held_v9.json 2>$R/h7_fp9.err)
for c in h100 h50; do HO_DIR=$D timeout 1100 python3 heldout_eval.py score $c > $R/h7_score_$c.log 2>&1; done
echo ALLDONE
