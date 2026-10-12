import itertools, json, sys, proto5 as P, zh_eval as Z
RH=Z.get_t1h('v5base_deep_all'); R=Z.get('v5base_deep')
G=dict(ph_k=[(3,),(4,),(3,4)], ph_frac=[0.03,0.1,0.3], ph_beta=[0.2,0.4,0.8], ph_pool=[30,60])
out=open(sys.argv[1],'w')
for vals in itertools.product(*G.values()):
    p=dict(P.V4); p.update(dict(zip(G,vals)))
    a=P.ev_t1h(RH,p)[0]; b=P.ev_t1(R,p)[0]; c=P.ev_t2(R,p)[0]
    out.write(json.dumps({'P':p,'t1h':a,'t1':b,'t2':c})+'\n'); out.flush()
