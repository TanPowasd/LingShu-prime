# -*- coding: utf-8 -*-
"""chain-r13 dev 读数（只用已暴露集：H1-dev/D2/D3/D4/D5 + H4–H8）。语料级抽取（ledger_cov 口径）。
  python r13_dev.py [sets] [--bad N]   缺省全部；--bad 打印每集前 N 条非 exact（键对比）"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE)
import ledger_cov as C  # noqa
SETS = {"h1": ("heldout", C.DEVDOCS, None), "d2": ("heldout_d2", C.DEVDOCS, None), "d3": ("heldout_d3", C.DEVDOCS, None),
        "d4": ("heldout_d4", C.DEVDOCS, None), "d5": ("heldout_d5", C.DEVDOCS, None), "h4": ("heldout_h4", None, None),
        "h5": ("heldout_h5", None, None), "h6": ("heldout_h6", None, None), "h7": ("heldout_h7", None, None),
        "h8": ("heldout_h8", None, "corpus_h8base.json"),
        "h9": ("heldout_h9", None, "corpus_h9base.json"),
        "h10": ("heldout_h10", None, "corpus_h10base.json"),
        "h11": ("heldout_h11", None, "corpus_h11base.json"),
        "h12": ("heldout_h12", None, "corpus_h12base.json"),
        "h13": ("heldout_h13", None, "corpus_h13base.json"),
        "h14": ("heldout_h14", None, "corpus_h14base.json")}   # chain-r13/r14 单次运行后暴露，降为 dev
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    nbad = int(sys.argv[sys.argv.index("--bad") + 1]) if "--bad" in sys.argv else 0
    if nbad:
        args = [a for a in args if not a.isdigit()]
    res = {}
    for k in (args[0].split(",") if args else SETS):
        d, docs, base = SETS[k]
        if base:
            os.environ["LC_BASE"] = os.path.join(OUT, d, base)
        else:
            os.environ.pop("LC_BASE", None)
        dp = f"/tmp/r13dev_{k}.json"; os.environ["LC_DUMP"] = dp
        st = C.cov(os.path.join(OUT, d, "rewrite_map.json"), docs)
        res[k] = st
        print(k, st, flush=True)
        if nbad:
            sent = json.load(open(dp)); n = 0
            for kk, v in sent.items():
                if v != "exact":
                    print("   ", v, kk.split("|", 1)[1][:110]); n += 1
                    if n >= nbad:
                        break
    print(json.dumps({k: v["exact_rate"] for k, v in res.items()}))


if __name__ == "__main__":
    main()
