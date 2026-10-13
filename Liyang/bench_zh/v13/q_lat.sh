#!/bin/bash
# zh-v13 延迟验收（修订 11.1），可重入
cd /workspace/work/ls/wt-zh/bench_zh
W=/workspace/work/ls/wt-zh
python3 v13/lat.py run base dev 6 "v4=$W|LINGSHU_NG_SEM=off" 'v71='$W'|LINGSHU_NG_ASSOC={"sem_dense":0}' "v11c=$W"
echo LAT_DONE
