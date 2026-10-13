#!/bin/bash
# zh-v13 C1 级联：等延迟复测跑完 → DuRT dev 前 6 段 v2-m3 打分（缓存，可重入）→ 评估 k ∈ {2,3,4,6}
cd /workspace/work/ls/wt-zh/bench_zh
while pgrep -f "v13/lat.py run" > /dev/null || pgrep -f "q_lat_fix.sh" > /dev/null; do sleep 20; done
T2R_SET=durt python3 v13/casc.py score dev v11c 6
T2R_SET=durt python3 v13/casc.py eval dev v11c 2,3,4,6
echo CASC_DEV_DONE
