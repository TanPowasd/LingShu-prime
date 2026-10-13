# 只读取证脚本：在 dsh-memory 检出根运行  python -X utf8 survey.py <仓根>
import ast, os, sys, subprocess, json, hashlib, collections, re
root=sys.argv[1]
files=subprocess.run(['git','-C',root,'ls-files','*.py'],capture_output=True,text=True).stdout.split()
def top(p): return p.split('/')[0] if '/' in p else '<root>'
def is_test(p):
    b=os.path.basename(p); return b.startswith('test_') or '/tests/' in p or p.startswith('test/') or p.startswith('tests/') or b.endswith('_test.py')
stats=collections.defaultdict(lambda: collections.Counter())
funcs=[]; broad=[]; glob=[]; dup=collections.defaultdict(list); imports=collections.Counter(); modlevel_mut=[]
imp_edges=collections.defaultdict(set)
for p in files:
    src=open(os.path.join(root,p),encoding='utf-8',errors='replace').read()
    t=top(p); kind='test' if is_test(p) else 'prod'
    stats[t][kind+'_files']+=1; stats[t][kind+'_loc']+=src.count('\n')
    try: tree=ast.parse(src)
    except SyntaxError as e:
        stats[t]['syntax_err']+=1; continue
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            L=(n.end_lineno or n.lineno)-n.lineno+1
            if kind=='prod': funcs.append((L,p,n.name))
            if kind=='prod' and L>=8:
                body=ast.dump(ast.Module(body=n.body,type_ignores=[]),annotate_fields=False)
                dup[hashlib.sha1(body.encode()).hexdigest()].append((p,n.name,L))
        if isinstance(n,ast.ExceptHandler) and kind=='prod':
            bt=n.type
            name=None
            if bt is None: name='bare'
            elif isinstance(bt,ast.Name) and bt.id in('Exception','BaseException'): name=bt.id
            elif isinstance(bt,ast.Tuple) and any(isinstance(e,ast.Name) and e.id in('Exception','BaseException') for e in bt.elts): name='tuple-Exception'
            if name:
                silent=all(isinstance(s,(ast.Pass,ast.Continue)) or (isinstance(s,ast.Return) and (s.value is None or isinstance(s.value,ast.Constant))) for s in n.body)
                broad.append((p,name,silent))
        if isinstance(n,ast.Global) and kind=='prod':
            glob.append((p,tuple(n.names)))
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            mods=[a.name for a in n.names] if isinstance(n,ast.Import) else ([n.module] if n.module else [])
            if isinstance(n,ast.ImportFrom) and n.level and n.level>0: mods=[t]  # relative => same pkg
            for m in mods:
                if not m: continue
                mt=m.split('.')[0]
                if mt in('md_cg','hive','swarm','compiler','scripts','test','tests','utf8_boot') and mt!=t:
                    imp_edges[(t,kind)].add(mt); imports[(t,kind,mt)]+=1
    # module-level mutable state
    if kind=='prod':
        for s in tree.body:
            if isinstance(s,(ast.Assign,ast.AnnAssign)):
                v=s.value
                if isinstance(v,(ast.Dict,ast.List,ast.Set)) or (isinstance(v,ast.Call) and isinstance(v.func,(ast.Name,ast.Attribute)) and getattr(v.func,'id',getattr(v.func,'attr',''))in('dict','list','set','OrderedDict','defaultdict','Lock','RLock','WeakValueDictionary','WeakKeyDictionary','deque')):
                    tg=s.targets[0] if isinstance(s,ast.Assign) else s.target
                    nm=getattr(tg,'id',None)
                    if nm and not nm.isupper(): modlevel_mut.append((p,nm))
out={}
out['stats']={k:dict(v) for k,v in sorted(stats.items())}
funcs.sort(reverse=True)
out['long_funcs_top40']=funcs[:40]
out['funcs_ge200']=sum(1 for f in funcs if f[0]>=200); out['funcs_ge100']=sum(1 for f in funcs if f[0]>=100); out['funcs_total_prod']=len(funcs)
c=collections.Counter((b[1],b[2]) for b in broad); out['broad_except']={f'{k[0]}|silent={k[1]}':v for k,v in c.items()}
pb=collections.Counter(b[0] for b in broad if b[2]); out['silent_broad_by_file_top25']=pb.most_common(25)
out['silent_broad_total']=sum(pb.values())
gc=collections.Counter(g[0] for g in glob); out['global_stmt_total']=len(glob); out['global_stmt_by_file_top20']=gc.most_common(20)
mc=collections.Counter(m[0] for m in modlevel_mut); out['modlevel_mutable_lowercase_total']=len(modlevel_mut); out['modlevel_mutable_top20']=mc.most_common(20)
dd=[v for v in dup.values() if len({x[0] for x in v})>1]
dd.sort(key=lambda v:-v[0][2]*len(v))
out['dup_func_groups_crossfile']=len(dd); out['dup_examples_top25']=[[f'{x[0]}::{x[1]}({x[2]}行)' for x in v] for v in dd[:25]]
out['cross_top_imports']={f'{k[0]}[{k[1]}]->{k[2]}':v for k,v in sorted(imports.items())}
print(json.dumps(out,ensure_ascii=False,indent=1))
