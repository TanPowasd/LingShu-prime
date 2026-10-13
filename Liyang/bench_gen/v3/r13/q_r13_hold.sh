#!/bin/bash
# r13 H-CM11 判定（修订 14 R14.4）：F4w(w40) + BASE 同库 sweep，v3.2 单跑；两口径；只跑一次；可重入（按 key 续跑）。
# 前置：R14.3 dev 门已全部读出且无显著负（脚本检查 out/r13_devgate.ok）。
cd /workspace/work/ls/wt-gen/bench_gen
[ -f out/r13_devgate.ok ] || { echo "dev 门未过/未跑，拒绝运行"; exit 1; }
python3 -c "import onnxruntime, tokenizers" 2>/dev/null || bash /workspace/work/ls/env_reinstall.sh
bash v3/r10/build_jobs.sh
[ -s /tmp/gen_jobs/cm11_hold.jsonl ] || { python3 v3/r11/mk_cm_r11.py > /dev/null && python3 v3/r11/cap_cm11.py > /dev/null; }
sha1sum /tmp/gen_jobs/cm11_hold.jsonl /tmp/gen_jobs/cm11s_hold.jsonl /tmp/gen_jobs/meta_cm11_hold.json
export G1_FROZEN_CLOCK=1
EMB=/workspace/work/ls/_shared/models/bge-small-en-v1.5
for s in cm11_hold cm11s_hold; do
  GEN_EMBED=$EMB python3 gen_eval.py run r13_hold $s --np 1 --sweep v3/r13/r13_hold_sweep.json; echo "$(date +%T) model-arms $s"
  python3 gen_eval.py run r13_v32h $s --np 1; echo "$(date +%T) v32 $s"
done
python3 v3/r13/r13_judge.py w40 > v3/logs/r13_judge.log 2>&1
echo R13HOLD_DONE
