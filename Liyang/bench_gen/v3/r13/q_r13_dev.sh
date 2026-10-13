#!/bin/bash
# r13 F4w dev 门补跑（修订 14 R14.3）：BASE vs w40 同库 sweep；单打分进程顺序；可重入（按 key 续跑）
cd /workspace/work/ls/wt-gen/bench_gen
python3 -c "import onnxruntime, tokenizers" 2>/dev/null || bash /workspace/work/ls/env_reinstall.sh
bash v3/r10/build_jobs.sh
EMB=/workspace/work/ls/_shared/models/bge-small-en-v1.5
export G1_FROZEN_CLOCK=1
for s in ${SETS:-lme_dev loc_dev lmelp_dev lmelps_dev}; do
  GEN_EMBED=$EMB python3 gen_eval.py run r13_dev $s --np 1 --sweep v3/r13/r13_sweep.json; echo "$(date +%T) r13dev $s"
done
echo R13DEV_DONE
