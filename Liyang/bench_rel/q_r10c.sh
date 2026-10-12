#!/bin/bash
# gen-r10c 合入后 rel-v1.8 候选回归门（串行、断点续跑）：tests_ng + gate_rel 四段（cn/chainzh/t2r/hmbzh）
# + gen loc_dev/LME dev 无模型 tag rel18（--np 1，对 rel17 逐题）+ 带模型 lmelp/lmelps_dev（tag rel18emb，wt-gen 的 gen_eval，对 rel15emb 逐题）
R=/workspace/work/ls/wt-rel; L=$R/bench_rel/logs; export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
python3 -c "import onnxruntime, tokenizers" 2>/dev/null || bash /workspace/work/ls/env_reinstall.sh
[ -s $L/tests_r10c.log ] && grep -q EXIT $L/tests_r10c.log || { (cd $R && timeout 1150 python3 -m pytest tests_ng -q -p no:cacheprovider > $L/tests_r10c.log 2>&1; echo "EXIT $?" >> $L/tests_r10c.log); }
echo "$(date +%T) tests" >> $L/q_r10c.log
[ -s /tmp/gen_jobs/loc_dev.jsonl ] || (cd $R/bench_gen && python3 gen_eval.py prep > $L/gen_prep_r10c.log 2>&1)
for st in cn chainzh t2r hmbzh; do grep -q "^EXIT" $L/$st.r10cdone 2>/dev/null && continue; bash $R/bench_rel/gate_rel.sh $st; cp $L/$st.log $L/$st.r10cdone; echo "$(date +%T) $st" >> $L/q_r10c.log; done
cd $R/bench_gen
for s in loc_dev lme_dev; do grep -q "^DONE $s" $L/gen_rel18.log 2>/dev/null && continue; G1_FROZEN_CLOCK=1 GEN_DB_CACHE=/workspace/work/ls/_shared/ls_cache_rel18 timeout 1150 python3 gen_eval.py run rel18 $s --root $R --np 1 >> $L/gen_rel18.log 2>&1; python3 gen_eval.py score rel18 $s >> $L/gen_rel18.log 2>&1 && echo "DONE $s" >> $L/gen_rel18.log; echo "$(date +%T) gen $s" >> $L/q_r10c.log; done
cd /workspace/work/ls/wt-gen/bench_gen
[ -s /tmp/gen_jobs/lmelp_dev.jsonl ] || python3 v3/r7/mk_lp.py > /dev/null
for s in lmelp_dev lmelps_dev; do grep -q "^DONE $s" $L/gen_rel18emb.log 2>/dev/null && continue; G1_FROZEN_CLOCK=1 GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5 python3 gen_eval.py run rel18emb $s --root $R --np 1 >> $L/gen_rel18emb.log 2>&1 && echo "DONE $s" >> $L/gen_rel18emb.log; echo "$(date +%T) emb $s" >> $L/q_r10c.log; done
echo GATE_R10C_DONE >> $L/q_r10c.log
