"""质量维对照：新增的 cc>10 函数、最长函数、重复窗口（只列本线改动的文件）。python qdiff.py <root_new> <root_old>"""
import sys,os,hashlib
from collections import defaultdict
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','evalsuite'))
import quality as Q
new,old=sys.argv[1],sys.argv[2]
a,b=Q.analyze(new,'ng'),Q.analyze(old,'ng')
for k in ('max_func','mean_func_len','cc_mean','cc_over_10','functions','dup_rate'):
    print(k, b[k], '->', a[k])
def funcs(root):
    import ast
    out={}
    base,files=Q.scope_files(root,'ng')
    for f in files:
        t=ast.parse(open(f,encoding='utf-8').read()); rel=os.path.relpath(f,root)
        for n in ast.walk(t):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                out[f"{rel}:{n.name}"]=(n.end_lineno-n.lineno+1,Q.cyclomatic(n))
    return out
fa,fb=funcs(new),funcs(old)
print('cc>10 new:', {k:v for k,v in fa.items() if v[1]>10 and (k not in fb or fb[k][1]<=10)})
print('len>40:', {k:v for k,v in fa.items() if v[0]>40})
base,files=Q.scope_files(new,'ng'); W=defaultdict(list)
for f in files:
    nl=Q._norm_lines(open(f,encoding='utf-8').read()); rel=os.path.relpath(f,new)
    for i in range(len(nl)-Q.WINDOW+1): W[hashlib.md5("\n".join(nl[i:i+Q.WINDOW]).encode()).hexdigest()].append((rel,i,nl[i]))
mine=('activation.py','dedup.py','causal.py','store/edges.py','store/textindex.py','engine.py','store/db.py','compat_engine_ops.py','store/schema.py')
seen=set()
for h,occ in W.items():
    if len(occ)>1 and any(o[0].endswith(mine) for o in occ):
        key=tuple(sorted(set((o[0],o[1]) for o in occ)))
        print('DUP', [(o[0],o[1]) for o in occ], occ[0][2][:60])
