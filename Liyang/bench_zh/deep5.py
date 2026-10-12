# v5 离线原型的底名单：HEAD 引擎关 LC（= v3 序），HMB limit100、hive limit300；T1-H 全 76 题（只在 dev 上用）
import sys, time, zh_eval as Z
t=time.time(); env={"ZH_DET":"1","LINGSHU_NG_ASSOC":'{"lc_beta":0}'}
Z.run("v5base_deep", env=env, hmb_limit=100, hive_limit=300); print("t1/t2", time.time()-t, flush=True)
Z.run_t1h("v5base_deep_all", "all", env=env, limit=300); print("t1h", time.time()-t, flush=True)
