#!/bin/sh
# 沙箱重启后一键续跑（每个 run 只补未完成的 job）。
cd "$(dirname "$0")"
python3 gen_eval.py prep >/dev/null
python3 gen_eval.py snap 05003d3 >/dev/null; python3 gen_eval.py snap 875d838 >/dev/null
python3 gen_eval.py run base lme_test --root /tmp/ng-gen-875d838 &
GEN_PATCH_DEFAULT='{"stem": false, "stop": false}' python3 gen_eval.py run abl_none lme_dev --np 1
wait
python3 gen_eval.py run v1-noctx loc_test --root /tmp/ng-gen-05003d3 --cfg '{"ctx_beta": 0}'
python3 gen_eval.py run v1-noctx lme_test --root /tmp/ng-gen-05003d3 --cfg '{"ctx_beta": 0}'
echo ALLDONE
