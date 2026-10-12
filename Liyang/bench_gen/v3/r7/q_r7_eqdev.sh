#!/bin/bash
# r7b：gen 树冻结 cfg 单配置（非 sweep）跑 lmelp dev 两口径，作 rel 带模型等价核对的参照（sweep 同库多配置会因 touch 互相影响名次尾部）
cd /workspace/work/ls/wt-gen/bench_gen
export G1_FROZEN_CLOCK=1 GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5 GEN_EMBED_CACHE=/tmp/ls_cache/vec
for s in lmelp_dev lmelps_dev; do python3 gen_eval.py run r7_candd $s --np 1 --cfg '{"sf":1,"sf_w":2,"sf_k":10,"sf_n":60,"sf_adj":0}'; done
echo EQDEV_DONE
