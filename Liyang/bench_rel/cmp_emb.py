import json,sys
# 发布树带模型运行（单配置）对研究树 sweep 某臂逐题名次比较；用法 cmp_emb.py rel.jsonl sweep.jsonl arm
def ld(p):
    d={}
    for l in open(p):
        try:o=json.loads(l)
        except: continue
        d[o['key']]=o
    return d
a=ld(sys.argv[1]);b=ld(sys.argv[2]);arm=sys.argv[3]
same=diff=0;top=0
for k in sorted(set(a)&set(b)):
    ra=a[k]['rank'];rb=b[k]['rank'][arm]
    ra=ra[next(iter(ra))] if isinstance(ra,dict) and len(ra)==1 and not isinstance(rb,dict) else ra
    if ra==rb: same+=1
    else:
        diff+=1
        x=ra if isinstance(ra,list) else json.dumps(ra); y=rb if isinstance(rb,list) else json.dumps(rb)
        if isinstance(ra,list) and isinstance(rb,list) and ra[:50]==rb[:50]: top+=1
print(f"common {same+diff} same {same} diff {diff} (diff but top50 same {top})")
