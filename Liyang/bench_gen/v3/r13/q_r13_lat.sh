#!/bin/bash
# r13 延迟（修订 14 R14.4）：r10 lat_model 同协议缩量——cm8_dev 前 20 job × 1 轮，三臂 R7（旧树 snap_985b69d）/ BASE（F4 sp_n 20）/ CAND（F4w sp_n 40）；可重入
cd /workspace/work/ls/wt-gen/bench_gen
SNAP=/workspace/work/ls/_shared/gen_tmp/snap_985b69d
R7='{"sf":1,"sf_w":2,"sf_k":10,"sf_n":60,"sf_adj":0}'
BASE='{"sf":1,"sf_w":2,"sf_k":10,"sf_n":60,"sf_adj":0,"sf_qp":2,"sf_mx":1,"sf_mxn":20,"sp":0.5,"sp_n":20,"sp_win":2}'
CAND='{"sf":1,"sf_w":2,"sf_k":10,"sf_n":60,"sf_adj":0,"sf_qp":2,"sf_mx":1,"sf_mxn":20,"sp":0.5,"sp_n":40,"sp_win":2}'
python3 v3/r10/lat_model.py r13 1 cm8_dev:20 "R7=$R7|PYTHONPATH=$SNAP" "BASE=$BASE" "CAND=$CAND"
echo LAT_DONE
