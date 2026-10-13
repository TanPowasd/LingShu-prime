# -*- coding: utf-8 -*-
"""生成「上游旧引擎写出的库」夹具（stab-r3 #4）：PYTHONPATH=<上游仓根> python tools/ci/make_upstream_db.py <out.sqlite> <ids.json>"""
import os,sys,json,sqlite3
out=sys.argv[1]
if os.path.exists(out): os.remove(out)
from lingshu.core.core import SpacetimeMemoryEngine
e=SpacetimeMemoryEngine(out)
ids=[]
for i in range(12):
    n=e.add_perception(f"上游旧引擎条目{i}：库房盘点第{i}批，经手人赵{i%4}")
    ids.append(n if isinstance(n,str) else getattr(n,'id',None))
try: e.store.conn.commit()
except Exception as x: print("commit",x)
try: e.close()
except Exception as x: print("close", x)
c=sqlite3.connect(out); c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); c.execute("PRAGMA journal_mode=DELETE"); c.execute("VACUUM")
print(c.execute("select count(*) from nodes").fetchone(), [r[1] for r in c.execute("pragma table_info(nodes)")][-6:]); c.close()
json.dump({"ids":ids},open(sys.argv[2],"w"))
