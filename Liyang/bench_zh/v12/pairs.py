# zh-v12（修订 10）：已暴露 dev（T2R2 r1dev + r2dev）题内 E / M / rel0 段落表 → runs/t2r2/v12/pairs.json
import json, os, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
os.environ.setdefault("T2R_SET", "t2r2")
import t2r_eval as E
out = {}
for sp in ("r1dev", "r2dev"):
    for c in E.cards(sp):
        st = E.T()["S"][c["store"]]
        it = [(i, "E") for i in c["ev"]] + [(i, "M") for i in c["mis"]] + [(i, "0") for i in c["rel0"]]
        out[c["qid"]] = {"split": sp, "q": c["question"], "items": [{"i": i, "lab": l, "t": st["docs"][i]["text"]} for i, l in it]}
os.makedirs(os.path.join(E.OUT, "v12"), exist_ok=True)
json.dump(out, open(os.path.join(E.OUT, "v12", "pairs.json"), "w"), ensure_ascii=False)
from collections import Counter
print(len(out), Counter(x["lab"] for v in out.values() for x in v["items"]))
