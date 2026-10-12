# -*- coding: utf-8 -*-
"""chain-r18 H14 / R18 单次评测件（PREREG_R18.md）。
  python r18_h14.py sel                v9 只计数选段（FP_ROOT=v9 快照）：按 (k, 文件名) 顺序逐窗建账，累计 ≥100 即停 → out/heldout_h14/r17_sel.json（只落条数）
  python r18_h14.py cov <tag>          H14 语料级抽取（LC_BASE=H14 换名语料；FP_ROOT 选代码根）→ lc_sent_<tag>.json
  python r18_h14.py fp <tag>           误登记：R18 窗口（r18_sel.json 里的窗）各自建账 + 小说奇数块
  python r18_h14.py sign a b           逐句配对 McNemar（精确二项；exact vs 非 exact）"""
import glob, hashlib, json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "out", "heldout_h14")
D17 = os.path.join(HERE, "out", "heldout_h13")
D16 = os.path.join(HERE, "out", "heldout_h12")
D15 = os.path.join(HERE, "out", "heldout_h11")
E2E = "/workspace/work/ls/hmb/e2e/corpus"
W = 200000
STOP_AT = 100
#: 学习能力理论讨论邀请.md 末 82,319 字已在 R14 读过
CAP = {"学习能力理论讨论邀请.md": 1858033}


def windows():
    files = []
    for p in sorted(glob.glob(os.path.join(E2E, "*.md"))):
        b = os.path.basename(p)
        if int(hashlib.md5(b.encode()).hexdigest()[0], 16) % 2 != 0:
            continue                                        # 只用偶数（dev）文件的未读部分
        n = len(open(p, encoding="utf-8").read())
        files.append((b, min(n, CAP.get(b, n))))
    r15 = {tuple(w["win"]) for w in json.load(open(os.path.join(D15, "r15_sel.json")))["windows"]}   # R15 已读窗不再用
    r15 |= {tuple(w["win"]) for w in json.load(open(os.path.join(D16, "r16_sel.json")))["windows"]}  # R16 已读窗不再用
    r15 |= {tuple(w["win"]) for w in json.load(open(os.path.join(D17, "r17_sel.json")))["windows"]}  # R17 已读窗不再用
    out = []
    k = 1
    while True:
        row = [(b, k * W, min((k + 1) * W, n)) for b, n in files if k * W < n]
        if not row:
            break
        out += [w for w in row if w not in r15]
        k += 1
    n = len(durt_text())                                    # e2e 偶数文件已读尽：其后接 DuRT 段落（20 万字窗，顺序写死）
    out += [("durt", a, min(a + W, n)) for a in range(0, n, W)]
    return out


DURT = "/workspace/work/ls/wt-zh/bench_zh/durt/durt.json"


def durt_text():
    """补充散文源（PREREG_R18 §6 修订）：DuRT 各 store 的段落（store 顺序、段内顺序、按 pid 去重），每段一行。"""
    d = json.load(open(DURT, encoding="utf-8")); seen = set(); out = []
    for st in d["stores"]:
        for p in st["docs"]:
            if p["pid"] in seen:
                continue
            seen.add(p["pid"]); out.append(p["text"].replace("\n", " ").strip())
    return "\n".join(out)


def _text(fn):
    if fn == "durt":
        return durt_text()
    return open(os.path.join(E2E, fn), encoding="utf-8").read()


def count_window(LG, fn, a, b):
    t = _text(fn)[a:b]
    L = LG.Ledger()
    for j, para in enumerate(t.split("\n")):
        if para.strip():
            L.add_text(para, ref=f"{fn}#r18_{a}_{j}")
    return sum(r.op not in ("mention",) for r in L.recs), len(t)


def fp_r15(C):
    sys.path.insert(1, "/workspace/work/ls/wt-titans/bench_titans")
    from common import novel_chunks  # noqa
    LG = C.LG; res = {}
    L = LG.Ledger()
    for i, c in enumerate(novel_chunks()):
        if i % 2 == 1:
            L.add_text(c["text"], ref=str(i))
    res["novel"] = sum(r.op not in ("mention",) for r in L.recs)
    sel = json.load(open(os.path.join(D, "r18_sel.json")))
    per = {}; chars = 0
    for fn, a, b in [tuple(w["win"]) for w in sel["windows"]]:
        n, m = count_window(LG, fn, a, b); chars += m
        per[f"{fn}[{a}:{b}]"] = n
    res["e2e"] = sum(per.values()); res["e2e_per_win"] = per; res["e2e_chars"] = chars
    res["total"] = res["e2e"] + res["novel"]
    return res


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "sel":
        sys.path.insert(0, HERE)
        import ledger_cov as C  # noqa: E402
        assert "chain_v9_snap" in C.ROOT, C.ROOT
        p = os.path.join(D, "r18_sel.json")
        st = json.load(open(p)) if os.path.exists(p) else {"root": C.ROOT, "windows": [], "total": 0, "done": False}
        seen = {tuple(w["win"]) for w in st["windows"]}
        t0 = time.time()
        for w in windows():
            if st["done"] or time.time() - t0 > float(os.environ.get("SEL_BUDGET", "900")):
                break
            if w in seen:
                continue
            n, m = count_window(C.LG, *w)
            st["windows"].append({"win": list(w), "v9": n, "chars": m}); st["total"] += n
            st["done"] = st["total"] >= STOP_AT
            json.dump(st, open(p, "w"), ensure_ascii=False, indent=1)     # 逐窗落盘（断点续跑）
            print(w, n, st["total"], flush=True)
        print(json.dumps({"total": st["total"], "n_win": len(st["windows"]), "done": st["done"]}))
    elif cmd in ("cov", "fp"):
        tag = sys.argv[2]
        os.environ.setdefault("LC_BASE", os.path.join(D, "corpus_h14base.json"))
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
        st = C.cov(os.path.join(D, "rewrite_map.json")) if cmd == "cov" else fp_r15(C)
        print(json.dumps({"tag": tag, "root": C.ROOT, **st, "wall_s": round(time.time() - t, 2), "llm": stats}, ensure_ascii=False))
    else:
        a = json.load(open(os.path.join(D, f"lc_sent_{sys.argv[2]}.json"))); b = json.load(open(os.path.join(D, f"lc_sent_{sys.argv[3]}.json")))
        assert set(a) == set(b)
        w = sum(a[k] == "exact" and b[k] != "exact" for k in a); l_ = sum(a[k] != "exact" and b[k] == "exact" for k in a)
        n = w + l_; k = min(w, l_)
        p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
        print(json.dumps({"A": sys.argv[2], "B": sys.argv[3], "n": len(a), "A_exact": sum(v == "exact" for v in a.values()),
                          "B_exact": sum(v == "exact" for v in b.values()),
                          "A_wrong": sum(v == "wrong" for v in a.values()), "B_wrong": sum(v == "wrong" for v in b.values()),
                          "win": w, "loss": l_, "p_mcnemar_exact": p}))
