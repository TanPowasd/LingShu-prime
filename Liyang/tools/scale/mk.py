"""建一个与 evalsuite/perf.py 同口径的 N 规模库（调试用）：python mk.py <root> <N> <out.db>"""
import sys,os,random
root=sys.argv[1]; n=int(sys.argv[2]); out=sys.argv[3]
sys.path.insert(0,root); sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','evalsuite'))
from adapters import Adapter
A=Adapter(os.environ.get('IMPL','ng')); rnd=random.Random(n)
words = ["服务器", "数据库", "备份", "用户", "配置", "端口", "证书", "日志", "预算", "会议", "合同", "版本"]
for s in ('','-wal','-shm'):
    if os.path.exists(out+s): os.remove(out+s)
m=A.open(out); ids=[]
for i in range(n):
    ids.append(m.add(f"{rnd.choice(words)}{rnd.choice(words)}记录{i}：{rnd.choice(words)}状态{i * 7919 % 100003}",importance=round(rnd.random(), 3), skip_dedup=True))
for i in range(n // 10):
    m.add(f"情境{i}：{rnd.choice(words)}", layer="context", importance=round(rnd.random(), 3))
for _ in range(n // 2):
    a, b = sorted(rnd.sample(range(n), 2)); m.add_edge(ids[a], ids[b], "causal", 0.6)
m.close()
