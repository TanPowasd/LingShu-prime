# chain-r21b h100/h50 回归（H7 已暴露改写集副本）。ngchain＝v21（本树缺省，chain-v1@6f698050）；ngchain_v8 槽位＝r19 的 v19 输出（regr_r19_h7/ranked_*_ngchain.json 原样复制，上次推送版 rel-v1.7）；ng、ngchain_v9 同 r19 原样复制。
cd /workspace/work/ls/wt-chain/bench_chain
D=/workspace/work/ls/wt-chain/bench_chain/out/regr_r21; R=/workspace/work/ls/chainrun
for c in h100 h50; do [ -s $R/r21_rank_${c}.ok ] && continue; HO_DIR=$D timeout 300 python3 heldout_eval.py rank $c ngchain > $R/r21_rank_${c}.log 2>&1 && echo ok > $R/r21_rank_${c}.ok; done
for c in h100 h50; do HO_DIR=$D timeout 1100 python3 heldout_eval.py score $c > $R/r21_score_$c.log 2>&1; done
echo ALLDONE > $R/r21_h100.done
