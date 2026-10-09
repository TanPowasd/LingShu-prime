"""ng 节点表的纯 SQL 写入代价（每行一事务）：比较索引/触发器/参数变体。python raw.py <db_with_rows>"""
import sqlite3,time,os,sys
src=sys.argv[1]
s=sqlite3.connect(src)
COLS="id, content, modality, spatial_coordinates, temporal_coordinate, condition_space, importance, confidence, layer, access_count, last_access, created_at, tags, semantic_coordinates, state_attributes, entity_id, dedup_key"
rows=s.execute(f"select {COLS} from nodes where layer='knowledge' limit 30000").fetchall()
ddl=[r[0] for r in s.execute("select sql from sqlite_master where sql is not null and type='table' and name not like 'sqlite_%'")]
ddl2=[(r[0],r[1]) for r in s.execute("select name,sql from sqlite_master where sql is not null and type in ('index','trigger')")]
def run(drop=(), wor=False, prag=(), hw=False):
    p='/tmp/scale/raw.db'
    for x in ['','-wal','-shm']:
        if os.path.exists(p+x): os.remove(p+x)
    c=sqlite3.connect(p,isolation_level=None)
    for q in prag: c.execute(q)
    c.execute('pragma journal_mode=WAL'); c.execute('pragma foreign_keys=ON')
    for d in ddl:
        if wor and d.startswith('CREATE TABLE index_dirty'): d=d+' WITHOUT ROWID'
        c.execute(d)
    for n,d in ddl2:
        if n in drop: continue
        if hw and n=='trg_nodes_ins':
            d=("CREATE TRIGGER trg_nodes_ins AFTER INSERT ON nodes WHEN NEW.rowid <= COALESCE((SELECT CAST(value AS INTEGER) FROM index_state WHERE key='hw'), 0) "
               "BEGIN INSERT OR IGNORE INTO index_dirty(node_id) VALUES (NEW.id); END")
        c.execute(d)
    if hw: c.execute("INSERT INTO index_state VALUES ('hw','0')")
    ins=f"INSERT INTO nodes ({COLS}) VALUES ({','.join('?'*17)})"
    t=time.perf_counter()
    for r in rows:
        c.execute('BEGIN IMMEDIATE'); c.execute(ins,r); c.execute('COMMIT')
    return round((time.perf_counter()-t)/len(rows)*1e6,1)
V=[("base",{}),("hw",dict(hw=True)),("hw-wor",dict(hw=True,wor=True)),("wor",dict(wor=True)),("wor-created",dict(wor=True,drop={'idx_nodes_created'})),
   ("ckpt10k",dict(prag=['pragma wal_autocheckpoint=10000'])),("ps2048",dict(prag=['pragma page_size=2048'])),
   ("nodirty",dict(drop={'trg_nodes_ins'})),("all-off",dict(drop={'idx_nodes_created','idx_nodes_temporal','idx_nodes_dedup','trg_nodes_ins','idx_nodes_layer'}))]
for rep in range(int(sys.argv[2]) if len(sys.argv)>2 else 2):
    print(' '.join(f"{k}={run(**kw)}" for k,kw in V), flush=True)
