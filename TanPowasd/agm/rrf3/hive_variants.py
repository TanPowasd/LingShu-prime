# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""RRF3 变体在 hive-memory-bench e2e 上的零模型对照（覆盖、窗口外、逐文件胜负）。
用法：python hive_variants.py <hive-memory-bench> v10 c100 t50c100 ...
  变体名：v10＝v1.0 参数；v11＝v1.1 默认；t<T>c<C>＝temporal=T/100、df_cap=C/100（缺省项取默认）。
目标与 verify_equiv.py 相同（回复里全文 df≤2% 的字二元组，去掉问句已有的）。
"""
import collections, pathlib, sys
HERE = pathlib.Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import rrf3 as R  # noqa: E402
from hive_e2e_stream import bset, chunk_turn, parse  # noqa: E402


def make(v):
    if v == 'v10':
        return R.RRF3Memory(df_cap=R.BM25_DF_CAP_V10)
    if v == 'v11':
        return R.RRF3Memory()
    t = c = None
    s = v
    if s.startswith('t'):
        s = s[1:]; t, _, s = s.partition('c'); s = 'c' + s if s else ''
    if s.startswith('c'):
        c = s[1:]
    return R.RRF3Memory(temporal=int(t) / 100 if t else 0.0, df_cap=int(c) / 100 if c else R.BM25_DF_CAP_V10)


def main():
    root, vs = sys.argv[1], sys.argv[2:]
    budget = 4000
    files = sorted((pathlib.Path(root) / "e2e" / "corpus").glob("*.md"))
    per = {v: [] for v in vs}
    for f in files:
        turns = parse(f)
        allc = [c for t in turns for c in chunk_turn(t)]
        dfc = collections.Counter(g for _, x in allc for g in bset(x))
        capf = max(2, int(0.02 * len(allc)))
        mems = {v: make(v) for v in vs}
        s = {v: [0.0, 0.0] for v in vs}; n = 0
        for ti, t in enumerate(turns):
            m0 = mems[vs[0]]
            if t["who"] == "human" and ti + 1 < len(turns) and turns[ti + 1]["who"] == "ai" and m0.N:
                q = bset(t["text"])
                tgt = {g for g in bset(turns[ti + 1]["text"]) if dfc.get(g, 0) <= capf} - q
                if tgt:
                    n += 1
                    rec, used = set(), 0
                    for i in m0.rank_recent():
                        if used + m0.size[i] > budget and used: break
                        rec |= bset(m0.raw[i]); used += m0.size[i]
                    for v in vs:
                        cx = set().union(*(bset(h.text) for h in mems[v].retrieve(t["text"], budget)))
                        s[v][0] += len(tgt & cx) / len(tgt); s[v][1] += len((tgt & cx) - rec) / len(tgt)
            for v in vs:
                mems[v].add_turn(t["who"], t["text"])
        for v in vs:
            per[v].append((s[v][0] / n, s[v][1] / n, n))
    base = per[vs[0]]
    for v in vs:
        N = sum(x[2] for x in per[v])
        cov = sum(x[0] * x[2] for x in per[v]) / N; wo = sum(x[1] * x[2] for x in per[v]) / N
        w = sum(a[1] > b[1] + 1e-12 for a, b in zip(per[v], base)); l = sum(a[1] < b[1] - 1e-12 for a, b in zip(per[v], base))
        print(f"{v:10s} 覆盖 {cov:.4f}  窗口外 {wo:.4f}  窗口外逐文件 胜{w}/负{l}（对 {vs[0]}）  查询 {N}")


if __name__ == "__main__":
    main()
