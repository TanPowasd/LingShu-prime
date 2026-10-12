#!/bin/bash
# zh-v11c 合入后 rel-v1.6 候选回归门：tests_ng + gate_rel 四段（cn/chainzh/t2r/hmbzh）+ gen loc_dev/LME dev 无模型 tag rel16（--np 1，对 rel15 逐题）（串行，断点续跑）
R=/workspace/work/ls/wt-rel; L=$R/bench_rel/logs; export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
[ -s $L/tests_zh11.log ] && grep -q EXIT $L/tests_zh11.log || { (cd $R && timeout 1150 python3 -m pytest tests_ng -q -p no:cacheprovider > $L/tests_zh11.log 2>&1; echo "EXIT $?" >> $L/tests_zh11.log); }
(cd $R/bench_gen && python3 gen_eval.py prep > $L/gen_prep_zh11.log 2>&1)
for st in cn chainzh t2r hmbzh; do grep -q "^EXIT" $L/$st.zh11done 2>/dev/null && continue; bash $R/bench_rel/gate_rel.sh $st; cp $L/$st.log $L/$st.zh11done; done
cd $R/bench_gen
for s in loc_dev lme_dev; do grep -q "^DONE $s" $L/gen_rel16.log 2>/dev/null && continue; G1_FROZEN_CLOCK=1 GEN_DB_CACHE=/workspace/work/ls/_shared/ls_cache_rel16 timeout 1150 python3 gen_eval.py run rel16 $s --root $R --np 1 >> $L/gen_rel16.log 2>&1; python3 gen_eval.py score rel16 $s >> $L/gen_rel16.log 2>&1 && echo "DONE $s" >> $L/gen_rel16.log; done
echo GATE_ALL_DONE >> $L/q_zh11.log
