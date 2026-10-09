"""冷自检（新进程首调）中位数：python sc_cold.py <root> <db> [reps]"""
import sys,subprocess,statistics,shutil
root,db=sys.argv[1],sys.argv[2]; reps=int(sys.argv[3]) if len(sys.argv)>3 else 5
code=f"""
import sys,time,shutil; sys.path.insert(0,{root!r}); shutil.copy({db!r},'/tmp/scale/scc.db')
from lingshu_ng.compat import SpacetimeMemoryEngine
e=SpacetimeMemoryEngine('/tmp/scale/scc.db'); e.add_perception('x',skip_dedup=True)
t=time.perf_counter(); e.self_check(); print((time.perf_counter()-t)*1000)
"""
v=[float(subprocess.run([sys.executable,'-c',code],capture_output=True,text=True).stdout) for _ in range(reps)]
print(root[-25:], 'cold self_check median', round(statistics.median(v),1), [round(x,1) for x in v])
