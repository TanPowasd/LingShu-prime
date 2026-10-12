import itertools, json, sys, proto5 as P, zh_eval as Z
RH=Z.get_t1h('v5base_deep_all'); R=Z.get('v5base_deep')
G=dict(hd_n=[10,15], hd_S=[1,2,3,5], hd_w=[1,2], hd_beta=[0.3,0.5,0.8,1.2], hd_gate=[0,0.05,0.15], hd_decay=[0.5])
out=open(sys.argv[1],'w')
for vals in itertools.product(*G.values()):
    p=dict(P.V4); p.update(dict(zip(G,vals)))
    a=P.ev_t1h(RH,p)[0]; b=P.ev_t1(R,p)[0]; c=P.ev_t2(R,p)[0]
    out.write(json.dumps({'P':p,'t1h':a,'t1':b,'t2':c})+'\n'); out.flush()
