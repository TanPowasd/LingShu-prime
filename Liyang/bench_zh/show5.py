import json, sys
L=[json.loads(l) for l in open(sys.argv[1])]
keys=sys.argv[2].split(',')
def sc(r):
    h=r['t1h']; t=r['t1']
    # dev 目标：全证据+primary 各档，减误用
    return sum(h[B]['primary']+h[B]['full']-0.5*h[B]['excl'] for B in ('2000','4000','8000')) + 0.5*sum(t[B]['primary']+t[B]['full']-0.5*t[B]['excl'] for B in ('2000','4000','8000'))
L.sort(key=lambda r:-sc(r))
for r in L[:int(sys.argv[3]) if len(sys.argv)>3 else 20]:
    p=r['P']; h=r['t1h']; t=r['t1']
    print('%.3f'%sc(r), {x:p.get(x) for x in keys}, 'H '+' '.join('%s:%.3f/%.3f/%.3f'%(B[0],h[B]['primary'],h[B]['full'],h[B]['excl']) for B in ('2000','4000','8000')), '| T1 '+' '.join('%s:%.3f/%.3f/%.3f'%(B[0],t[B]['primary'],t[B]['full'],t[B]['excl']) for B in ('2000','4000','8000')))
