import itertools, json, sys, time
import proto4 as P, zh_eval as Z
d = Z.data(); qs = {c['qid']: c['question'] for c in d['tcards']}
R1 = Z.get('v3deep'); RH = Z.get_t1h('v3deep_dev'); ids1 = Z.SPLIT['dev']
out = open(sys.argv[1], 'w')
G = dict(head=[10, 15], S=[5, 10, 20], w=[1, 2, 3], decay=[0.5], beta=[0, 0.3, 0.6, 1.0], gamma=[0, 0.5, 1.0], delta=[0, 0.05, 0.1], R=[6])
for vals in itertools.product(*G.values()):
    p = dict(P.DEF); p.update(dict(zip(G, vals)))
    if p['beta'] == 0 and (p['S'] != 10 or p['w'] != 2):
        continue
    m1 = P.eval_t1(R1, p, ids1, src_q=qs)[0]; mh = P.eval_t1h(RH, p)[0]
    out.write(json.dumps({'P': p, 't1': {B: m1[B] for B in m1}, 't1h': {B: mh[B] for B in mh}}) + '\n'); out.flush()
