#!/bin/bash
# arm.sh <name> <queries> [ENV=VAL ...]  —— 在预算内跑 sys_worker（可续跑），完成后写 out/retr_<name>.json
name=$1; qf=$2; shift 2
export HMB_ROOT=/workspace/work/hive-memory-bench PYTHONHASHSEED=0 HMB_DB_DIR=/workspace/work/hmbx/db_$name
cd /workspace/work/liyang
env "$@" PYTHONPATH=/workspace/work/liyang python3 -c "
import os,tempfile
from lingshu_ng.engine import MemoryEngine as E
e=E(os.path.join(tempfile.mkdtemp(),'m.db'))
assert e.semantic_error is None and e.neural_error is None, (e.semantic_error, e.neural_error)
print('preflight sem',e.semantic is not None,'neural',e.retriever.neural is not None, getattr(getattr(e.retriever.neural,'cross',None),'model',None))" || exit 3
env "$@" PYTHONPATH=/workspace/work/liyang timeout ${BUDGET:-580} python3 -X utf8 evalsuite_hmb/sys_worker.py --impl ng --task ingest --corpus novel --queries /workspace/work/hmbx/$qf --out /workspace/work/hmbx/out/retr_$name.json
echo "rc=$? $(python3 -c "import json;d=json.load(open('$HMB_DB_DIR/progress.json'));print('done',d['done'],'q',len(d['q']))")"
