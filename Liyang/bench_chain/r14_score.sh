cd /workspace/work/ls/wt-chain/bench_chain
D=/workspace/work/ls/wt-chain/bench_chain/out/regr_r14_h7; R=/workspace/work/ls/chainrun
for c in h100 h50; do HO_DIR=$D timeout 1100 python3 heldout_eval.py score $c > $R/r14_score_$c.log 2>&1; done
echo ALLDONE
