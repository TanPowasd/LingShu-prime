# -*- coding: utf-8 -*-
"""chain-r10 开发辅助（只读评测数据，不改任何读数文件）。
  python r10_tools.py sent <rewrite_map> [n] [docs]   逐句单独抽取：exact/wrong/none 计数，打印前 n 条非 exact
  python r10_tools.py lcw <rewrite_map> [n]            语料级建账下的键错明细（含是否锚定）
  python r10_tools.py fp <dev|held> [off] [n]          e2e 某半边某区段上速记事件明细
  python r10_tools.py time <root>                      干净语料 270 段建账耗时（5 次，取中位）"""
import collections, glob, hashlib, importlib, json, os, random, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(HERE)


def _mods(root=WT):
    sys.path.insert(0, root)
    return importlib.import_module("lingshu_ng.chain.extract"), importlib.import_module("lingshu_ng.chain.ledger")


def sent(rmp, n=0, docs=None):
    EX, _ = _mods()
    rw = json.load(open(rmp)); docs = set(docs.split(",")) if docs else None
    st = collections.Counter(); bad = []
    for k, r in rw.items():
        if not r["new"] or (docs and k.split("#")[0] not in docs):
            continue
        o = [e for e in EX.extract(r["orig"], loose=False) if e.op != "mention"][0]
        w = (o.op, o.entity, o.attr, o.value, o.alt)
        ev = [e for e in EX.extract(r["new"]) if e.op != "mention"]
        g = (ev[0].op, ev[0].entity, ev[0].attr, ev[0].value, ev[0].alt) if ev else None
        res = "exact" if g == w else "none" if g is None else "wrong"
        st[res] += 1
        if res != "exact":
            bad.append((res, r["new"], w, g))
    print(dict(st))
    for b in bad[:n]:
        print(b)


def lcw(rmp, n=20):
    sys.path.insert(0, HERE)
    import ledger_cov as C
    rw = C.load(rmp); corpus = C.load(os.path.join(C.CH, "corpus", "corpus.json"))
    L = C.LG.Ledger(); want = {}
    for c in corpus:
        ss = C.SPLIT.split(c["text"])
        for i in range(len(ss)):
            r = rw.get(f"{c['cid']}|{i}")
            if r and r["new"]:
                ss[i] = r["new"]; o = [e for e in C.EX.extract(r["orig"], loose=False) if e.op != "mention"][0]
                want[(c["cid"], r["new"].strip())] = (o.op, o.entity, o.attr, o.value, o.alt)
        L.add_text("".join(ss), ref=c["cid"])
    got = {}
    for r in L.recs:
        if r.op not in ("mention", "rename"):
            got.setdefault((r.ref, r.quote.strip()), []).append((r.op, r.entity, r.attr, r.value, r.alt, getattr(r, "_anchored", False)))
    cnt = collections.Counter(); k_ = 0
    for k, w in want.items():
        g = got.get(k)
        if g and w not in [x[:5] for x in g]:
            cnt[(tuple(i for i in range(5) if g[0][i] != w[i]), g[0][5])] += 1
            if k_ < n:
                print(k[1][:100], "\n  want", w, "\n  got ", g); k_ += 1
    print(cnt)


def fp(half, off=0, n=40):
    EX, _ = _mods()
    hits = []
    for p in sorted(glob.glob("/workspace/work/ls/hmb/e2e/corpus/*.md")):
        b = os.path.basename(p)
        h = "dev" if int(hashlib.md5(b.encode()).hexdigest()[0], 16) % 2 == 0 else "held"
        if h != half:
            continue
        for para in open(p, encoding="utf-8").read()[off:off + 200000].split("\n"):
            if para.strip():
                for e in EX.extract(para):
                    if e.extra.get("short"):
                        hits.append((e.op, e.entity, e.attr, e.value, e.quote[:90]))
    print(len(hits), collections.Counter(h[0] for h in hits))
    random.seed(0)
    for h in random.sample(hits, min(n, len(hits))):
        print(h)


def timing(root):
    _, LG = _mods(root)
    assert LG.__file__.startswith(root), LG.__file__
    c = json.load(open("/workspace/work/ls/hmb/chain/corpus/corpus.json")); ts = []
    for _ in range(5):
        L = LG.Ledger(); t = time.perf_counter()
        for x in c:
            L.add_text(x["text"], ref=x["cid"])
        ts.append(time.perf_counter() - t)
    ts.sort()
    print(json.dumps({"root": root, "median_s": round(ts[2], 4), "all": [round(x, 4) for x in ts], "recs": len(L.recs)}))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "sent":
        sent(a[1], int(a[2]) if len(a) > 2 else 0, a[3] if len(a) > 3 else None)
    elif a[0] == "lcw":
        lcw(a[1], int(a[2]) if len(a) > 2 else 20)
    elif a[0] == "fp":
        fp(a[1], int(a[2]) if len(a) > 2 else 0, int(a[3]) if len(a) > 3 else 40)
    elif a[0] == "time":
        timing(a[1])
