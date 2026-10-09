#!/bin/bash
# 后台分段驱动：循环调用 run_hard 直到无剩余作业（每段 ≤100s）。用法：drive.sh <run> [额外参数]
cd "$(dirname "$0")/.."
RUN=$1; shift
for i in $(seq 1 200); do
  out=$(python3 evalsuite_hard/run_hard.py --run "$RUN" --budget 100 "$@" 2>&1)
  echo "$out"
  echo "$out" | grep -q "剩余 0" && break
  echo "$out" | grep -q "本段完成 0" && sleep 2
done
echo DRIVE_END
