# v4 引擎实测网格（dev：T1-H dev 30 + T1 dev 13；T2 不受影响因 lc_head ≥ 10）
import itertools, json, sys
import zh_eval as Z
out = open(sys.argv[1], "w")
for b, h, S, w, dec in itertools.product((0.5, 0.6, 0.8), (10, 15), (20,), (2, 3), (0.5, 0.7)):
    cfg = json.dumps({"lc_beta": b, "lc_head": h, "lc_seeds": S, "lc_span": w, "lc_decay": dec})
    env = {"ZH_DET": "1", "LINGSHU_NG_ASSOC": cfg}
    Z.run_t1h("g4b", "dev", env=env); mh = Z.metrics_t1h("g4b", "dev")
    Z.run("g4b", env=env); m1 = Z.metrics("g4b", "dev")
    out.write(json.dumps({"cfg": cfg, "t1h": mh, "t1": {k: v for k, v in m1.items() if k.startswith("T1")}}) + "\n"); out.flush()
