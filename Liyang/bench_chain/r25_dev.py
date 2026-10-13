# -*- coding: utf-8 -*-
"""chain-r25 读数（PREREG_R25 §4）：调参 H20+H19，D8(=H18)（可看逐句）+ D7 + 旧 16 集。LC_ML=1。
  LINGSHU_NG_CHAIN_V22_FAM=A python r22_dev.py [sets] > out.json"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE)
os.environ.setdefault("LC_ML", "1"); os.environ.setdefault("LINGSHU_NG_CHAIN_LLM", "0")
import ledger_cov as C  # noqa
TUNE = ["h20", "h19", "h18", "h1", "d2", "d3", "d4", "d5", "d6", "h4", "h5", "h6", "h7", "h8", "h9", "h12", "h13", "h14", "h16", "d7"]
HOLD = []
DEVD = {"h1": "heldout", "d2": "heldout_d2", "d3": "heldout_d3", "d4": "heldout_d4", "d5": "heldout_d5", "d6": "heldout_d6", "d7": "heldout_d7"}


def one(k):
    d = DEVD.get(k, f"heldout_{k}")
    base = os.path.join(OUT, d, f"corpus_{k}base.json")
    if os.path.exists(base):
        os.environ["LC_BASE"] = base
    else:
        os.environ.pop("LC_BASE", None)
    dp = os.environ.get("R23_DUMP")
    if dp and k not in HOLD:
        os.environ["LC_DUMP"] = f"{dp}_{k}.json"
    else:
        os.environ.pop("LC_DUMP", None)
    return C.cov(os.path.join(OUT, d, "rewrite_map.json"), C.DEVDOCS if k in DEVD else None)


if __name__ == "__main__":
    sets = sys.argv[1].split(",") if len(sys.argv) > 1 else TUNE + HOLD
    res = {}
    for k in sets:
        if not os.path.exists(os.path.join(OUT, DEVD.get(k, f"heldout_{k}"), "rewrite_map.json")):
            continue
        t = time.time(); st = one(k); st["s"] = round(time.time() - t, 2); res[k] = st
        print(k, {x: st[x] for x in ("exact", "wrong", "none")}, file=sys.stderr, flush=True)
    tot = {x: sum(res[k][x] for k in res if k in TUNE) for x in ("exact", "wrong", "none")}
    res["_tune"] = tot; res["_fam"] = {k: os.environ.get(k, "") for k in ("LINGSHU_NG_CHAIN_V21_FAM", "LINGSHU_NG_CHAIN_V22_FAM", "LINGSHU_NG_CHAIN_V23_FAM", "LINGSHU_NG_CHAIN_V24_FAM", "LINGSHU_NG_CHAIN_V25_FAM")}
    print(json.dumps(res, ensure_ascii=False))
