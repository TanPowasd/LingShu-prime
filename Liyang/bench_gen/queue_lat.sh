#!/bin/sh
cd "$(dirname "$0")"
while ! grep -q ALLDONE runs_resume.log 2>/dev/null; do sleep 20; done
python3 gen_eval.py snap 05003d3 >/dev/null; python3 gen_eval.py snap 875d838 >/dev/null
python3 lat_bench.py loc_dev 3 2 base=/tmp/ng-gen-875d838 v1=/tmp/ng-gen-05003d3
python3 lat_bench.py lme_dev 8 1 base=/tmp/ng-gen-875d838 v1=/tmp/ng-gen-05003d3
echo ALLDONE
