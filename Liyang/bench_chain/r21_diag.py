# -*- coding: utf-8 -*-
"""chain-r21 none 诊断（只用调参集：PREREG_R21 §4 的 H16/H14/H13/D6 等；不得用于 H10/H11/H15/H17）。
对每个未登记（none）的改写句：金标键、当时账本锚点（已知主体/已确认属性）是否含金标主体/属性、取值是否逐字在句中。
  python r21_diag.py h16,h14,h13 > /workspace/work/ls/_r21/none_<sets>.jsonl"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE)
FORBID = {"h10", "h11", "h15", "h17"}
SETS = {"h1": ("heldout", True, None), "d2": ("heldout_d2", True, None), "d3": ("heldout_d3", True, None),
        "d4": ("heldout_d4", True, None), "d5": ("heldout_d5", True, None), "d6": ("heldout_d6", True, None),
        "h4": ("heldout_h4", False, None), "h5": ("heldout_h5", False, None), "h6": ("heldout_h6", False, None),
        "h7": ("heldout_h7", False, None)}
for v in ("h8", "h9", "h12", "h13", "h14", "h16"):
    SETS[v] = (f"heldout_{v}", False, f"corpus_{v}base.json")


def run(k):
    assert k not in FORBID
    import ledger_cov as C
    d, dev, base = SETS[k]
    rw = C.load(os.path.join(OUT, d, "rewrite_map.json"))
    if dev:
        rw = {a: b for a, b in rw.items() if a.split("#")[0] in C.DEVDOCS}
    corpus = C.load(os.path.join(OUT, d, base) if base else os.path.join(C.CH, "corpus", "corpus.json"))
    L = C.LG.Ledger(); res = []; pend = []
    for c in corpus:
        sents = C.SPLIT.split(c["text"]); want = {}
        for i in range(len(sents)):
            r = rw.get(f"{c['cid']}|{i}")
            if r and r["new"]:
                sents[i] = r["new"]
                o = [e for e in C.EX.extract(r["orig"], loose=False) if e.op != "mention"][0]
                want[r["new"].strip()] = (o.op, o.entity, o.attr, o.value, o.alt)
        n0 = len(L.recs)
        ns = C.LG.parse_header("".join(sents)).ns or ""
        names0, cattrs0 = L._v13_anchors(ns)
        L.add_text("".join(sents), ref=c["cid"])
        names, cattrs = L._v13_anchors(ns)
        gattrs = L._v16_gattrs()
        for s, w in want.items():
            pend.append((c, s, w, names0, names, cattrs, gattrs))
    got = {}
    for r in L.recs:
        if r.op not in ("mention", "rename"):
            got.setdefault((r.ref, r.quote.strip()), []).append((r.op, r.entity, r.attr, r.value, r.alt))
    for c, s, w, names0, names, cattrs, gattrs in pend:
            g = got.get((c["cid"], s))
            st = "none" if not g else "exact" if w in g else "wrong"
            if st == "exact":
                continue
            res.append({"set": k, "cid": c["cid"], "st": st, "s": s, "w": w, "g": g,
                        "e_known0": w[1] in names0, "e_known": w[1] in names, "e_in": w[1] in s,
                        "a_conf": w[2] in cattrs, "a_glob": w[2] in gattrs, "a_in": w[2] in s,
                        "v_in": bool(w[3]) and w[3] in s, "names_in": [n for n in names if n in s]})
    return res


if __name__ == "__main__":
    for k in sys.argv[1].split(","):
        for r in run(k):
            print(json.dumps(r, ensure_ascii=False))
