# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""对话体新保留集 crossproj-zh-dialog v0.1 · 结构校验与冻结（正文日期 v0.2 用；早于 PREREG_body_date_v0.2 与任何 v0.2 实现 / 读数）。
零 LLM、零 key、确定性。
  python -X utf8 dialog_hold.py --check     # 结构校验：只解析文本与金标（切句、句内时间、项数），不跑任何检索 / 解绑，不 import 任何 BD 代码
  python -X utf8 dialog_hold.py --freeze    # 校验通过后写 release/SHA256SUMS.json 与本文件 HOLD_SHA（之后数据不得再改）
口径 = PerLTQA 口径（seg_real.run_perltqa）：单元载荷 (tokens(原文), zh_time(原文))，长单元按句切、句角色 = zh_time(句)。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, hashlib, json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
import seg_real as SR  # noqa: E402
import real_v2 as RV  # noqa: E402
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402

DS = HERE.parent / "datasets" / "crossproj-zh-dialog" / "release"
NAME = "crossproj_zh_dialog_hold.json"
HOLD_SHA = "eac6a3d7dbaf14fdff5146f7b0e71b6b1ea679dd4dbb38aa44bd41885e6a6904"
TIME_CATS = ("first_plain", "first_interf", "body_echo", "body_plain", "short_time")
N_CAT = {"first_plain": 24, "first_interf": 28, "body_echo": 40, "body_plain": 20, "short_time": 32, "fact": 32}
_QFORM = re.compile(r"[？?]\s*$|[吗呢么]\s*[？?。！!]?\s*$")          # 问句形（数据卡定义；独立于任何实现）
_HDR = re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日 \d{2}:\d{2}:\d{2}$")


def load():
    raw = (DS / NAME).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def sent_times(text):
    """→ [(句, TIME 填充 | None)]（seg.split_sents 切句；zh_time 取句内最先出现的日期）。"""
    out = []
    for s in SG.split_sents(text):
        t = SR.zh_time(s)
        out.append((s, t[0][1] if t else None))
    return out


