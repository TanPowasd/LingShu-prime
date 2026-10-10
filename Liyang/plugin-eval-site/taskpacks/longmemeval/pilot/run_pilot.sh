#!/usr/bin/env bash
# 考卷 C 小规模试跑（可重复执行＝续跑；逐题落盘，已判分的题跳过）。沙箱重启后重跑本脚本即可。
# 用法：bash taskpacks/longmemeval/pilot/run_pilot.sh [phase]   phase: main | extra | all（默认 all）
set -u
cd "$(dirname "$0")/../../.."
S=taskpacks/longmemeval/pilot/subset.json
O=taskpacks/longmemeval/pilot_runs
L=taskpacks/longmemeval/pilot/logs; mkdir -p "$L"
W=${PES_C_WORKERS:-3}
phase=${1:-all}
run() { python3 -m harness.examC "$@"; }
if [[ $phase == main || $phase == all ]]; then
  run anchors --subset $S --n 32 --out $O --workers 2 >>"$L/anchors.log" 2>&1 &
  for arm in null bm25 oracle; do
    run run --subset $S --arm $arm --rerun 1 --out $O --workers $W >>"$L/$arm.r1.log" 2>&1 &
  done
  wait
fi
if [[ $phase == extra || $phase == all ]]; then
  run run --subset $S --arm leakprobe --rerun 1 --out $O --workers $W >>"$L/leakprobe.r1.log" 2>&1 &
  for arm in null bm25 oracle; do   # 第 2 次重跑：前 32 个场景，用于估场景内重跑方差
    run run --subset $S --arm $arm --rerun 2 --limit 32 --out $O --workers 2 >>"$L/$arm.r2.log" 2>&1 &
  done
  wait
fi
echo "done $(date)" >>"$L/pilot.done"
