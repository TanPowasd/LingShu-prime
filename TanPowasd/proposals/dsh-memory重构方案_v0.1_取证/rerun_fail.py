import subprocess,sys,os,re,json
R=sys.argv[1] if len(sys.argv)>1 else '.'
log=open('baseline_run_jobs1.log',encoding='utf-8').read()
fails=re.findall(r'^失败：(.*)$',log,re.M)[-1].split(', ')
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
out={}
for n in fails:
    if n.startswith('scripts.'): argv=[sys.executable,'-X','utf8','scripts/'+n.split('.',1)[1]+'.py']
    elif n.startswith('test.'): argv=[sys.executable,'-X','utf8','test/'+n.split('.',1)[1].replace('.','/')+'.py']
    else: argv=[sys.executable,'-X','utf8','-m',n]
    try:
        p=subprocess.run(argv,cwd=R,env=env,capture_output=True,text=True,timeout=300)
        txt=(p.stdout+p.stderr); rc=p.returncode
    except subprocess.TimeoutExpired: txt='TIMEOUT';rc='T'
    lines=[l for l in txt.splitlines() if re.search(r'FAIL|Error|错误|cargo|rust|二进制|binary|not found|No such|Traceback|assert|✗',l,re.I)]
    out[n]={'rc':rc,'hits':lines[:12],'tail':txt.splitlines()[-6:]}
    print(n,rc,flush=True)
json.dump(out,open('rerun_fail.json','w'),ensure_ascii=False,indent=1)
