#!/bin/bash
# 用法：hmb_cross.sh <code_rev> <db_rev> <reps> [path]——复制库后在 code_rev 代码下计时检索
set -e
c=$1; d=$2; cp /tmp/scale/hmb_$d.db /tmp/scale/q_${c}_${d}.db
PYTHONHASHSEED=0 python -X utf8 "$(dirname "$0")/hmb_e2e.py" query /tmp/scale/snap_$c /tmp/scale/q_${c}_${d}.db $3 ${4:-search}
rm -f /tmp/scale/q_${c}_${d}.db*
