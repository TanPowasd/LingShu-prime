"""单条写入分解（20k 知识层 skip_dedup）：compat 门面 / engine.perceive / 纯 SQL 三层各自的每条耗时"""
import sys,os,time,random,tempfile
root=sys.argv[1]; n=int(sys.argv[2]) if len(sys.argv)>2 else 20000
sys.path.insert(0,root)
from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.engine import MemoryEngine
words = ["服务器", "数据库", "备份", "用户", "配置", "端口", "证书", "日志", "预算", "会议", "合同", "版本"]
def texts(seed):
    r=random.Random(seed); return [(f"{r.choice(words)}{r.choice(words)}记录{i}：{r.choice(words)}状态{i * 7919 % 100003}", round(r.random(),3)) for i in range(n)]
T=texts(1); d=tempfile.mkdtemp(dir='/tmp/scale')
e=SpacetimeMemoryEngine(os.path.join(d,'a.db')); t=time.perf_counter()
for c,imp in T: e.add_perception(c,importance=imp,skip_dedup=True)
a=(time.perf_counter()-t)/n*1e6
g=MemoryEngine(os.path.join(d,'b.db')); t=time.perf_counter()
for c,imp in T: g.perceive(c,importance=imp,skip_dedup=True)
b=(time.perf_counter()-t)/n*1e6
print(f"compat {a:.1f}us  engine {b:.1f}us  (门面开销 {a-b:.1f}us)")
