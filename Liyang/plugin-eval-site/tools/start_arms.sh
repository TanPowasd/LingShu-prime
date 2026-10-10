#!/bin/bash
# 后台启动底子臂/参照臂全量（输出落工作区 runs/，/tmp 会随沙箱重启清空）
cd /workspace/work/pes
for a in "$@"; do (setsid nohup ./run_loop.sh $a runs/B_$a --seeds 1,2,3 >> logs/run_B_$a.log 2>&1 < /dev/null &); done
