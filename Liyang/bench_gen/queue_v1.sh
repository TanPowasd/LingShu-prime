#!/bin/sh
# v1 test 单次运行 + 基线 test 重跑 + s4 dev 扫描（断点续跑：重复执行只补未完成的 job）
cd "$(dirname "$0")"
[ -d /tmp/gen_jobs ] || python3 gen_eval.py prep
python3 gen_eval.py snap 05003d3 >/dev/null; python3 gen_eval.py snap 875d838 >/dev/null
python3 gen_eval.py run v1 loc_test --root /tmp/ng-gen-05003d3
python3 gen_eval.py run v1 lme_test --root /tmp/ng-gen-05003d3
python3 gen_eval.py run base loc_test --root /tmp/ng-gen-875d838
python3 gen_eval.py run s4 loc_dev --sweep sweeps/s4.json
python3 gen_eval.py run s4 lme_dev --sweep sweeps/s4.json
python3 gen_eval.py run base lme_test --root /tmp/ng-gen-875d838
echo ALLDONE
