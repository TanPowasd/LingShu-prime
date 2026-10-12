#!/bin/bash
# H8 单次评测（预登记 PREREG_R12.md；A/B 冻结提交见 git log）。全串行，单打分进程。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h8; R=/workspace/work/ls/chainrun
V9=/workspace/work/ls/chain_v9_snap; V12=/workspace/work/ls/chain_v12_snap
export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
cd /tmp
timeout 900 python3 $B/r12_h8.py cov A > $D/cov_A.json 2>$R/h8_A.err
timeout 900 env LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_B.jsonl python3 $B/r12_h8.py cov B > $D/cov_B.json 2>$R/h8_B.err
timeout 900 env LINGSHU_NG_CHAIN_LLM=1 python3 $B/r12_h8.py cov B_warm > $D/cov_B_warm.json 2>$R/h8_Bw.err
timeout 900 env FP_ROOT=$V12 python3 $B/r12_h8.py cov v12 > $D/cov_v12.json 2>$R/h8_v12.err
timeout 900 env FP_ROOT=$V9 python3 $B/r12_h8.py cov v9 > $D/cov_v9.json 2>$R/h8_v9.err
timeout 900 env FP_ROOT=$V12 LINGSHU_NG_CHAIN_SHORT=0 python3 $B/r12_h8.py cov v12_noshort > $D/cov_v12_noshort.json 2>$R/h8_v12ns.err
for x in "A v9" "B v9" "A v12" "B v12" "B A"; do python3 $B/r12_h8.py sign $x; done > $D/sign.jsonl
# 误登记 held（e2e 奇数文件 100 万–120 万字 + 小说奇数块第六次读）
timeout 900 env FP_OFF=1000000 python3 $B/r12_h8.py fp A > $D/fp_held_A.json 2>$R/h8_fpA.err
timeout 900 env FP_OFF=1000000 LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_B_fp.jsonl python3 $B/r12_h8.py fp B > $D/fp_held_B.json 2>$R/h8_fpB.err
timeout 900 env FP_OFF=1000000 FP_ROOT=$V9 python3 $B/r12_h8.py fp v9 > $D/fp_held_v9.json 2>$R/h8_fp9.err
timeout 900 env FP_OFF=1000000 FP_ROOT=$V12 python3 $B/r12_h8.py fp v12 > $D/fp_held_v12.json 2>$R/h8_fp12.err
# 耗时：交替子进程（v9、A 交替 3 轮，每次子进程内 5 次取中位）；B 臂（热缓存）另报
for i in 1 2 3; do python3 $B/r10_tools.py time $V9 >> $D/time_v9.jsonl; python3 $B/r10_tools.py time /workspace/work/ls/wt-chain >> $D/time_A.jsonl; done
for i in 1 2; do LINGSHU_NG_CHAIN_LLM=1 python3 $B/r10_tools.py time /workspace/work/ls/wt-chain >> $D/time_B_warm.jsonl; done
echo ALLDONE
