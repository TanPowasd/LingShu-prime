# T2 excl：疑问回声块「同区段替换」（只在 top-10 内；保章覆盖的代理：用 ±R 写入序邻块顶替）
import proto4 as P4, zh_eval as Z, statistics, sys
R=Z.get('v5base_deep'); d=Z.data(); qs={q['qid']:q['q'] for q in d['hq']}
C=P4.corp('hmb')
def run(th, Rw, depth, ids):
    new={}
    for q,r in R['hmb']['rank'].items():
        Q=C.qterms(qs[q]); top=list(r[:10]); rest=list(r[10:depth])
        for k,i in enumerate(list(top)):
            if C.echo(i,Q)>=th:
                rep=[j for j in rest if abs(j-i)<=Rw and C.echo(j,Q)<th]
                if rep:
                    top[k]=rep[0]; rest.remove(rep[0])
        new[q]=top
    ph,_=Z.perq_hmb({'hmb':{'rank':new}})
    return {k: round(statistics.mean(ph[x][k] for x in ids if ph[x][k] is not None),4) for k in ('cid','quote','point','excl')}
ids=Z.SPLIT['dev']
for th in (0.3,0.5,0.7,0.9):
    for Rw in (1,2,3):
        for depth in (20,40):
            print(th,Rw,depth,run(th,Rw,depth,ids))
