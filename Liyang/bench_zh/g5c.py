import itertools, json, sys, proto5 as P, zh_eval as Z
RH=Z.get_t1h('v5base_deep_all'); R=Z.get('v5base_deep')
HD=[dict(), dict(hd_n=10,hd_S=3,hd_w=2,hd_beta=0.8,hd_gate=0.05), dict(hd_n=10,hd_S=5,hd_w=1,hd_beta=0.5,hd_gate=0), dict(hd_n=10,hd_S=3,hd_w=1,hd_beta=0.5,hd_gate=0.05), dict(hd_n=10,hd_S=2,hd_w=2,hd_beta=0.8,hd_gate=0.05)]
G=dict(lc_beta=[0.3,0.5,0.8], lc_gate=[0,0.05,0.1,0.2], lc_tight=[0,1,2], lc_span=[2,3,4], lc_seeds=[10,20])
out=open(sys.argv[1],'w')
for hi,h in enumerate(HD):
  for vals in itertools.product(*G.values()):
    p=dict(P.V4); p.update(h); p.update(dict(zip(G,vals)))
    if p['lc_gate']==0 and p['lc_tight']>0: continue
    a=P.ev_t1h(RH,p)[0]; b=P.ev_t1(R,p)[0]
    out.write(json.dumps({'hd':hi,'P':p,'t1h':a,'t1':b})+'\n'); out.flush()
