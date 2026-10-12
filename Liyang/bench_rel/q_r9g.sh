#!/bin/bash
# gen-r9 合入后 rel-v1.5 候选回归门（串行、可重入）：tests_ng + gate_rel 四段（cn/chainzh/t2r/hmbzh）+ gen loc_dev/LME dev 新 tag rel15（无模型）
# + 带模型核对：lmelp_dev/lmelps_dev 用 wt-gen 的 gen_eval（GEN_EMBED）跑 --root wt-rel 缺省 cfg（tag rel15emb；对照 relr7emb = rel-v1.1 带模型）
R=/workspace/work/ls/wt-rel; L=$R/bench_rel/logs; export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
python3 -c "import onnxruntime, tokenizers" 2>/dev/null || bash /workspace/work/ls/env_reinstall.sh
[ -s $L/tests_r9g.log ] && grep -q EXIT $L/tests_r9g.log || { (cd $R && timeout 1150 python3 -m pytest tests_ng -q -p no:cacheprovider > $L/tests_r9g.log 2>&1; echo "EXIT $?" >> $L/tests_r9g.log); }
[ -s /tmp/gen_jobs/loc_dev.jsonl ] || (cd $R/bench_gen && python3 gen_eval.py prep > $L/gen_prep_r9g.log 2>&1)
for st in cn chainzh t2r hmbzh; do grep -q "^EXIT" $L/$st.r9gdone 2>/dev/null && continue; bash $R/bench_rel/gate_rel.sh $st; cp $L/$st.log $L/$st.r9gdone; done
cd $R/bench_gen
for s in loc_dev lme_dev; do G1_FROZEN_CLOCK=1 GEN_DB_CACHE=/tmp/ls_cache/rel15 timeout 1150 python3 gen_eval.py run rel15 $s --root $R --np 1 >> $L/gen_rel15.log 2>&1; python3 gen_eval.py score rel15 $s >> $L/gen_rel15.log 2>&1; done
cd /workspace/work/ls/wt-gen/bench_gen
export G1_FROZEN_CLOCK=1 GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5
for s in lmelp_dev lmelps_dev; do python3 gen_eval.py run rel15emb $s --root $R --np 1 >> $L/gen_rel15emb.log 2>&1; done
echo GATE_R9G_DONE
