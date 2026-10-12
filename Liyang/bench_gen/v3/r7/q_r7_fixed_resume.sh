#!/bin/bash
# r7b：沙箱重启后续跑 hold 固定臂的对手 lmelps_hold（按 key 跳过已完成）
cd /workspace/work/ls/wt-gen/bench_gen
export G1_FROZEN_CLOCK=1
PYTHONHASHSEED=0 python3 v3/cf_holdjobs.py lmelps_hold 0 1 >> runs/cf_lmelps_hold.0.log 2>&1; echo "$(date +%T) cf lmelps_hold"
echo R7HOLDFIXDONE
