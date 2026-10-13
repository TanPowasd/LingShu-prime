#!/bin/bash
# stab-r3 #4 数据安全压测：同一组用例以大轮数重复（线程共享引擎 REPS 轮、多连接 / 多进程 REPS/3 轮、写入中途被杀 REPS 个不同时点）。
# 用法：tools/ci/stress_db.sh [REPS=30]（在仓根目录执行；只用当前 python 环境，不装包）
cd "$(dirname "$0")/../.." || exit 1
LINGSHU_NG_STRESS_REPS=${1:-30} ${PYTHON:-python3} -m pytest tests_ng/test_db_safety.py -q -p no:cacheprovider -p no:randomly "${@:2}"
