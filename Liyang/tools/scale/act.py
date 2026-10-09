"""激活冷/热耗时：python act.py <root> <db>"""
import sys,time
sys.path.insert(0,sys.argv[1])
from lingshu_ng.activation import ActivationEngine
ae=ActivationEngine(sys.argv[2],'/tmp/scale/audit.jsonl')
for w in ['服务器状态','数据库状态','备份状态','服务器状态']:
  t=time.perf_counter(); r=ae.activate(w,hops=2,workset='w'); print('act',w,round((time.perf_counter()-t)*1000,1),r['size'],r['top'][:2])
