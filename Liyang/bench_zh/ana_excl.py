# T2 dev must_exclude 分析（只用 dev）
import zh_eval as Z
H=Z.H; d=Z.data(); hc=d['hc']; cards=d['hcards']
V=Z.get('v5base_deep'); A=Z.get('AGM')
nx=0
for q in Z.SPLIT['dev']:
    c=cards[q]; me=c.get('must_exclude') or []
    if not me: continue
    r=V['hmb']['rank'][q]; ra=A['hmb']['rank'][q]
    ev=H.card_evidence(c)
    for e in me:
        nq=H.norm(e['quote']); loc=[i for i in range(len(hc)) if nq in H.norm(hc[i]['text'])]
        rk=[r.index(i) if i in r else -1 for i in loc]; rka=[ra.index(i) if i in ra else -1 for i in loc]
        evloc=[i for i in loc if any(H.norm(x['quote']) in H.norm(hc[i]['text']) for x in ev)]
        print(q, 'excl', e['quote'][:30], 'loc',loc,'rankV',rk,'rankA',rka,'same_chunk_as_evidence',evloc, e.get('exclusion_type'))
    print('   Q:', c.get('question', c.get('q',''))[:60] if isinstance(c,dict) else '')
