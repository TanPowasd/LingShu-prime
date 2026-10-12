#!/bin/sh
# 等 queue_v1 完成后跑 v1-noctx 消融臂（test 各一次）
cd "$(dirname "$0")"
while ! grep -q ALLDONE runs_queue_v1.log 2>/dev/null; do sleep 20; done
[ -d /tmp/gen_jobs ] || python3 gen_eval.py prep
python3 gen_eval.py snap 05003d3 >/dev/null
python3 gen_eval.py run v1-noctx loc_test --root /tmp/ng-gen-05003d3 --cfg '{"ctx_beta": 0}'
python3 gen_eval.py run v1-noctx lme_test --root /tmp/ng-gen-05003d3 --cfg '{"ctx_beta": 0}'
echo ALLDONE
