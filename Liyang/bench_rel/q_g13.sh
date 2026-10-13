#!/bin/bash
# gen-r13 合入 F4w（sp_n 40）后 rel-v1.15 候选回归门（串行、断点续跑）：tests_ng + gate_rel 四段（cn/chainzh/t2r/hmbzh）
# + gen loc_dev/LME dev 无模型 tag rel115（--np 1，对 rel114（chain-r27b）逐题）+ 带模型 lmelp/lmelps_dev（tag rel115emb，对 wt-gen r13_dev@w40 逐题，验证发布树≡研究树）
R=/workspace/work/ls/wt-rel; L=$R/bench_rel/logs; export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
python3 -c "import onnxruntime, tokenizers" 2>/dev/null || bash /workspace/work/ls/env_reinstall.sh
[ -L /tmp/gen_jobs ] || bash /workspace/work/ls/wt-gen/bench_gen/v3/r10/build_jobs.sh
[ -s $L/tests_g13.log ] && grep -q EXIT $L/tests_g13.log || { (cd $R && timeout 1150 python3 -m pytest tests_ng -q -p no:cacheprovider > $L/tests_g13.log 2>&1; echo "EXIT $?" >> $L/tests_g13.log); }
echo "$(date +%T) tests" >> $L/q_g13.log
for st in cn chainzh t2r hmbzh; do grep -q "^EXIT" $L/$st.g13done 2>/dev/null && continue; bash $R/bench_rel/gate_rel.sh $st; cp $L/$st.log $L/$st.g13done; echo "$(date +%T) $st" >> $L/q_g13.log; done
cd $R/bench_gen
for s in loc_dev lme_dev; do grep -q "^DONE $s" $L/gen_rel115.log 2>/dev/null && continue; G1_FROZEN_CLOCK=1 GEN_DB_CACHE=/workspace/work/ls/_shared/ls_cache_rel115 timeout 1150 python3 gen_eval.py run rel115 $s --root $R --np 1 >> $L/gen_rel115.log 2>&1; python3 gen_eval.py score rel115 $s >> $L/gen_rel115.log 2>&1 && echo "DONE $s" >> $L/gen_rel115.log; echo "$(date +%T) gen $s" >> $L/q_g13.log; done
cd /workspace/work/ls/wt-gen/bench_gen
for s in lmelp_dev lmelps_dev; do grep -q "^DONE $s" $L/gen_rel115emb.log 2>/dev/null && continue; G1_FROZEN_CLOCK=1 GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5 python3 gen_eval.py run rel115emb $s --root $R --np 1 >> $L/gen_rel115emb.log 2>&1 && echo "DONE $s" >> $L/gen_rel115emb.log; echo "$(date +%T) emb $s" >> $L/q_g13.log; done
echo GATE_G13_DONE >> $L/q_g13.log
