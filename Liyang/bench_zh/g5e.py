import itertools, json, sys, proto5 as P, zh_eval as Z
RH=Z.get_t1h('v5base_deep_all'); R=Z.get('v5base_deep')
HD=dict(hd_n=10,hd_S=3,hd_w=2,hd_beta=0.8,hd_gate=0.05)
G=dict(lc_head=[10,12,15,20], lc_beta=[0.3,0.5,0.8], lc_seeds=[10,15,20], lc_span=[2,3], lc_gate=[0,0.05], lc_tight=[1])
out=open(sys.argv[1],'w')
for vals in itertools.product(*G.values()):
    p=dict(P.V4); p.update(HD); p.update(dict(zip(G,vals)))
    a=P.ev_t1h(RH,p)[0]; b=P.ev_t1(R,p)[0]
    out.write(json.dumps({'P':p,'t1h':a,'t1':b})+'\n'); out.flush()
