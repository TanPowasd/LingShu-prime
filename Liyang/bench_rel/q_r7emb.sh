#!/bin/bash
# rel-v1 + r7「带模型」等价核对：用 wt-gen 的 gen_eval（含 GEN_EMBED）跑 --root wt-rel，rel 默认 cfg（不传 --cfg）
cd /workspace/work/ls/wt-gen/bench_gen
export G1_FROZEN_CLOCK=1 GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5 GEN_EMBED_CACHE=/tmp/ls_cache/vec
mkdir -p /tmp/ls_cache/vec; [ -s /tmp/ls_cache/vec/vec.db ] || cp /workspace/work/ls/_shared/models/_vec_cache/vec.db /tmp/ls_cache/vec/
for s in lmelp_dev lmelps_dev; do python3 gen_eval.py run relr7emb $s --root /workspace/work/ls/wt-rel --np 1; done
echo Q_R7EMB_DONE
