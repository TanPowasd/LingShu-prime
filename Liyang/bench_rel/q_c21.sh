#!/bin/bash
# chain-r21b 合入后 rel-v1.9 候选回归门（串行、断点续跑）：tests_ng + gate_rel 四段（cn/chainzh/t2r/hmbzh）+ gen loc_dev/LME dev 无模型 tag rel19（--np 1，对 rel18 逐题）
R=/workspace/work/ls/wt-rel; L=$R/bench_rel/logs; export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
python3 -c "import onnxruntime, tokenizers" 2>/dev/null || bash /workspace/work/ls/env_reinstall.sh
[ -s $L/tests_c21.log ] && grep -q EXIT $L/tests_c21.log || { (cd $R && timeout 1150 python3 -m pytest tests_ng -q -p no:cacheprovider > $L/tests_c21.log 2>&1; echo "EXIT $?" >> $L/tests_c21.log); }
echo "$(date +%T) tests" >> $L/q_c21.log
[ -s /tmp/gen_jobs/loc_dev.jsonl ] || (cd $R/bench_gen && python3 gen_eval.py prep > $L/gen_prep_c21.log 2>&1)
for st in cn chainzh t2r hmbzh; do grep -q "^EXIT" $L/$st.c21done 2>/dev/null && continue; bash $R/bench_rel/gate_rel.sh $st; cp $L/$st.log $L/$st.c21done; echo "$(date +%T) $st" >> $L/q_c21.log; done
cd $R/bench_gen
for s in loc_dev lme_dev; do grep -q "^DONE $s" $L/gen_rel19.log 2>/dev/null && continue; G1_FROZEN_CLOCK=1 GEN_DB_CACHE=/workspace/work/ls/_shared/ls_cache_rel19 timeout 1150 python3 gen_eval.py run rel19 $s --root $R --np 1 >> $L/gen_rel19.log 2>&1; python3 gen_eval.py score rel19 $s >> $L/gen_rel19.log 2>&1 && echo "DONE $s" >> $L/gen_rel19.log; echo "$(date +%T) gen $s" >> $L/q_c21.log; done
echo GATE_C21_DONE >> $L/q_c21.log
