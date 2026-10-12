#!/bin/bash
# H9 单次评测（预登记 PREREG_R13.md；A/B 冻结提交见 git log）。全串行，单打分进程。
set -u
B=/workspace/work/ls/wt-chain/bench_chain; D=$B/out/heldout_h9; R=/workspace/work/ls/chainrun
V9=/workspace/work/ls/chain_v9_snap; V12=/workspace/work/ls/chain_v12_snap
export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
cd /tmp
timeout 900 python3 $B/r13_h9.py cov v13 > $D/cov_v13.json 2>$R/h9_v13.err
timeout 900 env LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_v13B.jsonl python3 $B/r13_h9.py cov v13B > $D/cov_v13B.json 2>$R/h9_v13B.err
timeout 900 env LINGSHU_NG_CHAIN_LLM=1 python3 $B/r13_h9.py cov v13B_warm > $D/cov_v13B_warm.json 2>$R/h9_v13Bw.err
timeout 900 env FP_ROOT=$V12 python3 $B/r13_h9.py cov v12 > $D/cov_v12.json 2>$R/h9_v12.err
timeout 900 env FP_ROOT=$V9 python3 $B/r13_h9.py cov v9 > $D/cov_v9.json 2>$R/h9_v9.err
timeout 900 env FP_ROOT=$V12 LINGSHU_NG_CHAIN_SHORT=0 python3 $B/r13_h9.py cov v12_noshort > $D/cov_v12_noshort.json 2>$R/h9_v12ns.err
for x in "v13 v9" "v13B v9" "v13 v12" "v12 v9" "v13B v13"; do python3 $B/r13_h9.py sign $x; done > $D/sign.jsonl
# 误登记 held（e2e 奇数文件 120 万–140 万字 + 小说奇数块第七次读）
timeout 900 env FP_OFF=1200000 python3 $B/r13_h9.py fp v13 > $D/fp_held_v13.json 2>$R/h9_fpv13.err
timeout 900 env FP_OFF=1200000 LINGSHU_NG_CHAIN_LLM=1 LINGSHU_NG_CHAIN_LLM_COSTLOG=$D/llm_cost_v13B_fp.jsonl python3 $B/r13_h9.py fp v13B > $D/fp_held_v13B.json 2>$R/h9_fpv13B.err
timeout 900 env FP_OFF=1200000 FP_ROOT=$V9 python3 $B/r13_h9.py fp v9 > $D/fp_held_v9.json 2>$R/h9_fp9.err
timeout 900 env FP_OFF=1200000 FP_ROOT=$V12 python3 $B/r13_h9.py fp v12 > $D/fp_held_v12.json 2>$R/h9_fp12.err
# 耗时：交替子进程（v9、A 交替 3 轮，每次子进程内 5 次取中位）；B 臂（热缓存）另报
for i in 1 2 3; do python3 $B/r10_tools.py time $V9 >> $D/time_v9.jsonl; python3 $B/r10_tools.py time /workspace/work/ls/wt-chain >> $D/time_v13.jsonl; done
for i in 1 2; do LINGSHU_NG_CHAIN_LLM=1 python3 $B/r10_tools.py time /workspace/work/ls/wt-chain >> $D/time_v13B_warm.jsonl; done
echo ALLDONE
