"""一次写入后的激活（派生图增量重建）耗时：python act_rebuild.py <root> <db>"""
import sys,time,shutil
sys.path.insert(0,sys.argv[1])
shutil.copy(sys.argv[2],'/tmp/scale/rb.db')
from lingshu_ng.activation import ActivationEngine
from lingshu_ng.engine import MemoryEngine
e=MemoryEngine('/tmp/scale/rb.db'); ae=ActivationEngine('/tmp/scale/rb.db','/tmp/scale/audit.jsonl')
ae.activate('服务器状态',workset='w')
for i in range(3):
    e.perceive(f'新服务器状态{i}')
    t=time.perf_counter(); ae.activate('服务器状态',workset='w'); print('after-write act',round((time.perf_counter()-t)*1000,1))
