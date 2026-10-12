# -*- coding: utf-8 -*-
"""chain-r12 A 臂逐句等价验证：在 dev 语料上建账，导出全部记录（全字段）的摘要与逐条列表，两个代码根逐条比对。
不计算任何指标，只比对输出是否逐条相同。
  python r12_equiv.py dump <root> <out.json> [parts]   parts 逗号分隔：clean,dev,novel,e2e（缺省全部）
  python r12_equiv.py cmp a.json b.json"""
import glob, hashlib, importlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CH = "/workspace/work/ls/hmb/chain"
SPLIT = re.compile(r"(?<=[。])")
DEVMAPS = {"h1": "heldout", "d2": "heldout_d2", "d3": "heldout_d3", "d4": "heldout_d4", "d5": "heldout_d5",
           "h4": "heldout_h4", "h5": "heldout_h5", "h6": "heldout_h6", "h7": "heldout_h7"}


def rec(r):
    return [r.op, r.entity, r.attr, r.value, r.alt, getattr(r, "reason", None), r.quote, r.ref,
            sorted((getattr(r, "extra", None) or {}).items(), key=lambda kv: kv[0]).__repr__()]


def build(LG, docs, rw=None):
    L = LG.Ledger()
    for c in docs:
        t = c["text"]
        if rw:
            s = SPLIT.split(t)
            for i in range(len(s)):
                r = rw.get(f"{c['cid']}|{i}")
                if r and r["new"]:
                    s[i] = r["new"]
            t = "".join(s)
        L.add_text(t, ref=c["cid"])
    return [rec(r) for r in L.recs]


def dump(root, outp, parts):
    sys.path.insert(0, root)
    LG = importlib.import_module("lingshu_ng.chain.ledger")
    assert LG.__file__.startswith(root), LG.__file__
    corpus = json.load(open(os.path.join(CH, "corpus", "corpus.json"), encoding="utf-8"))
    res = {}
    if "clean" in parts:
        res["clean"] = build(LG, corpus)
    if "dev" in parts:
        for k, d in DEVMAPS.items():
            res["dev_" + k] = build(LG, corpus, json.load(open(os.path.join(OUT, d, "rewrite_map.json"), encoding="utf-8")))
    if "novel" in parts:
        sys.path.insert(1, "/workspace/work/ls/wt-titans/bench_titans")
        from common import novel_chunks  # noqa
        L = LG.Ledger()
        for i, c in enumerate(novel_chunks()):
            if i % 2 == 0:
                L.add_text(c["text"], ref=str(i))
        res["novel_even"] = [rec(r) for r in L.recs]
    if "e2e" in parts:
        out = []
        for p in sorted(glob.glob("/workspace/work/ls/hmb/e2e/corpus/*.md")):
            b = os.path.basename(p)
            if int(hashlib.md5(b.encode()).hexdigest()[0], 16) % 2 != 0:
                continue
            L = LG.Ledger()
            for j, para in enumerate(open(p, encoding="utf-8").read()[:200000].split("\n")):
                if para.strip():
                    L.add_text(para, ref=f"{b}#{j}")
            out += [rec(r) for r in L.recs]
        res["e2e_even"] = out
    json.dump(res, open(outp, "w", encoding="utf-8"), ensure_ascii=False)
    print({k: len(v) for k, v in res.items()})


def cmp(a, b):
    A, B = json.load(open(a)), json.load(open(b)); ok = True
    for k in sorted(set(A) | set(B)):
        x, y = A.get(k), B.get(k)
        same = x == y
        ok &= same
        print(k, len(x or []), len(y or []), "SAME" if same else "DIFF")
        if not same and x and y:
            n = 0
            for i, (p, q) in enumerate(zip(x, y)):
                if p != q:
                    print("  ", i, p, "\n   ", q); n += 1
                    if n >= 5:
                        break
    print("ALL_SAME" if ok else "NOT_SAME")


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        dump(sys.argv[2], sys.argv[3], set((sys.argv[4] if len(sys.argv) > 4 else "clean,dev,novel,e2e").split(",")))
    else:
        cmp(sys.argv[2], sys.argv[3])
