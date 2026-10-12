#!/bin/bash
# rel-v1 + r7：tests_ng 与「带模型」等价核对（rel 默认 cfg vs gen 冻结候选 r7_it1@w2_k10_n60_a0，lmelp_dev 两口径）
R=/workspace/work/ls/wt-rel
( cd $R; timeout 3000 python3 -m pytest -q tests_ng -p no:cacheprovider > bench_rel/logs/tests_r7.log 2>&1; echo EXIT $? >> bench_rel/logs/tests_r7.log ) &
cd $R/bench_gen
export G1_FROZEN_CLOCK=1 GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5 GEN_EMBED_CACHE=/tmp/ls_cache/vec
mkdir -p /tmp/ls_cache/vec; [ -s /tmp/ls_cache/vec/vec.db ] || cp /workspace/work/ls/_shared/models/_vec_cache/vec.db /tmp/ls_cache/vec/
for s in lmelp_dev lmelps_dev; do python3 gen_eval.py run relr7emb $s --root $R --np 1; done
wait; echo Q_R7_DONE
