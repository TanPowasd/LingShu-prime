# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""长单元分块 L1 · 真实集读数（PREREG_long §3–§5）。零 LLM、零 key、确定性。
  python -X utf8 long_real.py --set locomo|hive|perltqa|crossproj [--budget-secs S]   # dev：S0 / L1 的 E1/E2/E3，逐单元缓存可续跑
  python -X utf8 long_real.py --summary                                               # → results/long_dev.json/.md（含 §4 门槛判定）
数据加载、元素构造、E1/E2 计分全部复用 seg_real.py 的 run_*（同一口径）；只把其中的臂表与 rank_unit 换成 S0/L1（模块属性替换，不改 seg_real.py）。
保留集：crossproj hold 无长单元（L1 ≡ S0）按 §5 不跑；KMB / TMD 因 reuse 阈值状态缺失按 §5 跳过，本脚本不提供保留集入口。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, json, pathlib, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
import seg_real as SR  # noqa: E402
import real_v2 as RV  # noqa: E402
import hdc as H  # noqa: E402
import seg as SG  # noqa: E402

ARMS = ["S0", "L1"]
SETS = SR.SETS


def rank_unit(owner_payload, elems, forced, queries, arms=ARMS, texts=None, need_mem=False):
    """与 seg_real.rank_unit 同签名：S0 = 逐单元；L1 = 短单元原样 + 长单元按 K_MAX 顺序装块（seg.segment_long）。"""
    m0 = SG.memory_from(owner_payload)
    if texts is not None:
        m0.texts = list(texts)
    s0 = m0.search_many(queries, beta=SR.BETA)
    n = len(owner_payload)
    orders, e3, mems = {"S0": [SR.order0(x) for x in s0]}, {}, {"S0": m0}
    e3["S0"] = {"n_units": n, "n_rejected": sum(SG.n_items(p) > H.K_MAX for p in owner_payload),
                "max_items": max((SG.n_items(p) for p in owner_payload), default=0)}
    if "L1" in arms:
        el2, segs, why, rows, n_long = SG.segment_long(owner_payload, elems)
        assert max((SG.n_items(r) for r in rows), default=0) <= H.K_MAX, "I3：L1 任何痕迹 ≤ K_MAX"
        ml = SG.memory_from(rows)
        sl = ml.search_many(queries, beta=SR.BETA)
        orders["L1"] = [SG.expand(b, SG.expand_segs(segs, why), el2, a, n) for a, b in zip(s0, sl)]
        if n_long == 0:                                        # PREREG_long §3：无长单元 ⇒ 必须逐位 ≡ S0（运行时断言，不静默）
            assert rows == [(list(a), list(b)) for a, b in owner_payload] and orders["L1"] == orders["S0"], "无长单元却 L1 ≠ S0"
        e3["L1"] = {"n_units": n, "n_long": n_long, "n_traces": len(segs), "n_chunks": sum(w in ("chunk", "kmax") for w in why),
                    "max_items": max((SG.n_items(r) for r in rows), default=0), "n_rejected": 0}
        if need_mem:
            mems["L1"] = SG.SegView(ml, segs, el2, texts if texts is not None else [""] * n)
    return orders, e3, mems


def install():
    """把 seg_real 的 run_* 指向 S0/L1（其函数在调用时按模块全局查找 ARMS / rank_unit）。"""
    SR.ARMS = ARMS
    SR.rank_unit = rank_unit


