# -*- coding: utf-8 -*-
"""chain-r14 H10 单次评测件（PREREG_R14.md）。
  python r14_h10.py cov <tag>        语料级抽取（LC_BASE=H10 换名语料；FP_ROOT 选代码根；LINGSHU_NG_CHAIN_LLM 选 B 臂），落 lc_sent_<tag>.json
  python r14_h10.py fp <tag>         误登记 R14 区段（信任协议权重调整.md [1400000:] + 学习能力理论讨论邀请.md 最后 82319 字，各自建账）+ 小说奇数块
  python r14_h10.py sign a b         逐句配对符号检验（exact vs 非 exact）"""
import json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "out", "heldout_h10")
E2E = "/workspace/work/ls/hmb/e2e/corpus"
#: R14 区段（预登记，从未读过）：(文件, 起, 止)
R14 = [("信任协议权重调整.md", 1400000, None), ("学习能力理论讨论邀请.md", -82319, None)]


def fp_r14(C):
    sys.path.insert(1, "/workspace/work/ls/wt-titans/bench_titans")
    from common import novel_chunks  # noqa
    LG = C.LG; res = {}
    L = LG.Ledger()
    for i, c in enumerate(novel_chunks()):
        if i % 2 == 1:
            L.add_text(c["text"], ref=str(i))
    res["novel"] = sum(r.op not in ("mention",) for r in L.recs)
    per = {}; chars = 0
    for fn, a, b in R14:
        t = open(os.path.join(E2E, fn), encoding="utf-8").read()[a:b]; chars += len(t)
        L = LG.Ledger()
        for j, para in enumerate(t.split("\n")):
            if para.strip():
                L.add_text(para, ref=f"{fn}#r14_{j}")
        per[fn] = sum(r.op not in ("mention",) for r in L.recs)
    res["e2e"] = sum(per.values()); res["e2e_per_file"] = per; res["e2e_chars"] = chars
    res["total"] = res["e2e"] + res["novel"]
    return res


if __name__ == "__main__":
    if sys.argv[1] in ("cov", "fp"):
        tag = sys.argv[2]
        os.environ.setdefault("LC_BASE", os.path.join(D, "corpus_h10base.json"))
        os.environ["LC_DUMP"] = os.path.join(D, f"lc_sent_{tag}.json")
        sys.path.insert(0, HERE)
        import ledger_cov as C  # noqa: E402
        try:
            from lingshu_ng.chain import llm_extract as M  # noqa: E402
            assert M.__file__.startswith(C.ROOT)
            stats = M.STATS
        except Exception:  # noqa: BLE001
            stats = None
        t = time.time()
        st = C.cov(os.path.join(D, "rewrite_map.json")) if sys.argv[1] == "cov" else fp_r14(C)
        out = {"tag": tag, "root": C.ROOT, **st, "wall_s": round(time.time() - t, 2), "llm": stats}
        print(json.dumps(out, ensure_ascii=False))
    else:
        a = json.load(open(os.path.join(D, f"lc_sent_{sys.argv[2]}.json"))); b = json.load(open(os.path.join(D, f"lc_sent_{sys.argv[3]}.json")))
        assert set(a) == set(b)
        w = sum(a[k] == "exact" and b[k] != "exact" for k in a); l_ = sum(a[k] != "exact" and b[k] == "exact" for k in a)
        n = w + l_; k = min(w, l_)
        p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
        print(json.dumps({"A": sys.argv[2], "B": sys.argv[3], "n": len(a), "A_exact": sum(v == "exact" for v in a.values()),
                          "B_exact": sum(v == "exact" for v in b.values()), "win": w, "loss": l_, "p": p}))
