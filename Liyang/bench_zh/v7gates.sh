#!/bin/bash
# v7 回归门（PREREG_ZH 修订 5.3 ①）：HEAD 代码缺省（sem_n=0）+ v7 配置两种下的 tests_ng / 状态链门 / HMB T2 / 英文 gen dev
cd /workspace/work/ls/wt-zh
timeout 3000 python3 -m pytest -q tests_ng -p no:cacheprovider > bench_zh/runs/t2r2/gate_tests_ng.log 2>&1; echo rc=$? >> bench_zh/runs/t2r2/gate_tests_ng.log
cd bench_zh
V7='LINGSHU_NG_ASSOC={"tp_head":5,"sem_n":40,"sem_tau":-3.25,"sem_min":3,"sem_paths":"tp,lc"}'
timeout 1500 python3 zh_eval.py run v7full ZH_DET=1 "$V7" > runs/t2r2/gate_hmb_v7.log 2>&1
timeout 900 python3 gate_chain.py /workspace/work/ls/wt-zh v7c ZH_DET=1 > runs/t2r2/gate_chain_v7.log 2>&1; echo rc=$? >> runs/t2r2/gate_chain_v7.log
# 补（收尾时发现原版漏了 v7 配置下的状态链门）：
timeout 900 python3 gate_chain.py /workspace/work/ls/wt-zh v7envc ZH_DET=1 "$V7" > runs/t2r2/gate_chain_v7env.log 2>&1; echo rc=$? >> runs/t2r2/gate_chain_v7env.log
cd ../bench_gen
for s in loc_dev lme_dev; do timeout 1500 python3 gen_eval.py run zhv7 $s --root /workspace/work/ls/wt-zh --np 2 > ../bench_zh/runs/t2r2/engate_v7_$s.log 2>&1; python3 gen_eval.py score zhv7 $s >> ../bench_zh/runs/t2r2/engate_v7_$s.log 2>&1; done
echo ALLDONE > ../bench_zh/runs/t2r2/v7gates.done
