"""分段计时灌库：python build.py <root> <N>（IMPL=legacy 测旧实现）"""
import sys,os,time,random
root=sys.argv[1]; n=int(sys.argv[2])
sys.path.insert(0,root); sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','evalsuite'))
from adapters import Adapter
A=Adapter(os.environ.get("IMPL","ng")); rnd=random.Random(n)
words = ["服务器", "数据库", "备份", "用户", "配置", "端口", "证书", "日志", "预算", "会议", "合同", "版本"]
c0=time.process_time(); t0=time.perf_counter(); m=A.open(A.tmpdb('b')); ids=[]
for i in range(n):
    ids.append(m.add(f"{rnd.choice(words)}{rnd.choice(words)}记录{i}：{rnd.choice(words)}状态{i * 7919 % 100003}",importance=round(rnd.random(), 3), skip_dedup=True))
t1=time.perf_counter(); c1=time.process_time()
for i in range(n // 10):
    m.add(f"情境{i}：{rnd.choice(words)}", layer="context", importance=round(rnd.random(), 3))
t2=time.perf_counter()
for _ in range(n // 2):
    a, b = sorted(rnd.sample(range(n), 2)); m.add_edge(ids[a], ids[b], "causal", 0.6)
t3=time.perf_counter(); c3=time.process_time()
print(f"{os.environ.get('IMPL','ng'):7s} {root[-30:]:30s} nodes {t1-t0:.2f} ctx {t2-t1:.2f} edges {t3-t2:.2f} total {t3-t0:.2f} | cpu nodes {c1-c0:.2f} total {c3-c0:.2f}")
