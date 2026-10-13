#!/bin/bash
# zh-v13 F1 预取复测（修订 11.1）：v7.1 对 v11c+预取，同协议轮换；等 base 跑完再开，可重入
cd /workspace/work/ls/wt-zh/bench_zh
W=/workspace/work/ls/wt-zh
while pgrep -f "v13/lat.py run base" > /dev/null; do sleep 20; done
python3 v13/lat.py run fix dev 6 'v71='$W'|LINGSHU_NG_ASSOC={"sem_dense":0}' "v11cpf=$W|_PREFETCH=1"
echo LAT_FIX_DONE
