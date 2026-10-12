import json, sys
AGM = {"T2": {"cid": .5854, "quote": .2850, "point": .5679, "excl": .25},
       "T1_2000": {"primary": .279, "full": .077, "cross": 0, "excl": .304},
       "T1_4000": {"primary": .349, "full": .077, "cross": 0, "excl": .348},
       "T1_8000": {"primary": .5, "full": .154, "cross": .091, "excl": .522}}
def score(m):
    t2 = m["T2"]; s = 2 * t2["quote"] - t2["excl"] + 0.5 * t2["cid"] + 0.5 * t2["point"]
    for B, w in (("T1_2000", .5), ("T1_4000", .7), ("T1_8000", 1.0)):
        r = m[B]; s += w * (r["primary"] + 0.5 * (r["full"] or 0) + 0.5 * (r["cross"] or 0) - 0.3 * r["excl"])
    return s
def nlose(m):
    n = 0
    for blk, d in AGM.items():
        for k, v in d.items():
            x = m[blk][k] or 0
            n += (x > v + 1e-9) if k == "excl" else (x < v - 1e-9)
    return n
if __name__ == "__main__":
    rows = [json.loads(l) for l in open(sys.argv[1])]
    key = sys.argv[2] if len(sys.argv) > 2 else "score"
    rows.sort(key=lambda r: (nlose(r["m"]), -score(r["m"])) if key == "lose" else -score(r["m"]))
    import zh_eval as Z
    for r in rows[:int(sys.argv[3]) if len(sys.argv) > 3 else 15]:
        P = {k: v for k, v in r["P"].items() if k not in ("pool", "wa", "pw", "topk")}
        print(round(score(r["m"]), 3), nlose(r["m"]), P); print("   ", Z.fmt(r["m"]))
