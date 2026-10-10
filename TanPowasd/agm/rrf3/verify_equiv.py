# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""对照：rrf3.RRF3Memory 与测评臂 RRF3(近因,BM25,AGM) 在 hive-memory-bench e2e 全部查询上的排序/取块是否逐条一致，并复算覆盖读数。
用法：python verify_equiv.py <hive-memory-bench 路径> [--budget 4000]
"""
import argparse
import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import rrf3 as R  # noqa: E402
import agm_algos as X  # noqa: E402
from hive_e2e_stream import Store, bset, chunk_turn, norm, parse, take  # noqa: E402
from hive_e2e_full import AgmX  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--budget", type=int, default=4000)
    A = ap.parse_args()
    files = sorted((pathlib.Path(A.root) / "e2e" / "corpus").glob("*.md"))
    nq = diff = 0
    cov_sum = 0.0
    for f in files:
        turns = parse(f)
        allc = [c for t in turns for c in chunk_turn(t)]
        dfc = collections.Counter(g for _, x in allc for g in bset(x))
        capf = max(2, int(0.02 * len(allc)))
        st, agm, mem = Store(), None, R.RRF3Memory(df_cap=R.BM25_DF_CAP_V10)  # 对照臂是 v1.0 参数
        agm = AgmX(st, False)
        last = None
        for ti, t in enumerate(turns):
            if t["who"] == "human" and ti + 1 < len(turns) and turns[ti + 1]["who"] == "ai" and st.N:
                q = bset(t["text"])
                reply = turns[ti + 1]["text"]
                tgt = {g for g in bset(reply) if dfc.get(g, 0) <= capf} - q
                if tgt:
                    sc = st.bm25(q)
                    ref = take(X.rrf([list(range(st.N - 1, -1, -1)), sorted(sc, key=lambda i: -sc[i]), agm.rank_from(sc)]), st, A.budget)
                    got = [h.id for h in mem.retrieve(t["text"], A.budget)]
                    nq += 1; diff += ref != got
                    cx = set().union(*(st.bs[i] for i in got)) if got else set()
                    cov_sum += len(tgt & cx) / len(tgt)
            prev = None
            for ln, x in chunk_turn(t):
                i = st.add(ti, ln, x)
                agm.link_new(i, prev, last if prev is None else None)
                prev = i
            if prev is not None:
                last = prev
            mem.add_turn(t["who"], t["text"])
            assert mem.N == st.N
    print(f"文件 {len(files)}  查询 {nq}  取块不一致 {diff}  覆盖(按查询平均) {cov_sum / nq:.4f}")
    sys.exit(1 if diff else 0)


if __name__ == "__main__":
    main()
