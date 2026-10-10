#!/bin/bash
# 后台续跑 EverOS 臂（runs/B_everos，89 卡 × 种子 1,2,3）。run_loop.sh 自动 --resume。
# 沙箱（venv/HOME）在 runs/sbx/（持久盘）；EverOS 记忆根与写入进度在 runs/B_everos/everos_state/（持久盘），续跑跳过已 flush 的批次。
# PES_EVEROS_PAR：最多几份语料并行写入（缺省 4；LLM 总速率仍受 harness/llm.py 匀速闸约束）。
cd /workspace/work/pes
export PES_SBX_ROOT=/workspace/work/pes/runs/sbx PES_EVEROS_PORT=${PES_EVEROS_PORT:-18780} PES_EVEROS_PAR=${PES_EVEROS_PAR:-4}
(setsid nohup ./run_loop.sh plugins/everos/adapter.py:EverOS runs/B_everos --seeds 1,2,3 >> logs/run_B_everos.log 2>&1 < /dev/null &)
