"""激活派生图的 Python 堆：常驻与峰值（tracemalloc）。python mem.py <root> <db>"""
import sys,tracemalloc,shutil
sys.path.insert(0,sys.argv[1])
from lingshu_ng.activation import ActivationEngine
ae=ActivationEngine(sys.argv[2],'/tmp/scale/audit.jsonl')
tracemalloc.start()
ae.activate('服务器状态',workset='w'); cur,peak=tracemalloc.get_traced_memory()
print(f"after first activate: resident {cur/2**20:.1f} MB peak {peak/2**20:.1f} MB")
tracemalloc.reset_peak()
ae._view.fp=(-1,-1); ae.activate('服务器状态',workset='w'); cur,peak=tracemalloc.get_traced_memory()
print(f"after forced reload: resident {cur/2**20:.1f} MB peak {peak/2**20:.1f} MB")
