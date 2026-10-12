#!/bin/bash
# H10 + R14 单次评测（预登记 PREREG_R14.md；v13.1 冻结＝d340e95 代码）。全串行，单打分进程。三臂：v9、v13.1、v13.1+B。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h10; R=/workspace/work/ls/chainrun
V9=/workspace/work/ls/chain_v9_snap
export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
cd /tmp
timeout 900 python3 $B/r14_h10.py cov v131 > $D/cov_v131.json 2>$R/h10_v131.err
timeout 900 env LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_v131B.jsonl python3 $B/r14_h10.py cov v131B > $D/cov_v131B.json 2>$R/h10_v131B.err
timeout 900 env FP_ROOT=$V9 python3 $B/r14_h10.py cov v9 > $D/cov_v9.json 2>$R/h10_v9.err
for x in "v131 v9" "v131B v9" "v131B v131"; do python3 $B/r14_h10.py sign $x; done > $D/sign.jsonl
# 误登记 R14 区段（未读）+ 小说奇数块（第八次读）
timeout 900 python3 $B/r14_h10.py fp v131 > $D/fp_r14_v131.json 2>$R/h10_fpv131.err
timeout 900 env LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_v131B_fp.jsonl python3 $B/r14_h10.py fp v131B > $D/fp_r14_v131B.json 2>$R/h10_fpv131B.err
timeout 900 env FP_ROOT=$V9 python3 $B/r14_h10.py fp v9 > $D/fp_r14_v9.json 2>$R/h10_fp9.err
# 耗时：交替子进程（v9、v13.1 交替 3 轮，每次子进程内 5 次取中位）
for i in 1 2 3; do python3 $B/r10_tools.py time $V9 >> $D/time_v9.jsonl; python3 $B/r10_tools.py time /workspace/work/ls/wt-chain >> $D/time_v131.jsonl; done
echo ALLDONE
