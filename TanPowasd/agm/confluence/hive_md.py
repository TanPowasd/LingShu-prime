# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流多维 v3×3 × hive-memory-bench 主轮检索面（零 key、零模型），口径同 bench/hive_retrieval.py：
同一 160 字句界块、同一字符预算，读 primary 证据召回等。
中文零模型源图：每块的显著二元组（旧 AGM 的术语集）作实体，块内按出现顺序相邻的两个实体连一条谓词边（主→宾）。
用法：python hive_md.py <hive-memory-bench 路径>"""
import collections, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import hive_retrieval as HR, confluence as C, multidim as M  # noqa: E402

root = pathlib.Path(sys.argv[1])
chunks, cards = HR.load_chunks(root), HR.load_cards(root)
bm = HR.BM25(chunks); agm = HR.AGM(chunks, bm)
C.ent_key = lambda s: str(s)                      # 中文：实体名即二元组本身
C.content = lambda k: {k} if k else set()
tri = []
for c, T in zip(chunks, agm.T):
    pos = sorted((c["n"].find(t), t) for t in T)
    tri.append([[a, "共现", b] for (_, a), (_, b) in zip(pos, pos[1:])])
ids = [f"{c['cid']}:{c['i']}" for c in chunks]


class HiveMD(M.MultiDim):
    def qents(self, q):
        qb = set(HR.bigrams(q))
        return {e: 1 for e in self.prov if next(iter(self.cw[e])) in qb}


arms = {"BM25": None, "旧AGM": None, "v3": None, "多维v3×3": {"w_v3": 3.0}, "多维v3×2": {"w_v3": 2.0}}
mds = {k: HiveMD([c["text"] for c in chunks], ids, tri, **v) for k, v in arms.items() if v}
md0 = next(iter(mds.values()))
orders = {k: {} for k in arms}
for c in cards:
    q = c["question"]; s = bm.scores(q)
    orders["BM25"][c["qid"]] = sorted(range(len(chunks)), key=lambda i: -s[i])
    orders["旧AGM"][c["qid"]] = agm.rank(q)
    orders["v3"][c["qid"]] = md0.base.v3_turns(q)
    for k, g in mds.items():
        orders[k][c["qid"]] = g.rank(q)
out = {}
for B in HR.BUDGETS:
    row = {k: HR.evaluate(cards, lambda c, od=od: HR.take(od[c["qid"]], chunks, B)) for k, od in orders.items()}
    for A, Bn in (("多维v3×3", "v3"), ("多维v3×3", "旧AGM")):
        w = l = 0
        for c in cards:
            ps = [HR.norm(e["quote"]) for e in c.get("supporting_evidence") or [] if e.get("weight") == "primary"]
            if not ps:
                continue
            ca, cb = HR.take(orders[A][c["qid"]], chunks, B), HR.take(orders[Bn][c["qid"]], chunks, B)
            d = sum(x in ca for x in ps) - sum(x in cb for x in ps); w += d > 0; l += d < 0
        row[f"{A} vs {Bn} 胜/负"] = [w, l]
    out[f"预算{B}"] = row
    print(B, {k: (v["primary证据召回"], v["全证据题"]) if isinstance(v, dict) else v for k, v in row.items()}, flush=True)
(HERE / "results").mkdir(exist_ok=True)
(HERE / "results" / "hive_md_zerokey.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
