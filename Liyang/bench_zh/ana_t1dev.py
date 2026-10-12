import zh_eval as Z, collections
HR=Z.HR; d=Z.data(); ch=d['tc']; cards={c['qid']:c for c in d['tcards']}
V=Z.get('v3deep'); A=Z.get('AGM')
def take_set(order,B):
    got,used=[],0
    for i in order:
        L=len(ch[i]['n'])
        if used+L>B and used: break
        got.append(i); used+=L
    return got
for q in Z.SPLIT['dev']:
    c=cards[q]; ev=[e for e in c.get('supporting_evidence') or [] if e.get('weight')=='primary']
    if not ev: continue
    rv=V['hive']['rank'][q]; ra=A['hive']['rank'][q]
    sv=take_set(rv,8000); sa=take_set(ra,8000)
    print(q, c['question'][:40], 'nV',len(sv),'nA',len(sa))
    print('  chapters V', collections.Counter(ch[i]['cid'] for i in sv).most_common(6))
    print('  chapters A', collections.Counter(ch[i]['cid'] for i in sa).most_common(6))
    for e in ev:
        nq=HR.norm(e['quote']); loc=[i for i in range(len(ch)) if nq in ch[i]['n']]
        rkv=[rv.index(i) if i in rv else -1 for i in loc]; rka=[ra.index(i) for i in loc]
        print('   ', e['cid'], loc, 'rankV',rkv,'rankA',rka, e['quote'][:30])
