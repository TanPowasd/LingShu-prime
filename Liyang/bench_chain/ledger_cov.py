# -*- coding: utf-8 -*-
"""v9 语料级抽取覆盖：把改写集套进语料（只改写 rewrite_map 里的句子），按语料序逐段建账（含词表锚定二次抽取），
逐个改写句看账本里有没有同句（ref＝cid、quote＝改写句）的事件、键是否与原句一致。
  python ledger_cov.py dev                 dev 改写集（H1-dev / D2 / D3）
  python ledger_cov.py fp dev|held         误登记：小说奇偶块、e2e 奇偶文件上建账，数登记条数（锚定开/关）
  python ledger_cov.py set <rewrite_map>   任意改写集（冻结后的保留集只跑一次）
可设 FP_ROOT=<代码根>。"""
import importlib, json, os, re, sys
ROOT = os.environ.get("FP_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
LG = importlib.import_module("lingshu_ng.chain.ledger")
EX = importlib.import_module("lingshu_ng.chain.extract")
assert LG.__file__.startswith(ROOT), LG.__file__
try:
    ANC = importlib.import_module("lingshu_ng.chain.anchored")
except ImportError:
    ANC = None
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
CH = "/workspace/work/ls/hmb/chain"
SPLIT = re.compile(r"(?<=[。])")
DEVDOCS = {"猎户项目", "青石镇"}


def load(p):
    return json.load(open(p, encoding="utf-8"))


def key(op, e, a, v, alt):
    return (op, e, a, v, alt)


def cov(rmp, only_docs=None):
    rw = load(rmp)
    if only_docs:
        rw = {k: v for k, v in rw.items() if k.split("#")[0] in only_docs}
    corpus = load(os.environ.get("LC_BASE") or os.path.join(CH, "corpus", "corpus.json"))   # chain-r12：H8 用换名后的基础语料
    L = LG.Ledger(); want = {}
    for c in corpus:
        sents = SPLIT.split(c["text"])
        for i in range(len(sents)):
            r = rw.get(f"{c['cid']}|{i}")
            if r and r["new"]:
                sents[i] = r["new"]
                o = [e for e in EX.extract(r["orig"], loose=False) if e.op != "mention"][0]
                want[(c["cid"], r["new"].strip())] = key(o.op, o.entity, o.attr, o.value, o.alt)
        L.add_text("".join(sents), ref=c["cid"])
    got = {}
    for r in L.recs:
        if r.op in ("mention", "rename"):
            continue
        got.setdefault((r.ref, r.quote.strip()), []).append(key(r.op, r.entity, r.attr, r.value, r.alt))
    if os.environ.get("LC_ML") == "1":                   # chain-r16 口径修订（PREREG_R16）：多行改写句（主题行+正文）按行登记，quote 等于该句任一非空行的记录归到该句（各臂一致）
        for (cid, s_) in list(want):
            if "\n" in s_:
                for ln in {x.strip() for x in s_.split("\n") if x.strip()}:
                    got.setdefault((cid, s_), []).extend(got.get((cid, ln), []))
    st = {"exact": 0, "wrong": 0, "none": 0}
    for k, w in want.items():
        g = got.get(k)
        st["none" if not g else "exact" if w in g else "wrong"] += 1
    st["n"] = len(want); st["exact_rate"] = round(st["exact"] / max(1, st["n"]), 4)
    if os.environ.get("LC_DUMP"):                        # chain-r10：逐句结果（配对符号检验用），键＝cid|改写句
        json.dump({f"{k[0]}|{k[1]}": ("none" if not got.get(k) else "exact" if w in got[k] else "wrong") for k, w in want.items()},
                  open(os.environ["LC_DUMP"], "w", encoding="utf-8"), ensure_ascii=False)
    return st


def fp(half):
    sys.path.insert(1, "/workspace/work/ls/wt-titans/bench_titans")
    from common import novel_chunks  # noqa
    import glob, hashlib
    res = {}
    L = LG.Ledger()
    for i, c in enumerate(novel_chunks()):
        if (i % 2 == 0) == (half == "dev"):
            L.add_text(c["text"], ref=str(i))
    res["novel"] = sum(r.op not in ("mention",) for r in L.recs)
    n = 0
    for p in sorted(glob.glob("/workspace/work/ls/hmb/e2e/corpus/*.md")):
        b = os.path.basename(p)
        h = "dev" if int(hashlib.md5(b.encode()).hexdigest()[0], 16) % 2 == 0 else "held"
        if h != half:
            continue
        L = LG.Ledger()
        off = int(os.environ.get("FP_OFF", "0"))         # 冻结后读 held 用新区段（20 万–40 万字），与 v8 的精度读数区段不重叠
        for j, para in enumerate(open(p, encoding="utf-8").read()[off:off + 200000].split("\n")):
            if para.strip():
                L.add_text(para, ref=f"{b}#{j}")
        n += sum(r.op not in ("mention",) for r in L.recs)
    res["e2e"] = n
    return res


if __name__ == "__main__":
    if sys.argv[1] == "dev":
        out = {"h1": cov(os.path.join(OUT, "heldout", "rewrite_map.json"), DEVDOCS),
               "d2": cov(os.path.join(OUT, "heldout_d2", "rewrite_map.json"), DEVDOCS),
               "d3": cov(os.path.join(OUT, "heldout_d3", "rewrite_map.json"), DEVDOCS)}
        if os.environ.get("DEV_R10", "1") != "0":          # chain-r10：H4（已暴露，降为 dev）与 D4/D5
            out.update({"h4": cov(os.path.join(OUT, "heldout_h4", "rewrite_map.json")),
                        "d4": cov(os.path.join(OUT, "heldout_d4", "rewrite_map.json"), DEVDOCS),
                        "d5": cov(os.path.join(OUT, "heldout_d5", "rewrite_map.json"), DEVDOCS)})
        for k, v in out.items():
            print(k, v)
    elif sys.argv[1] == "fp":
        print(json.dumps(fp(sys.argv[2])))
    else:
        print(json.dumps(cov(sys.argv[2])))
