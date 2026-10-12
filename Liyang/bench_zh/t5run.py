# v5 test 单次运行（PREREG_ZH §5 v5 登记 47dd5f7）：T1-H2 探索集全部臂 + T1-H test v5 + 原 T2/T1 test v5
import os, subprocess, sys, time, json
import zh_eval as Z
S = os.path.join(Z.HERE, "snap"); DET = {"ZH_DET": "1"}; t = time.time()
def log(*a): print(f"[{time.time()-t:.0f}s]", *a, flush=True)
Z.set_t1h("2")
for tag, root in (("v5_test", f"{S}/647d51d"), ("v4_test", f"{S}/9592060"), ("v3_test", f"{S}/33f05a3")):
    Z.run_t1h(tag, "test", root=root, env=DET); log("t1h2", tag)
Z.t1h_arms(); log("t1h2 AGM/BM25")
for arm in ("md_heur", "md_llm", "tricue"):
    r = subprocess.run([sys.executable, "conf_arms.py", arm, "hive", "t1h2", f"runs/conf/{arm}_hive_t1h2.json"], capture_output=True, text=True)
    log("t1h2", arm, r.stdout.strip()[-300:], r.stderr.strip()[-300:])
Z.set_t1h("")
Z.run_t1h("v5_test", "test", root=f"{S}/647d51d", env=DET); log("t1h test v5")
Z.run("test_v5_det", root=f"{S}/647d51d", env=DET); log("orig T1/T2 v5")
log("DONE")
