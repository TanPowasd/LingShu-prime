#!/bin/bash
# 停 EverOS 全量臂（run_loop、harness、everos 服务、考场侧转发器）与外联采样器。断点在 runs/B_everos/everos_state/，之后可用 start_everos_arm.sh 续跑。
for pat in "run_loop.sh plugins/everos/adapter.py:EverOS runs/B_everos" "harness.run --plugin plugins/everos/adapter.py:EverOS --out runs/B_everos" \
           "everos server start --root /workspace/work/pes/runs/B_everos/" "llm_proxy.py --port 18781" "egress_watch.py"; do
  for pid in $(pgrep -f -- "$pat"); do [ "$pid" != "$$" ] && kill "$pid" 2>/dev/null && echo "killed $pid ($pat)"; done
done
