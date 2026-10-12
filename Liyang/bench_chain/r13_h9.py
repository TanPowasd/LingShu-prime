# -*- coding: utf-8 -*-
"""chain-r13 H9 单次评测件（PREREG_R13.md）。
  python r12_h8.py cov <tag>        语料级抽取（LC_BASE=H9 换名语料；FP_ROOT 选代码根；LINGSHU_NG_CHAIN_LLM 选 B 臂），落 lc_sent_<tag>.json
  python r12_h8.py fp <tag>         误登记 held（FP_OFF=1200000 + 小说奇数块）
  python r12_h8.py sign a b         逐句配对符号检验（exact vs 非 exact）"""
import json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "out", "heldout_h9")
if sys.argv[1] in ("cov", "fp"):
    tag = sys.argv[2]
    os.environ.setdefault("LC_BASE", os.path.join(D, "corpus_h9base.json"))
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
    st = C.cov(os.path.join(D, "rewrite_map.json")) if sys.argv[1] == "cov" else C.fp("held")
    out = {"tag": tag, "root": C.ROOT, **st, "wall_s": round(time.time() - t, 2), "llm": stats}
    if sys.argv[1] == "fp":
        out["fp_off"] = os.environ.get("FP_OFF")
    print(json.dumps(out, ensure_ascii=False))
else:
    a = json.load(open(os.path.join(D, f"lc_sent_{sys.argv[2]}.json"))); b = json.load(open(os.path.join(D, f"lc_sent_{sys.argv[3]}.json")))
    assert set(a) == set(b)
    w = sum(a[k] == "exact" and b[k] != "exact" for k in a); l_ = sum(a[k] != "exact" and b[k] == "exact" for k in a)
    n = w + l_; k = min(w, l_)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
    print(json.dumps({"A": sys.argv[2], "B": sys.argv[3], "n": len(a), "A_exact": sum(v == "exact" for v in a.values()),
                      "B_exact": sum(v == "exact" for v in b.values()), "win": w, "loss": l_, "p": p}))
