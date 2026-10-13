#!/bin/bash
# stab-r2 rel-v1.17 候选门（wt-rel = stab-v1@4d03dbfd 快进）：gate_rel t2r/hmbzh + gen 无模型 loc_dev/LME dev（tag rel117，对 rel116 逐题）。
# tests_ng / cn / chainzh / 链 h100,h50 / 误登记逐条 / 多版本 venv 已在同一代码的 wt-stab 上跑过（_stab/r2/q_r2.sh，读数见 CHANGELOG_rel-v1.17）。
R=/workspace/work/ls/wt-rel; L=$R/bench_rel/logs; O=/workspace/work/ls/_stab1c/r2
python3 -c "import onnxruntime, tokenizers" 2>/dev/null || bash /workspace/work/ls/env_reinstall.sh
[ -L /tmp/gen_jobs ] || bash /workspace/work/ls/wt-gen/bench_gen/v3/r10/build_jobs.sh
for st in t2r hmbzh; do grep -q "^EXIT" $L/$st.s17done 2>/dev/null && continue; bash $R/bench_rel/gate_rel.sh $st; cp $L/$st.log $L/$st.s17done; echo "$(date +%T) $st" >> $O/q17.log; done
cd $R/bench_gen
for s in loc_dev lme_dev; do grep -q "^DONE $s" $O/gen_rel117.log 2>/dev/null && continue; G1_FROZEN_CLOCK=1 GEN_DB_CACHE=/workspace/work/ls/_shared/ls_cache_rel117 timeout 1150 python3 gen_eval.py run rel117 $s --root $R --np 1 >> $O/gen_rel117.log 2>&1; python3 gen_eval.py score rel117 $s >> $O/gen_rel117.log 2>&1 && echo "DONE $s" >> $O/gen_rel117.log; echo "$(date +%T) gen $s" >> $O/q17.log; done
echo GATE_S17_DONE >> $O/q17.log
