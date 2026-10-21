# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""PREREG_long §5 前置：只统计各候选保留集里叠加项数 > K_MAX 的写入单元数（不跑任何检索、不读任何题目 / 金标）。
  python -X utf8 long_count.py        # → results/long_count.json
单元口径与 seg_real.py 的 S0 写入完全相同：crossproj = 每轮（含 v2 角色），KMB / TMD = 每条（无角色）。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import hashlib, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
import seg_real as SR  # noqa: E402
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402


def stat(pays):
    n = [SG.n_items(p) for p in pays]
    return {"n_units": len(n), "n_over_kmax": sum(x > H.K_MAX for x in n), "max_items": max(n, default=0)}


def main():
    import lmeb_extra as LX
    res = {"K_MAX": H.K_MAX}
    raw = (SR.CP / "crossproj_zh_hold.json").read_bytes()
    h = hashlib.sha256(raw).hexdigest()
    if h != SR.CP_HOLD_SHA:
        raise SystemExit(f"存疑：crossproj hold sha256 不符（{h}），停")
    conv = json.loads(raw)[0]["conversation"]                     # 只取语料，不读 qa
    _, _, pay, _, _ = SR.cp_elems(conv)
    res["crossproj_hold"] = {"sha256": h, **stat(pay)}
    kroot = os.environ.get("KMB_DATA") or "/workspace/work/kmb"
    pays = []
    for c, it in LX.kmb(kroot, "hold"):
        pays += [(M.tokens(t), []) for t in it["turns"]]
    res["kmb_hold"] = stat(pays)
    troot = os.environ.get("TMD_DATA") or "/workspace/work/tmd"
    pays = []
    for sub, it in LX.tmd(troot):
        pays += [(M.tokens(t), []) for t in it["turns"]]
    res["tmd"] = stat(pays)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "long_count.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
