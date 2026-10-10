#!/usr/bin/env bash
# 后台续跑外壳：flock 保证全局只有一个实例；rc=3（作答未完/异常）→ 30 s 后续跑；rc=0 完成；rc=4 预算上限停。
#   setsid nohup plugins/dsh-auto-memory/run_loop_dam.sh validation/dam-20261010T1045 > validation/dam-20261010T1045/raw/_loop.log 2>&1 &
set -u
cd "$(dirname "$0")/../.."
VDIR="$1"
mkdir -p "$VDIR/raw"
exec 9>"$VDIR/raw/.loop.lock"
if ! flock -n 9; then echo "已有续跑外壳在运行（$VDIR/raw/.loop.lock），退出"; exit 9; fi
for i in $(seq 1 200); do
  echo "[loop] $(TZ=Asia/Shanghai date '+%F %T') 第 $i 轮"
  python3 plugins/dsh-auto-memory/run_pairs.py --vdir "$VDIR" --concurrency "${DAM_CONC:-4}"
  rc=$?
  echo "[loop] rc=$rc"
  if [ $rc -eq 0 ] || [ $rc -eq 4 ]; then
    if [ -f "$VDIR/raw/_status.json" ] && grep -q '"all_done": true' "$VDIR/raw/_status.json"; then exit 0; fi
    [ $rc -eq 4 ] && exit 4
  fi
  sleep 30
done
