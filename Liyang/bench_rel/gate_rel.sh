#!/bin/bash
# rel-v1 集成回归门：集成树须与各线冻结交付逐题相同（中文 v7.1、英文 gen-v3.2），且 HMB/状态链/tests_ng 过门。
# 用法：gate_rel.sh <stage>；每段 ≤1150s（工具后台上限），日志 bench_rel/logs/<stage>.log
R=/workspace/work/ls/wt-rel; L=$R/bench_rel/logs; export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
st=$1; exec > $L/$st.log 2>&1; echo "start $(date +%T)"
case $st in
 cn) cd $R/bench_gen; G1_FROZEN_CLOCK=1760000000 timeout 1150 python3 gate_cn.py $R relhead_fz ;;
 chainzh) cd $R/bench_zh; timeout 1150 python3 gate_chain.py $R relheadc ZH_DET=1 ;;
 t2r) cd $R/bench_zh; T2R_SET=t2r2 T2R_NP=2 timeout 1150 python3 t2r_eval.py ng relhead r1test $R ;;
 hmbzh) cd $R/bench_zh; timeout 1150 python3 zh_eval.py run relhead ZH_DET=1 ;;
 gen_*) s=${st#gen_}; cd $R/bench_gen; G1_FROZEN_CLOCK=1 GEN_DB_CACHE=/tmp/ls_cache/rel timeout 1150 python3 gen_eval.py run relhead $s --root $R --np 2; python3 gen_eval.py score relhead $s ;;
esac
echo "EXIT $? $(date +%T)"
