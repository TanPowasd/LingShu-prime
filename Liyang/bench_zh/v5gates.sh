cd /workspace/work/ls/wt-zh
cd /workspace/work/ls/wt-zh/bench_zh && timeout 900 python3 gate_chain.py /workspace/work/ls/wt-zh v5c ZH_DET=1 > runs/gate_chain_v5.log 2>&1; echo rc=$? >> runs/gate_chain_v4.log
cd /workspace/work/ls/wt-zh/bench_gen
for s in loc_dev lme_dev; do timeout 1500 python3 gen_eval.py run zhv5 $s --root /workspace/work/ls/wt-zh --np 2 > ../bench_zh/runs/engate_v5_$s.log 2>&1; python3 gen_eval.py score zhv5 $s >> ../bench_zh/runs/engate_v5_$s.log 2>&1; done
echo ALLDONE > /tmp/v5gates.done
