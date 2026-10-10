#!/bin/bash
# 考卷 A 断点续跑包装（同 run_loop.sh，模块换成 harness.examA）。作答未完成（rc=3）或异常时自动 --resume，最多 8 次。
# usage: tools/run_loop_A.sh <plugin> <out> [其它 harness.examA 参数...]
cd /workspace/work/pes
export PES_LLM_INTERVAL=${PES_LLM_INTERVAL:-1.75}   # 与另两个代理共享约 35 次/分（跨进程匀速闸 /tmp/pes-llm-slots/pace）
P=$1; O=$2; shift 2
for i in 1 2 3 4 5 6 7 8; do
  R=""; [ -f "$O/recording.jsonl" ] && R="--resume"
  python3 -m harness.examA --plugin "$P" --out "$O" $R "$@"
  rc=$?; { [ $rc -eq 0 ] || [ $rc -eq 2 ]; } && exit $rc
  sleep 30
done
exit 3
