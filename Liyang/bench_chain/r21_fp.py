# -*- coding: utf-8 -*-
"""chain-r21 误登记读数（PREREG_R21 §3/§4）：R15/R16/R17/R20 已暴露区段（各自 sel.json 的窗）+ 小说奇数块 + R21 对抗集。
臂由 FP_ROOT（代码根）与 LINGSHU_NG_CHAIN_V21_FAM 决定；逐区段落盘、断点续跑。
  FP_ROOT=... python r21_fp.py <tag> [regions]   regions 缺省 adv,novel,r15,r16,r17,r20 → /workspace/work/ls/_r21/fp_<tag>.json"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
E2E = "/workspace/work/ls/hmb/e2e/corpus"
SEL = {"r15": "heldout_h11/r15_sel.json", "r16": "heldout_h12/r16_sel.json", "r17": "heldout_h13/r17_sel.json", "r20": "heldout_h16/r20_sel.json"}


def main():
    tag = sys.argv[1]
    regs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["adv", "novel", "r15", "r16", "r17", "r20"]
    root = os.environ.get("FP_ROOT") or os.path.dirname(HERE)
    sys.path.insert(0, root)
    import lingshu_ng.chain.ledger as LG
    assert os.path.realpath(LG.__file__).startswith(os.path.realpath(root)), LG.__file__
    P = f"/workspace/work/ls/_r21/fp_{tag}.json"
    res = json.load(open(P)) if os.path.exists(P) else {"tag": tag, "root": root, "fam": os.environ.get("LINGSHU_NG_CHAIN_V21_FAM", ""), "win": {}}
    t0 = time.time()

    def save():
        json.dump(res, open(P, "w"), ensure_ascii=False, indent=0)

    for rg in regs:
        if rg == "adv":
            if "adv" in res:
                continue
            adv = json.load(open(os.path.join(OUT, "r21_adv", "adv.json"), encoding="utf-8")); per = {}
            for cls, ss in adv.items():
                L = LG.Ledger()
                for j, s in enumerate(ss):
                    L.add_text(s, ref=f"r21adv#{cls}{j}")
                per[cls] = sum(r.op not in ("mention",) for r in L.recs)
            res["adv"] = per; save(); continue
        if rg == "novel":
            if "novel" in res:
                continue
            sys.path.insert(1, "/workspace/work/ls/wt-titans/bench_titans")
            from common import novel_chunks  # noqa
            L = LG.Ledger()
            for i, c in enumerate(novel_chunks()):
                if i % 2 == 1:
                    L.add_text(c["text"], ref=str(i))
            res["novel"] = sum(r.op not in ("mention",) for r in L.recs); save(); continue
        sel = json.load(open(os.path.join(OUT, SEL[rg])))
        for w in sel["windows"]:
            fn, a, b = w["win"]; k = f"{rg}|{fn}[{a}:{b}]"
            if k in res["win"]:
                continue
            if fn == "perltqa_zh":
                sys.path.insert(0, HERE)
                import r20_h16 as R20
                t = R20.plt_text()[a:b]
            else:
                t = open(os.path.join(E2E, fn), encoding="utf-8").read()[a:b]
            L = LG.Ledger()
            for j, para in enumerate(t.split("\n")):
                if para.strip():
                    L.add_text(para, ref=f"{fn}#{rg}_{a}_{j}")
            res["win"][k] = sum(r.op not in ("mention",) for r in L.recs); save()
            if time.time() - t0 > float(os.environ.get("FP_BUDGET", "100")):
                print("PARTIAL", file=sys.stderr); return
    tot = {rg: sum(v for k, v in res["win"].items() if k.startswith(rg + "|")) for rg in SEL}
    tot["novel"] = res.get("novel"); tot["adv"] = sum((res.get("adv") or {}).values())
    res["tot"] = tot; res["done"] = all(r in res or any(k.startswith(r + "|") for k in res["win"]) for r in regs); save()
    print(json.dumps({"tag": tag, "tot": tot, "adv": res.get("adv")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
