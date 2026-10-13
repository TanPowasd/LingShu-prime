# r13 dev 门读数（修订 14 R14.3）：w40 vs BASE；全部无显著负且 loc/lme 容差过 ⇒ 写 out/r13_devgate.ok
import sys, os, json, statistics
sys.argv = ["x", "w40"]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import gen_eval as G
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "r13_judge.py")).read()
exec(src.split("out = {")[0].split("import gen_eval as G  # noqa: E402")[1])
res, ok = {}, True
for s, ks in DEV.items():
    tag = "r12_it2" if s.startswith("cm") else "r13_dev"
    jf = f"/tmp/gen_jobs/{s}.jsonl"; rf = os.path.join(G.RUNS, tag, f"{s}.0.jsonl")
    nj = sum(1 for x in open(jf) if x.strip()); nr = sum(1 for x in open(rf) if x.strip()) if os.path.exists(rf) else 0
    if nr < nj:
        print(s, "INCOMPLETE", nr, nj); ok = False; continue
    A = per(f"{tag}@w40", s); B = per(f"{tag}@BASE", s)
    res[s] = {k: comp(A, B, k) for k in ks}
    print(s, " ".join(f"{k}:{c['a']:.4f}/{c['b']:.4f} {c['win']}:{c['loss']}{c['sig']}" for k, c in res[s].items()))
    if any(c["sig"] == "-" for c in res[s].values()): ok = False
if "loc_dev" in res and res["loc_dev"]["r@10"]["a"] < res["loc_dev"]["r@10"]["b"] - .005: ok = False
if "lme_dev" in res and any(res["lme_dev"][k]["a"] < res["lme_dev"][k]["b"] - .013 for k in ("t@10", "s@5")): ok = False
G.dump(os.path.join(G.OUT, "r13_devgate.json"), {"ok": ok, "res": res})
print("DEVGATE_OK" if ok else "DEVGATE_FAIL")
if ok:
    open(os.path.join(G.OUT, "r13_devgate.ok"), "w").write("ok\n")
