# -*- coding: utf-8 -*-
"""chain-r27 H23 单次评测件（PREREG_R27.md §5；cov 与 sign；误登记见 r21_fp.py；由 r21_h17.py 改目录）。
  python r20_h16.py sel                v19r 只计数选段（FP_ROOT=chain_v19r_snap）：按 (k, 文件名) 顺序逐窗建账，累计 ≥100 即停 → out/heldout_h17/r20_sel.json（只落条数）
  python r20_h16.py cov <tag>          H16 语料级抽取（LC_BASE=H16 换名语料；FP_ROOT 选代码根）→ lc_sent_<tag>.json
  python r20_h16.py fp <tag>           误登记：R20 窗口（r20_sel.json 里的窗）各自建账 + 小说奇数块
  python r20_h16.py sign a b           逐句配对 McNemar（精确二项；exact vs 非 exact）"""
import glob, hashlib, json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "out", "heldout_h23")
D17 = os.path.join(HERE, "out", "heldout_h13")
D16 = os.path.join(HERE, "out", "heldout_h12")
D15 = os.path.join(HERE, "out", "heldout_h11")
E2E = "/workspace/work/ls/hmb/e2e/corpus"
W = 200000
STOP_AT = 100
#: 学习能力理论讨论邀请.md 末 82,319 字已在 R14 读过
CAP = {"学习能力理论讨论邀请.md": 1858033}


PLT = "/workspace/work/ls/_shared/perltqa/perltmem_zh.json"   # sha256 5869ee39e944cf835af5c163c5213723bd2d30c44eb6705271031a644ee0ab7b
COVR = "/workspace/work/ls/wt-zh/bench_zh/covr/covr.json"
_CACHE = {}


def plt_text():
    """R20 误登记源（PREREG_R20 §3）：PerLTQA 中文版对话（CC BY-NC 4.0，只本地评测）。人物顺序 → dialogues 键序 → contents 时间戳键序；时间戳一行、每轮话语一行。"""
    if "plt" not in _CACHE:
        d = json.load(open(PLT, encoding="utf-8")); out = []
        for x in d:
            for _k, dl in (x.get("dialogues") or {}).items():
                for ts, turns in (dl.get("contents") or {}).items():
                    out.append(str(ts).strip())
                    out += [str(t).replace("\n", " ").strip() for t in turns if str(t).strip()]
        _CACHE["plt"] = "\n".join(out)
    return _CACHE["plt"]


def covr_text():
    """R19 新散文源 2：CovidRetrieval 段落（store 顺序、段内顺序、pid 去重，每段一行）。"""
    if "covr" not in _CACHE:
        d = json.load(open(COVR, encoding="utf-8")); seen = set(); out = []
        for st in d["stores"]:
            for p in st["docs"]:
                if p["pid"] in seen:
                    continue
                seen.add(p["pid"]); out.append(p["text"].replace("\n", " ").strip())
        _CACHE["covr"] = "\n".join(out)
    return _CACHE["covr"]


def windows():
    out = []
    for fn, f in (("perltqa_zh", plt_text),):
        n = len(f())
        out += [(fn, a, min(a + W, n)) for a in range(0, n, W)]
    return out


def _text(fn):
    return plt_text() if fn == "perltqa_zh" else covr_text()


class _ParaTimeout(Exception):
    pass


SKIPPED = []


def count_window(LG, fn, a, b):
    """逐段建账只记条数。评测件守卫（PREREG_R19 §8，各臂同规则）：单段建账 > PARA_TO 秒（速记体正则灾难回溯）⇒ 该段跳过并记录。"""
    import signal
    to = int(os.environ.get("PARA_TO", "15"))
    def _h(*_a):
        raise _ParaTimeout()
    old = signal.signal(signal.SIGALRM, _h)
    t = _text(fn)[a:b]
    L = LG.Ledger()
    try:
        for j, para in enumerate(t.split("\n")):
            if para.strip():
                signal.alarm(to)
                try:
                    L.add_text(para, ref=f"{fn}#r20_{a}_{j}")
                except _ParaTimeout:
                    SKIPPED.append(f"{fn}[{a}:{b}]#{j}")
                finally:
                    signal.alarm(0)
    finally:
        signal.signal(signal.SIGALRM, old)
    return sum(r.op not in ("mention",) for r in L.recs), len(t)


def fp_r15(C):
    """误登记：小说奇数块 + R20 各窗（逐窗落盘，断点续跑：out/heldout_h17/fp_part_<tag>.json）。"""
    LG = C.LG
    part = os.path.join(D, f"fp_part_{os.environ.get('FP_TAG', 'x')}.json")
    res = json.load(open(part)) if os.path.exists(part) else {"per": {}, "chars": {}}
    if "novel" not in res:
        sys.path.insert(1, "/workspace/work/ls/wt-titans/bench_titans")
        from common import novel_chunks  # noqa
        L = LG.Ledger()
        for i, c in enumerate(novel_chunks()):
            if i % 2 == 1:
                L.add_text(c["text"], ref=str(i))
        res["novel"] = sum(r.op not in ("mention",) for r in L.recs)
        json.dump(res, open(part, "w"), ensure_ascii=False)
    sel = json.load(open(os.path.join(D, "r20_sel.json")))
    for fn, a, b in [tuple(w["win"]) for w in sel["windows"]]:
        k = f"{fn}[{a}:{b}]"
        if k in res["per"]:
            continue
        n, m = count_window(LG, fn, a, b)
        res["per"][k] = n; res["chars"][k] = m
        res.setdefault("skipped", []).extend(SKIPPED); SKIPPED.clear()
        json.dump(res, open(part, "w"), ensure_ascii=False)
        print(k, n, file=sys.stderr, flush=True)
    per = res["per"]
    out = {"novel": res["novel"], "e2e": sum(per.values()), "e2e_per_win": per, "e2e_chars": sum(res["chars"].values())}
    out["perltqa_zh"] = sum(v for k, v in per.items() if k.startswith("perltqa_zh"))
    out["total"] = out["e2e"] + out["novel"]
    out["skipped_paras"] = res.get("skipped", [])
    return out


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "sel":
        sys.path.insert(0, HERE)
        import ledger_cov as C  # noqa: E402
        assert "chain_v19r_snap" in C.ROOT, C.ROOT   # PREREG_R20 §3：用基线臂 v19r 只计数选段
        p = os.path.join(D, "r20_sel.json")
        st = json.load(open(p)) if os.path.exists(p) else {"root": C.ROOT, "windows": [], "total": 0, "done": False}
        seen = {tuple(w["win"]) for w in st["windows"]}
        t0 = time.time()
        for w in windows():
            if st["done"] or time.time() - t0 > float(os.environ.get("SEL_BUDGET", "900")):
                break
            if w in seen:
                continue
            n, m = count_window(C.LG, *w)
            st["windows"].append({"win": list(w), "v19r": n, "chars": m}); st["total"] += n
            st["done"] = st["total"] >= STOP_AT
            json.dump(st, open(p, "w"), ensure_ascii=False, indent=1)     # 逐窗落盘（断点续跑）
            print(w, n, st["total"], flush=True)
        print(json.dumps({"total": st["total"], "n_win": len(st["windows"]), "done": st["done"]}))
    elif cmd in ("cov", "fp"):
        tag = sys.argv[2]
        os.environ["FP_TAG"] = tag
        os.environ.setdefault("LC_BASE", os.path.join(D, "corpus_h23base.json"))
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
