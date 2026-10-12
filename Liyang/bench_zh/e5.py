# v5 引擎读数（dev only）：python e5.py tag '{"hd_beta":0.8,...}'
import json, sys, zh_eval as Z
tag=sys.argv[1]; env={"ZH_DET":"1"}
if len(sys.argv)>2 and sys.argv[2]: env["LINGSHU_NG_ASSOC"]=sys.argv[2]
Z.run(tag, env=env); Z.run_t1h(tag+"_dev", "dev", env=env)
print(tag, sys.argv[2] if len(sys.argv)>2 else "")
print("  T1H", Z.fmt_t1h(Z.metrics_t1h(tag+"_dev","dev")))
print("  ", Z.fmt(Z.metrics(tag,"dev")))