def summary():
    res = {"prereg": "PREREG_long.md", "E1": {}, "E2": {}, "E3": {}}
    for s in SETS:
        p = SR.OUT / "runs" / "dev" / f"long_{s}.json"
        if not p.exists():
            raise SystemExit(f"缺 dev 缓存：{p}（先跑 --set {s}）")
        D = json.loads(p.read_text(encoding="utf-8"))
        qs = sorted(D["per"])
        v = {a: [D["per"][q][a] for q in qs] for a in ARMS}
        res["E1"][s] = {"n": len(qs), "mean": {a: float(np.mean(v[a])) for a in ARMS}, "L1_vs_S0": SR.sign(v["L1"], v["S0"]),
                        "identical": all(abs(x - y) < 1e-15 for x, y in zip(v["L1"], v["S0"]))}
        if D.get("e2"):
            e = D["e2"]; eq = sorted(e)
            ok = {a: [bool(e[q][a]["ok"]) for q in eq] for a in ARMS}
            mc = RV.mcn(ok["L1"], ok["S0"])
            res["E2"][s] = {"n": len(eq), "acc": {a: sum(ok[a]) / len(eq) for a in ARMS}, "L1_vs_S0": mc,
                            "identical_pred": all(e[q]["L1"]["pred"] == e[q]["S0"]["pred"] for q in eq)}
        us = list(D["e3"].values())
        res["E3"][s] = {"S0": {"n_units": sum(x["S0"]["n_units"] for x in us), "n_rejected": sum(x["S0"]["n_rejected"] for x in us),
                               "max_items": max(x["S0"]["max_items"] for x in us)},
                        "L1": {k: (max if k == "max_items" else sum)(x["L1"][k] for x in us) for k in ("n_long", "n_traces", "n_chunks", "max_items", "n_rejected")}}
    sig = lambda c, w, l: c["p"] < .05 and w > l
    reg, up = [], []
    for s, e in res["E1"].items():
        c = e["L1_vs_S0"]
        if sig(c, c["loss"], c["win"]):
            reg.append(f"E1:{s}")
        if sig(c, c["win"], c["loss"]):
            up.append(f"E1:{s}")
    for s, e in res["E2"].items():
        c = e["L1_vs_S0"]
        if sig(c, c["loss"], c["win"]):
            reg.append(f"E2:{s}")
        if sig(c, c["win"], c["loss"]):
            up.append(f"E2:{s}")
    res["gate"] = {"regress": reg, "up": up, "pass": (not reg) and bool(up)}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "long_dev.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = render(res)
    (HERE / "results" / "long_dev.md").write_text(md, encoding="utf-8")
    print(md)


def render(res):
    f = lambda x: f"{x:.4f}"
    md = ["# VSA 长单元分块 L1 · dev 读数（PREREG_long §3–§4）", "", "## E1 VSA 检索 r@10", "",
          "| 集 | 题数 | S0 | L1 | L1 vs S0 胜/负/平 | p | 逐题全等 |", "|---|---:|---:|---:|---|---:|---|"]
    for s, e in res["E1"].items():
        c = e["L1_vs_S0"]
        md.append(f"| {s} | {e['n']} | {f(e['mean']['S0'])} | {f(e['mean']['L1'])} | {c['win']}/{c['loss']}/{c['tie']} | {c['p']:.3g} | {'是' if e['identical'] else '否'} |")
    md += ["", "## E2 时间题解绑", "", "| 集 | 题数 | S0 | L1 | McNemar L1 胜/负 | 预测全等 |", "|---|---:|---:|---:|---|---|"]
    for s, e in res["E2"].items():
        md.append(f"| {s} | {e['n']} | {f(e['acc']['S0'])} | {f(e['acc']['L1'])} | {e['L1_vs_S0']['win']}/{e['L1_vs_S0']['loss']} p={e['L1_vs_S0']['p']:.3g} | {'是' if e['identical_pred'] else '否'} |")
    md += ["", "## E3 描述性", "", "| 集 | 单元 | S0 拒写 | S0 最大项数 | L1 长单元 | L1 痕迹数 | L1 块数 | L1 最大项数 | L1 拒写 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s, e in res["E3"].items():
        a, b = e["S0"], e["L1"]
        md.append(f"| {s} | {a['n_units']} | {a['n_rejected']} | {a['max_items']} | {b['n_long']} | {b['n_traces']} | {b['n_chunks']} | {b['max_items']} | {b['n_rejected']} |")
    g = res["gate"]
    md += ["", "## §4 门槛", "", f"- 显著倒退：{g['regress'] or '无'}；显著上升：{g['up'] or '无'}。",
           f"- 判定：**{'dev 合格' if g['pass'] else 'dev 不合格'}**（保留集见 PREREG_long §5）。"]
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=SETS); ap.add_argument("--budget-secs", type=float); ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        return summary()
    install()
    t0 = time.time()
    c = SR.Cache(f"long_{a.set}")
    done = {"locomo": SR.run_locomo, "hive": SR.run_hive, "perltqa": SR.run_perltqa, "crossproj": SR.run_crossproj}[a.set](c, a.budget_secs, t0)
    c.save()
    print(a.set, "完成" if done else "预算到，下次同命令续跑", f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
