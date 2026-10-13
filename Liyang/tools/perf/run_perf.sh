#!/bin/bash
# stab-r5 规模与资源基准：1k / 10k / 100k × 无模型 / v7.1。串行（一次只一个重进程），已完成的跳过，可续跑。
# 用法：OUT=<读数目录> DBDIR=/tmp/perf [PERF_PKG_ROOT=<含 lingshu_ng 的目录，缺省本仓>] bash tools/perf/run_perf.sh [规模列表] [档位列表]
# 真实语料（可选）：PERF_ZH_TSV（T2Ranking collection.tsv）、PERF_ZH_Q（queries.train.tsv）、PERF_EN_DIR（ConvoMem 目录）；缺则用合成语料。
# v7.1 档需模型件：LINGSHU_NG_SEM=<模型根目录>（或 ~/.cache/lingshu_ng/models 存在）。
set -u
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../.." && pwd)
OUT=${OUT:-$ROOT/_out/perf}; DBDIR=${DBDIR:-/tmp/perf}; mkdir -p "$OUT" "$DBDIR"
SIZES=${1:-"1000 10000 100000"}; TIERS=${2:-"nomodel v71"}
PKG=${PERF_PKG_ROOT:-$ROOT}; export PERF_PKG_ROOT=$PKG PYTHONPATH=$PKG PYTHONDONTWRITEBYTECODE=1 LINGSHU_NG_SEM_CACHE=
for tier in $TIERS; do for n in $SIZES; do
  o=$OUT/perf_${tier}_${n}.json; [ -s "$o" ] && continue
  case $tier in
    nomodel) envs=(LINGSHU_NG_SEM=off) ;;
    v71) envs=(LINGSHU_NG_ASSOC='{"sem_dense":0}') ;;
    v11c) envs=() ;;
  esac
  echo "$(date +%T) start $tier $n" >> "$OUT/run.log"
  env "${envs[@]}" python3 "$HERE/perf_bench.py" --n "$n" --tier "$tier" --db "$DBDIR/perf_${tier}_${n}.db" --out "$o" >> "$OUT/run.log" 2>&1
  echo "$(date +%T) end $tier $n rc=$?" >> "$OUT/run.log"
  rm -f "$DBDIR/perf_${tier}_${n}.db"*
done; done
echo PERF_DONE >> "$OUT/run.log"
