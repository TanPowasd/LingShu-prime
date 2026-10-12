#!/bin/bash
# v7.1 门（续）：沙箱重启后 /tmp 清空 → 重建英文 gen 作业；T2R2 语义件每进程约 1G → T2R_NP=2
cd /workspace/work/ls/wt-zh/bench_zh
O=runs/t2r2/v71
while [ ! -f $O/all.done ]; do sleep 20; done
V7='LINGSHU_NG_ASSOC={"tp_head":5,"sem_n":40,"sem_tau":-3.25,"sem_min":3,"sem_paths":"tp,lc"}'
T2R_SET=t2r2 T2R_NP=2 timeout 4000 python3 t2r_eval.py ng v71_r1dev r1dev /workspace/work/ls/wt-zh "$V7" > $O/r1dev.log 2>&1; echo rc=$? >> $O/r1dev.log
T2R_SET=t2r2 T2R_NP=2 timeout 7000 python3 t2r_eval.py ng v71_r1test r1test /workspace/work/ls/wt-zh "$V7" > $O/r1test.log 2>&1; echo rc=$? >> $O/r1test.log
cd ../bench_gen
python3 gen_eval.py prep > ../bench_zh/$O/gen_prep.log 2>&1
for s in loc_dev lme_dev; do timeout 2500 python3 gen_eval.py run zhv71 $s --root /workspace/work/ls/wt-zh --np 2 > ../bench_zh/$O/engate_$s.log 2>&1; python3 gen_eval.py score zhv71 $s >> ../bench_zh/$O/engate_$s.log 2>&1; done
echo ALLDONE > ../bench_zh/$O/all2.done
