cd /workspace/work/ls/wt-gen/bench_gen
bash /workspace/work/ls/env_reinstall.sh
python3 gen_eval.py prep >/dev/null
for r in 05003d3 875d838 9ffe1e9; do python3 gen_eval.py snap $r >/dev/null; done
python3 mixq.py jobs lme_test
echo PREPDONE
python3 gen_eval.py run mixt_v1 mix_lme_test --root /tmp/ng-gen-05003d3 &
python3 gen_eval.py run mixt_v2 mix_lme_test --root /tmp/ng-gen-9ffe1e9 &
MIXQ_THREADS=4 python3 mixq.py make loc_test > runs_mixq_loc.log 2>&1 &
wait; echo RUNDONE
