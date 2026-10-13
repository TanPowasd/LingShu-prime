# chain-r20：_cue_only 与原 _CUE_ONLY.fullmatch 在 dev 全集逐调用一致性核对。 python cue_eq.py <sets>
import os, sys, runpy
sys.path.insert(0, "/workspace/work/ls/wt-chain/bench_chain"); sys.path.insert(0, "/workspace/work/ls/wt-chain")
from lingshu_ng.chain import shorthand as S
new = S._cue_only; ST = {"calls": 0, "long": 0, "pos": 0, "bad": []}
def chk(c):
    a = bool(S._CUE_ONLY.fullmatch(c)); b = new(c)
    ST["calls"] += 1; ST["long"] += len(c) > S._CUE_SHORT; ST["pos"] += a
    if a != b: ST["bad"].append(c)
    return b
S._cue_only = chk
sys.argv = ["r16_diag.py", sys.argv[1], "/workspace/work/ls/_r19b/d_cue.json"]
try:
    runpy.run_path("/workspace/work/ls/wt-chain/bench_chain/r16_diag.py", run_name="__main__")
finally:
    print("CUE", {k: (v if k != "bad" else len(v)) for k, v in ST.items()}, ST["bad"][:5], flush=True)
