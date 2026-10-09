"""自检冷/热耗时与分解：python sc.py <root> <db>"""
import sys,time,shutil
sys.path.insert(0,sys.argv[1])
shutil.copy(sys.argv[2],'/tmp/scale/sc.db')
from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng import causal
e=SpacetimeMemoryEngine('/tmp/scale/sc.db')
for i in range(4):
  t=time.perf_counter(); r=e.self_check(); print('self_check',round((time.perf_counter()-t)*1000,1))
st=e.ng.store
t=time.perf_counter(); a=st.edges.arcs(("causal","cyclic")); print('arcs',round((time.perf_counter()-t)*1000,1))
t=time.perf_counter(); causal.cyclic_from_arcs(a); print('scc',round((time.perf_counter()-t)*1000,1))
t=time.perf_counter(); e.store.get_stats(); print('stats',round((time.perf_counter()-t)*1000,1))
ng=e.ng
t=time.perf_counter(); ng.store.registry.list_blindspots("open"); ng.skills.count(); ng.self_store.persisted; print('misc',round((time.perf_counter()-t)*1000,1))
