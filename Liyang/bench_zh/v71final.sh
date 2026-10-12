#!/bin/bash
# v7.1 交付 HEAD（代码缺省，无 env）核对：状态链门 / r1test = v7 / r1dev = s7e / 无模型 r1test = v4 / HMB = v4 / 英文 / tests_ng
cd /workspace/work/ls/wt-zh/bench_zh
O=runs/t2r2/v71
timeout 900 python3 gate_chain.py /workspace/work/ls/wt-zh v71headc ZH_DET=1 > $O/gate_chain_head.log 2>&1; echo rc=$? >> $O/gate_chain_head.log
T2R_SET=t2r2 T2R_NP=2 timeout 4000 python3 t2r_eval.py ng v71head r1test > $O/head_r1test.log 2>&1; echo rc=$? >> $O/head_r1test.log
T2R_SET=t2r2 T2R_NP=2 timeout 4000 python3 t2r_eval.py ng v71head r1dev > $O/head_r1dev.log 2>&1; echo rc=$? >> $O/head_r1dev.log
T2R_SET=t2r2 T2R_NP=2 timeout 4000 python3 t2r_eval.py ng v71nomodel r1test /workspace/work/ls/wt-zh LINGSHU_NG_SEM=off > $O/nomodel_r1test.log 2>&1; echo rc=$? >> $O/nomodel_r1test.log
timeout 1500 python3 zh_eval.py run v71head ZH_DET=1 > $O/hmb_head.log 2>&1; echo rc=$? >> $O/hmb_head.log
cd ../bench_gen
for s in loc_dev lme_dev; do timeout 2500 python3 gen_eval.py run zhv71h $s --root /workspace/work/ls/wt-zh --np 2 > ../bench_zh/$O/engate_head_$s.log 2>&1; python3 gen_eval.py score zhv71h $s >> ../bench_zh/$O/engate_head_$s.log 2>&1; done
cd ..
timeout 3000 python3 -m pytest -q tests_ng -p no:cacheprovider > bench_zh/$O/tests_ng_head.log 2>&1; echo rc=$? >> bench_zh/$O/tests_ng_head.log
echo ALLDONE > bench_zh/$O/final.done
