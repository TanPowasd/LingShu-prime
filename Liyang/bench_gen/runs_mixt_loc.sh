cd /workspace/work/ls/wt-gen/bench_gen
python3 gen_eval.py run mixt_v1 mix_loc_test --root /tmp/ng-gen-05003d3 --np 1 &
python3 gen_eval.py run mixt_v2 mix_loc_test --root /tmp/ng-gen-9ffe1e9 --np 1 &
wait; echo RUNDONE