def check():
    data, h = load()
    errs = []
    stat = collections.Counter()
    items = {"long": [], "short": []}
    multi_date = 0
    for bn, b in data["banks"].items():
        for u, (t, kd) in enumerate(zip(b["texts"], b["unit_kind"])):
            k = SG.n_items((M.tokens(t), SR.zh_time(t)))
            items[kd].append(k)
            if (k > H.K_MAX) != (kd == "long"):
                errs.append(f"{bn}#{u} 单元类型 {kd} 与项数 {k} 不符（K_MAX={H.K_MAX}）")
            lines = t.split("\n")
            if not _HDR.match(lines[0]):
                errs.append(f"{bn}#{u} 首行不是时间戳")
            st = sent_times(t)
            fills = [f for _, f in st if f]
            for s, f in st:
                if f and not (f.startswith("DATE:") or f.startswith("YEAR:")):
                    errs.append(f"{bn}#{u} 出现 DATE/YEAR 以外的时间表达：{s}")
            if kd == "long":
                multi_date += len(set(fills)) >= 2
                if len(set(fills)) < 2:
                    errs.append(f"{bn}#{u} 长单元不同日期 < 2")
                yrs = [f[5:9] for f in fills]
                if len(set(yrs)) != len(yrs):
                    errs.append(f"{bn}#{u} 单元内日期年份重复（金标在年粒度上须唯一）")
                for ln in lines[1:]:
                    if not re.match(r"^(AI助手|" + re.escape(bn) + r"):\S", ln):
                        errs.append(f"{bn}#{u} 行不是「说话人:话语」：{ln[:20]}")
        hd = [sent_times(t)[0][1] for t in b["texts"]]
        if len(set(hd)) != len(hd):
            errs.append(f"{bn} 库内单元日期重复")
    cnt = collections.Counter(q["category"] for q in data["qa"])
    if dict(cnt) != N_CAT:
        errs.append(f"题数分型 {dict(cnt)} ≠ {N_CAT}")
    for q in data["qa"]:
        b = data["banks"][q["bank"]]
        c, ev = q["category"], q["evidence"][0]
        t, kd = b["texts"][ev], b["unit_kind"][ev]
        if c not in TIME_CATS:
            if RV.ZH_TIME_Q.search(q["question"]):
                errs.append(f"{q['qid']} 检索题命中 ZH_TIME_Q")
            hits = [u for u, x in enumerate(b["texts"]) if q["answer"] in x]
            if hits != [ev]:
                errs.append(f"{q['qid']} 取值不唯一出现在证据单元：{hits}")
            continue
        if not RV.ZH_TIME_Q.search(q["question"]):
            errs.append(f"{q['qid']} 时间题未命中 ZH_TIME_Q")
        gc = RV.canon_zh(q["answer"])
        if not gc:
            errs.append(f"{q['qid']} 金标不可解析：{q['answer']}"); continue
        st = sent_times(t)
        head = st[0][1]
        gran = lambda f: RV.granularity(q["question"], f)
        same = [k for k, (_, f) in enumerate(st) if f and gran(f) == gc]
        if c in ("first_plain", "first_interf", "short_time"):
            if kd != ("short" if c == "short_time" else "long"):
                errs.append(f"{q['qid']} 证据单元类型不符（{c}，{kd}）")
            if c != "short_time" and (q["fact"]["v"] not in t or f"{q['fact']['e']}的{q['fact']['k']}" not in q["question"]):
                errs.append(f"{q['qid']} 首日期题事实不在证据单元")
            if gran(head) != gc or same != [0]:
                errs.append(f"{q['qid']} 首日期题金标须 = 首行日期且单元内唯一（{same}）")
            if c == "first_interf":
                du = q["decoy_unit"]
                dt_ = b["texts"][du]
                f = q["fact"]
                if du == ev or b["unit_kind"][du] != "long":
                    errs.append(f"{q['qid']} 干扰单元须为另一长单元")
                if f"{f['e']}的{f['k']}" not in dt_ or f["v"] in dt_:
                    errs.append(f"{q['qid']} 干扰单元须提到同一对象与属性、且不含取值")
                sd = sent_times(dt_)
                dd = {x for _, x in sd[:max(3, len(sd) // 3)] if x}
                if len(dd) < 2:
                    errs.append(f"{q['qid']} 干扰单元前三分之一日期 < 2")
                stat["interf_decoy_ok"] += 1
        else:
            if kd != "long":
                errs.append(f"{q['qid']} 正文日期题证据须为长单元")
            if gran(head) == gc or len(same) != 1 or same[0] == 0:
                errs.append(f"{q['qid']} 正文日期金标须在非首句出现、≠ 首日期且单元内唯一（{same}）")
            if c == "body_echo":
                e = q["echo"]
                ln = f"AI助手:{e}"
                lines = t.split("\n")
                if ln not in lines:
                    errs.append(f"{q['qid']} 回声句不在证据单元"); continue
                i = lines.index(ln)
                if SR.zh_time(e) or not _QFORM.search(e):
                    errs.append(f"{q['qid']} 回声句须问句形且无日期")
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                if not (nxt.startswith(q["bank"] + ":") and any(f and gran(f) == gc for _, f in sent_times(nxt))):
                    errs.append(f"{q['qid']} 回声句的下一行须为用户回答且含金标日期")
                stat[f"echo_{q['echo_style']}"] += 1
            stat["head_form" if q.get("head_form") else "mid_form"] += 1
    rep = {"sha256": h, "n_banks": len(data["banks"]), "n_units": sum(len(b["texts"]) for b in data["banks"].values()),
           "n_long": len(items["long"]), "n_short": len(items["short"]), "long_items_min_max": [min(items["long"]), max(items["long"])],
           "short_items_max": max(items["short"]), "K_MAX": H.K_MAX, "long_multi_date": multi_date, "n_q": len(data["qa"]), "by_cat": dict(cnt),
           "stat": dict(stat), "errors": errs}
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return rep


def freeze():
    rep = check()
    if rep["errors"]:
        raise SystemExit("结构校验未过，不冻结")
    gen = (DS.parent / "gen.py").read_bytes()
    (DS / "SHA256SUMS.json").write_text(json.dumps({NAME: rep["sha256"], "gen.py": hashlib.sha256(gen).hexdigest()}, ensure_ascii=False, indent=1) + "\n",
                                        encoding="utf-8")
    src = (HERE / "dialog_hold.py").read_text(encoding="utf-8")
    (HERE / "dialog_hold.py").write_text(src.replace('HOLD_SHA = "待冻结"', f'HOLD_SHA = "{rep["sha256"]}"', 1), encoding="utf-8")
    print("已冻结", rep["sha256"])


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true"); g.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    if a.check:
        rep = check()
        raise SystemExit(1 if rep["errors"] else 0)
    freeze()


if __name__ == "__main__":
    main()
