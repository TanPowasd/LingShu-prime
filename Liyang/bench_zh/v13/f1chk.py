# F1 名次核对：有无 prefetch 返回列表逐位相同（rank 全等；score 全等另报）
import json,sys,os
pairs=[("durt","v11c_dev","v11cpf_dev"),("durt","v11c_hold2","v11cpf_hold2"),("t2r2","v11cnp_r1dev","v11cpf_r1dev"),("t2r2","v11cnp_r2dev","v11cpf_r2dev")]
out={}
for s,a,b in pairs:
    fa,fb=f"runs/{s}/{a}.json",f"runs/{s}/{b}.json"
    if not (os.path.exists(fa) and os.path.exists(fb)): print(s,a,b,"缺"); continue
    A=json.load(open(fa));B=json.load(open(fb))
    rd=[q for q in A["rank"] if A["rank"][q]!=B["rank"].get(q)]
    sd=[q for q in A["score"] if A["score"][q]!=B["score"].get(q)]
    miss=set(A["rank"])^set(B["rank"])
    print(f"{s} {a} vs {b}: 题 {len(A['rank'])} 名次不同 {len(rd)} 分数不同 {len(sd)} 题集差 {len(miss)}")
    out[f"{s}:{a}:{b}"]={"n":len(A["rank"]),"rank_diff":rd,"score_diff":sd,"qset_diff":sorted(miss)}
json.dump(out,open("runs/durt/v13/f1chk.json","w"),ensure_ascii=False,indent=1)
