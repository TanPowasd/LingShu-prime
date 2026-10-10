#!/bin/bash
# 后台续跑 dsh-memory 两臂（主臂 + 附录 jaccard 臂），输出落工作区 runs/；run_loop.sh 自动 --resume。
cd /workspace/work/pes
(setsid nohup ./run_loop.sh plugins/dsh-memory/adapter.py:DshMemoryPlugin runs/B_dsh --seeds 1,2,3 >> logs/run_B_dsh.log 2>&1 < /dev/null &)
(setsid nohup ./run_loop.sh plugins/dsh-memory/adapter.py:DshMemoryJaccardPlugin runs/B_dsh_jaccard --seeds 1,2,3 >> logs/run_B_dsh_jaccard.log 2>&1 < /dev/null &)
