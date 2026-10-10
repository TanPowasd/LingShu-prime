#!/bin/bash
# 考卷 A 三臂后台续跑（沙箱重启后重新执行本脚本即可；结果落 runs/A_*，--resume 自动接上）。
cd /workspace/work/pes; mkdir -p logs
for spec in "plugins/dsh-memory/adapter.py:DshMemoryPlugin runs/A_dsh" "bm25 runs/A_bm25" "null runs/A_null"; do
  set -- $spec
  n=$(basename $2)
  pgrep -f "run_loop_A.sh $1 $2" >/dev/null && { echo "$n 已在跑（run_loop 在）"; continue; }
  (setsid nohup tools/run_loop_A.sh $1 $2 --seeds 1,2,3 >> logs/run_$n.log 2>&1 < /dev/null &)
  echo "$n 已启动"
done
