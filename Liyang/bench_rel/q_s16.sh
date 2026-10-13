#!/bin/bash
# stab-r1b 合入 stab-v1 后 rel-v1.16 候选回归门（串行、断点续跑；持平门：对 rel-v1.15 = gen-r13b q_g13 输出逐项/逐题）
# tests_ng + gate_rel 四段（对 *.g13done）+ gen loc_dev/LME dev 无模型 tag rel116（对 rel115 逐题）
# + 带模型 lmelp/lmelps_dev tag rel116emb（对 rel115emb 逐题）+ 链 h100/h50 ngchain（对 regr_r27 = rel-v1.14/1.15 链输出）
R=/workspace/work/ls/wt-rel; L=$R/bench_rel/logs; export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
python3 -c "import onnxruntime, tokenizers" 2>/dev/null || bash /workspace/work/ls/env_reinstall.sh
[ -L /tmp/gen_jobs ] || bash /workspace/work/ls/wt-gen/bench_gen/v3/r10/build_jobs.sh
[ -s $L/tests_s16.log ] && grep -q EXIT $L/tests_s16.log || { (cd $R && PYTHONDONTWRITEBYTECODE=1 timeout 1150 python3 -m pytest tests_ng -q -p no:cacheprovider > $L/tests_s16.log 2>&1; echo "EXIT $?" >> $L/tests_s16.log); }
echo "$(date +%T) tests" >> $L/q_s16.log
for st in cn chainzh t2r hmbzh; do grep -q "^EXIT" $L/$st.s16done 2>/dev/null && continue; bash $R/bench_rel/gate_rel.sh $st; cp $L/$st.log $L/$st.s16done; echo "$(date +%T) $st" >> $L/q_s16.log; done
cd $R/bench_gen
for s in loc_dev lme_dev; do grep -q "^DONE $s" $L/gen_rel116.log 2>/dev/null && continue; G1_FROZEN_CLOCK=1 GEN_DB_CACHE=/workspace/work/ls/_shared/ls_cache_rel116 timeout 1150 python3 gen_eval.py run rel116 $s --root $R --np 1 >> $L/gen_rel116.log 2>&1; python3 gen_eval.py score rel116 $s >> $L/gen_rel116.log 2>&1 && echo "DONE $s" >> $L/gen_rel116.log; echo "$(date +%T) gen $s" >> $L/q_s16.log; done
cd /workspace/work/ls/wt-gen/bench_gen
for s in lmelp_dev lmelps_dev; do grep -q "^DONE $s" $L/gen_rel116emb.log 2>/dev/null && continue; G1_FROZEN_CLOCK=1 GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5 python3 gen_eval.py run rel116emb $s --root $R --np 1 >> $L/gen_rel116emb.log 2>&1 && echo "DONE $s" >> $L/gen_rel116emb.log; echo "$(date +%T) emb $s" >> $L/q_s16.log; done
D=$R/bench_chain/out/regr_s16; mkdir -p $D; cp -n /workspace/work/ls/wt-chain/bench_chain/out/regr_r27/rewrite_map.json $D/
cd $R/bench_chain
for c in h100 h50; do [ -s $D/rank_${c}.ok ] && continue; HO_DIR=$D timeout 600 python3 heldout_eval.py rank $c ngchain > $D/rank_${c}.log 2>&1 && echo ok > $D/rank_${c}.ok; echo "$(date +%T) chain $c" >> $L/q_s16.log; done
echo GATE_S16_DONE >> $L/q_s16.log
