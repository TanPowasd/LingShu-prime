#!/bin/bash
# r9 H-CM9 判定（修订 10；冻结 F3 原样，只跑一次）：候选 / R7 / v3.2（无模型）/ TriCue v3 + 多维 启发，两口径；单打分进程顺序。
# 可重入：沙箱重启后再执行即按 key 断点续跑同一次运行（worker / cf_holdjobs 均跳过已完成 key）。
cd /workspace/work/ls/wt-gen/bench_gen
python3 -c "import onnxruntime, tokenizers" 2>/dev/null || bash /workspace/work/ls/env_reinstall.sh
[ -s /tmp/gen_jobs/lme_dev.jsonl ] || python3 gen_eval.py prep
if [ ! -s /tmp/gen_jobs/cm9_hold.jsonl ]; then
  python3 v3/mk_holdout_cm.py > /dev/null && python3 v3/mk_cm_r4.py > /dev/null && python3 v3/mk_cm_r5.py > /dev/null && python3 v3/r8/mk_cm_r8.py > /dev/null && python3 v3/r9/mk_cm_r9.py > /tmp/mk_cm_r9.log
fi
sha1sum /tmp/gen_jobs/cm9_hold.jsonl /tmp/gen_jobs/cm9s_hold.jsonl /tmp/gen_jobs/meta_cm9_hold.json
export G1_FROZEN_CLOCK=1
EMB=/workspace/work/ls/_shared/models/bge-small-en-v1.5
CFG='{"sf":1,"sf_w":2,"sf_k":10,"sf_n":60,"sf_adj":0,"sf_qp":2,"sf_mx":1,"sf_mxn":20}'
R7='{"sf":1,"sf_w":2,"sf_k":10,"sf_n":60,"sf_adj":0}'
for s in cm9_hold cm9s_hold; do
  GEN_EMBED=$EMB python3 gen_eval.py run r9_cand $s --np 1 --cfg "$CFG"; echo "$(date +%T) cand $s"
  GEN_EMBED=$EMB python3 gen_eval.py run r9_r7h $s --np 1 --cfg "$R7"; echo "$(date +%T) r7 $s"
  python3 gen_eval.py run r9_v32h $s --np 1; echo "$(date +%T) v32 $s"
  PYTHONHASHSEED=0 python3 v3/cf_holdjobs.py $s 0 1 > runs/cf_$s.0.log 2>&1; echo "$(date +%T) cf $s"
done
rm -rf out/r9_cand out/r9_r7h out/r9_v32h; rm -f out/cf_tricue_v3/cm9*_hold.json out/cf_md33/cm9*_hold.json
python3 v3/r9/r9_judge.py > v3/logs/r9_judge.log 2>&1
echo R9HOLD_DONE
