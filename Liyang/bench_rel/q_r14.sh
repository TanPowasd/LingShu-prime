#!/bin/bash
# chain-r14 合入后 rel-v1.2 候选回归门：tests_ng + gate_rel 六段（串行）
R=/workspace/work/ls/wt-rel; L=$R/bench_rel/logs; export LINGSHU_LLM_CACHE=/workspace/work/ls/_shared/llm_cache
(cd $R && timeout 1150 python3 -m pytest tests_ng -q -p no:cacheprovider > $L/tests_r14.log 2>&1; echo "EXIT $?" >> $L/tests_r14.log)
(cd $R/bench_gen && python3 gen_eval.py prep > $L/gen_prep_r14.log 2>&1)
for st in cn chainzh t2r hmbzh gen_loc_dev gen_lme_dev; do bash $R/bench_rel/gate_rel.sh $st; done; echo GATE_ALL_DONE
