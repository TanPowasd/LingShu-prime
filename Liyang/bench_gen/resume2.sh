#!/bin/sh
# 沙箱重启后续跑（接替会话）：环境、job、快照，然后续跑 mixv2 扫描与 J2 判分
cd "$(dirname "$0")"
bash /workspace/work/ls/env_reinstall.sh
python3 gen_eval.py prep >/dev/null
python3 gen_eval.py snap 05003d3 >/dev/null; python3 gen_eval.py snap 875d838 >/dev/null
python3 mixq.py jobs lme_dev; python3 mixq.py jobs loc_dev
echo PREPDONE
