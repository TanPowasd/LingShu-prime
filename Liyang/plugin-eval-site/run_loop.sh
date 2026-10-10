#!/bin/bash
# 断点续跑包装：作答未完成（退出码 3）时自动 --resume 重来，最多 6 次。
# usage: ./run_loop.sh <plugin> <out> [其它 harness.run 参数...]
P=$1; O=$2; shift 2
for i in 1 2 3 4 5 6; do
  R=""; [ -f "$O/recording.jsonl" ] && R="--resume"
  python3 -m harness.run --plugin "$P" --out "$O" $R "$@"
  rc=$?; { [ $rc -eq 0 ] || [ $rc -eq 2 ]; } && exit $rc
  sleep 30
done
exit 3
