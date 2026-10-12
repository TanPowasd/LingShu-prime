#!/bin/bash
# v7.1 回归门（PREREG_ZH 修订 5b）：v7 配置（env）下 状态链门 / r1test 身份核对 / r1dev 身份 / HMB T2 / 英文 dev / tests_ng
cd /workspace/work/ls/wt-zh/bench_zh
O=runs/t2r2/v71
mkdir -p $O
V7='LINGSHU_NG_ASSOC={"tp_head":5,"sem_n":40,"sem_tau":-3.25,"sem_min":3,"sem_paths":"tp,lc"}'
timeout 900 python3 gate_chain.py /workspace/work/ls/wt-zh v71envc ZH_DET=1 "$V7" > $O/gate_chain_v71env.log 2>&1; echo rc=$? >> $O/gate_chain_v71env.log
T2R_SET=t2r2 timeout 3000 python3 t2r_eval.py ng v71_r1dev r1dev /workspace/work/ls/wt-zh "$V7" > $O/r1dev.log 2>&1; echo rc=$? >> $O/r1dev.log
T2R_SET=t2r2 timeout 5000 python3 t2r_eval.py ng v71_r1test r1test /workspace/work/ls/wt-zh "$V7" > $O/r1test.log 2>&1; echo rc=$? >> $O/r1test.log
timeout 1500 python3 zh_eval.py run v71full ZH_DET=1 "$V7" > $O/hmb.log 2>&1; echo rc=$? >> $O/hmb.log
echo STEP1 > $O/step1.done
cd ../bench_gen
for s in loc_dev lme_dev; do timeout 1500 python3 gen_eval.py run zhv71 $s --root /workspace/work/ls/wt-zh --np 2 > ../bench_zh/$O/engate_$s.log 2>&1; python3 gen_eval.py score zhv71 $s >> ../bench_zh/$O/engate_$s.log 2>&1; done
cd ..
timeout 3000 python3 -m pytest -q tests_ng -p no:cacheprovider > bench_zh/$O/tests_ng.log 2>&1; echo rc=$? >> bench_zh/$O/tests_ng.log
echo ALLDONE > bench_zh/$O/all.done
