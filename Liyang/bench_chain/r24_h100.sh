# chain-r24 h100/h50 回归（H7 已暴露改写集副本）。ngchain＝v24（本树缺省）；ngchain_v8 槽位＝r21 的 v21 输出（regr_r21/ranked_*_ngchain.json 原样复制，上次 chain 推送版 rel-v1.9）；ng、ngchain_v9 同 r21 原样复制。
cd /workspace/work/ls/wt-chain/bench_chain
D=/workspace/work/ls/wt-chain/bench_chain/out/regr_r24; R=/workspace/work/ls/chainrun
for c in h100 h50; do [ -s $R/r24_rank_${c}.ok ] && continue; HO_DIR=$D timeout 300 python3 heldout_eval.py rank $c ngchain > $R/r24_rank_${c}.log 2>&1 && echo ok > $R/r24_rank_${c}.ok; done
for c in h100 h50; do HO_DIR=$D timeout 1100 python3 heldout_eval.py score $c > $R/r24_score_$c.log 2>&1; done
echo ALLDONE > $R/r24_h100.done
