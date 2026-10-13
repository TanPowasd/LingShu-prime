import ast,os,sys,subprocess,collections
root=sys.argv[1]
fs=[f for f in subprocess.run(['git','-C',root,'ls-files','md_cg/*.py'],capture_output=True,text=True).stdout.split() if f.count('/')==1 and not os.path.basename(f).startswith(('test_','bench_'))]
mods={os.path.basename(f)[:-3] for f in fs}
top=collections.defaultdict(set); lazy=collections.defaultdict(set)
for f in fs:
    m=os.path.basename(f)[:-3]; tree=ast.parse(open(os.path.join(root,f),encoding='utf-8').read())
    toplevel_nodes=set(id(s) for s in tree.body)
    # find imports & whether at module top (incl. inside top-level try/if)
    def walk(node,depth_fn):
        for ch in ast.iter_child_nodes(node):
            infn=depth_fn or isinstance(ch,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and not isinstance(ch,ast.ClassDef)
            if isinstance(ch,ast.ImportFrom):
                tg=[]
                if ch.level==1: tg=[ch.module.split('.')[0]] if ch.module else [a.name for a in ch.names]
                elif ch.module and ch.module.startswith('md_cg.'): tg=[ch.module.split('.')[1]]
                elif ch.module=='md_cg': tg=[a.name for a in ch.names]
                for t in tg:
                    if t in mods and t!=m: (lazy if depth_fn else top)[m].add(t)
            elif isinstance(ch,ast.Import):
                for a in ch.names:
                    if a.name.startswith('md_cg.'):
                        t=a.name.split('.')[1]
                        if t in mods and t!=m: (lazy if depth_fn else top)[m].add(t)
            walk(ch, depth_fn or isinstance(ch,(ast.FunctionDef,ast.AsyncFunctionDef)))
    walk(tree,False)
print('prod modules (md_cg top-level, excl test_/bench_):',len(mods))
print('top-level edges',sum(len(v) for v in top.values()),'lazy(in-function) edges',sum(len(v) for v in lazy.values()))
# SCC on top-level graph
import itertools
def scc(g,nodes):
    idx={};low={};st=[];on=set();res=[];c=[0]
    sys.setrecursionlimit(10000)
    def sc(v):
        idx[v]=low[v]=c[0];c[0]+=1;st.append(v);on.add(v)
        for w in g.get(v,()):
            if w not in idx: sc(w);low[v]=min(low[v],low[w])
            elif w in on: low[v]=min(low[v],idx[w])
        if low[v]==idx[v]:
            comp=[]
            while True:
                w=st.pop();on.discard(w);comp.append(w)
                if w==v:break
            res.append(comp)
    for v in nodes:
        if v not in idx: sc(v)
    return [r for r in res if len(r)>1]
print('SCC top-level:',scc(top,mods))
allg={m:top[m]|lazy[m] for m in mods}
s=scc(allg,mods); print('SCC incl lazy: count',len(s),'sizes',[len(x) for x in s]); 
for x in s: print(' ',sorted(x)[:60], '...' if len(x)>60 else '')
fanin=collections.Counter(t for v in allg.values() for t in v)
print('fan-in top15',fanin.most_common(15))
print('fan-out top15',sorted(((len(v),k) for k,v in allg.items()),reverse=True)[:15])
print('lazy imports by file top15',sorted(((len(v),k) for k,v in lazy.items()),reverse=True)[:15])
