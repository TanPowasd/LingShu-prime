import sys,os,json,hashlib
sys.path.insert(0,'/workspace/work/pes'); sys.path.insert(0,'/workspace/work/pes/plugins/dsh-memory')
from adapter import DshMemory
from harness.recorder import Recorder
from tools.gates import state_check
p=DshMemory(base="/tmp/gates-dshm-state")
p._bind_sandbox()
# re-point fields as install would (base layout)
r=Recorder("/tmp/gates-recallmut.jsonl","rm",resume=os.path.exists("/tmp/gates-recallmut.jsonl"))
roots={"MDCG_ROOT":p.root}
before=state_check.scan(roots)
p._start(r)
for q in ["我的猫叫什么名字","住在哪里"]: p.recall(q,5,r)
p.mcp.close()
after=state_check.scan(roots)
ch=[k for k in set(before)|set(after) if before.get(k)!=after.get(k)]
print(json.dumps({"changed_after_2_recalls":sorted(ch)},ensure_ascii=False))
