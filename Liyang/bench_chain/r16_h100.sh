# chain-r16 h100/h50 回归（H7 已暴露改写集副本）。ngchain＝v16（本树）；ngchain_v8 槽位＝r15 的 v15 输出（regr_r16_h7/ranked_*_ngchain.json 原样复制）；ng、ngchain_v9 同 r15 原样复制。
cd /workspace/work/ls/wt-chain/bench_chain
D=/workspace/work/ls/wt-chain/bench_chain/out/regr_r16_h7; R=/workspace/work/ls/chainrun
for c in h100 h50; do HO_DIR=$D timeout 300 python3 heldout_eval.py rank $c ngchain > $R/r16_rank_${c}.log 2>&1; done
for c in h100 h50; do HO_DIR=$D timeout 1100 python3 heldout_eval.py score $c > $R/r16_score_$c.log 2>&1; done
echo ALLDONE
