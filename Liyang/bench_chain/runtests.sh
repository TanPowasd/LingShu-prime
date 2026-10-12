#!/bin/bash
# 逐文件跑 tests_ng，结果追加到日志：runtests.sh <log> <files...>
log=$1; shift
for f in "$@"; do
  r=$(timeout 600 python3 -m pytest "$f" -q -p no:cacheprovider 2>&1 | tail -1)
  echo "$f :: $r" >> $log
done
