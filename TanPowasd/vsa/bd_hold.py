# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""正文日期 BD · 新造保留集 crossproj-zh-bodydate（PREREG_body_date.md §3–§6）。零 LLM、零 key、确定性。
  python -X utf8 bd_hold.py --check     # §3 结构校验（只解析文本与金标，不跑任何检索 / 解绑，不 import BD 代码）
  python -X utf8 bd_hold.py --freeze    # 结构校验通过后写 release/SHA256SUMS.json 与本文件 HOLD_SHA（之后数据不得再改）
读数入口 --run 在 BD 实现提交时加入（本文件此版只含校验与冻结）。"""
import os, sys
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-X", "utf8"] + sys.argv)
import argparse, collections, datetime, hashlib, json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
import seg_real as SR  # noqa: E402
import real_v2 as RV  # noqa: E402
import hdc as H  # noqa: E402
import memory as M  # noqa: E402
import seg as SG  # noqa: E402

DS = HERE.parent / "datasets" / "crossproj-zh-bodydate" / "release"
NAME = "crossproj_zh_bodydate_hold.json"
HOLD_SHA = "1ee094411472e1cbf70a5d06a2d08d0f27c27cf1b84d5305ad9bae6b8a302e2f"
TIME_CATS = {"time_short": "a", "time_head": "b", "time_body": "c", "time_loginh": "d"}
N_CAT = {"fact_short": 20, "fact_long": 40, "time_short": 30, "time_head": 40, "time_body": 50, "time_loginh": 30}
RES = HERE / "results" / "bd_hold.json"
_MD = re.compile(r"(?<![\d年])(\d{1,2})月(\d{1,2})日")


def load():
    raw = (DS / NAME).read_bytes()
    return json.loads(raw)[0], hashlib.sha256(raw).hexdigest()


def _md(d):
    return f"{d.month}月{d.day}日"


def check():
    data, h = load()
    conv = data["conversation"]
    ids, texts, pay, elems, forced = SR.cp_elems(conv)
    k = [SG.n_items(p) for p in pay]
    long_ = {d: x > H.K_MAX for d, x in zip(ids, k)}
    sess_date = {}
    for key, v in conv.items():
        if re.fullmatch(r"session_\d+", key):
            for t in v:
                sess_date[t["dia_id"]] = datetime.date.fromisoformat(conv[f"{key}_date_time"][:10])
    txt = dict(zip(ids, texts))
    errs = []
    n_long = sum(long_.values())
    if n_long < 60:
        errs.append(f"长单元 {n_long} < 60")
    cnt = collections.Counter(q["category"] for q in data["qa"])
    if dict(cnt) != N_CAT:
        errs.append(f"题数分型 {dict(cnt)} ≠ {N_CAT}")
    other = [(r, rx) for r, rx in M.RE2_ZH if r != "zh-TM2-md"]
    for d, t in txt.items():                                   # 全文只允许「M月D日」一种时间表达（否则金标口径会被别的规则干扰）
        for r, rx in other:
            if rx.search(t):
                errs.append(f"{d} 出现非 M月D日 时间表达（{r}：{rx.search(t).group(0)}）")
    for d in data["doc_dia_ids"]:
        if not long_.get(d):
            errs.append(f"文档 {d} 不是长单元（{k[ids.index(d)]} 项）")
    for q in data["qa"]:
        c = q["category"]
        ev = q["evidence"][0]
        for g in q["evidence_groups"]:
            for x in g:
                if x not in txt:
                    errs.append(f"{q['qid']} 证据 {x} 不存在")
        if c not in TIME_CATS:
            if RV.ZH_TIME_Q.search(q["question"]):
                errs.append(f"{q['qid']} 检索题命中 ZH_TIME_Q")
            continue
        if not RV.ZH_TIME_Q.search(q["question"]):
            errs.append(f"{q['qid']} 时间题未命中 ZH_TIME_Q")
        gc = RV.canon_zh(q["answer"])
        if not (gc and gc.startswith("DATE:")):
            errs.append(f"{q['qid']} 金标不可解析：{q['answer']}"); continue
        gd = datetime.date.fromisoformat(gc[5:])
        t = txt.get(ev, "")
        want_long = TIME_CATS[c] != "a"
        if long_.get(ev) != want_long:
            errs.append(f"{q['qid']} 证据轮类型不符（{c}，长={long_.get(ev)}）")
        first = M.extract_time_v2(t, sess_date[ev])            # 单元首个日期（= L1 的单元 TIME 口径）
        first = first[0][1] if first else None
        if c == "time_head" and first != gc:
            errs.append(f"{q['qid']} (b) 金标 ≠ 单元首个日期（{first} vs {gc}）")
        if c == "time_body":
            pos = [m.start() for m in re.finditer(re.escape(_md(gd)), t)]
            mid = [p for p in pos if p > 0 and t[p - 1] not in "\n" and not re.search(r"(^|\n)(\d{1,3}\. )?$", t[:p])]
            if not mid or first == gc:
                errs.append(f"{q['qid']} (c) 金标不是句中日期或等于首个日期")
        if c == "time_loginh" and ("\n" + _md(gd) + "：") not in t:
            errs.append(f"{q['qid']} (d) 金标不是句首「M月D日：」日期")
        if c == "time_short" and _md(gd) not in t:
            errs.append(f"{q['qid']} (a) 金标日期不在证据轮")
    multi = 0
    for d in data["doc_dia_ids"]:
        multi += len({m.group(0) for m in _MD.finditer(txt[d])}) >= 2
    kinds = collections.Counter(data["doc_kind"].values())
    rep = {"sha256": h, "n_turns": len(ids), "n_long_units": n_long, "n_docs": len(data["doc_dia_ids"]), "doc_kinds": dict(kinds),
           "docs_multi_date": multi, "long_items_min_max": [min(x for x in k if x > H.K_MAX), max(k)], "short_max_items": max(x for x in k if x <= H.K_MAX),
           "K_MAX": H.K_MAX, "n_q": len(data["qa"]), "by_cat": dict(cnt),
           "time_body_doc_kind": dict(collections.Counter(q.get("doc_kind") for q in data["qa"] if q["category"] == "time_body")), "errors": errs}
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return rep


def freeze():
    rep = check()
    if rep["errors"]:
        raise SystemExit("结构校验未过，不冻结")
    (DS / "SHA256SUMS.json").write_text(json.dumps({NAME: rep["sha256"]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    src = (HERE / "bd_hold.py").read_text(encoding="utf-8")
    (HERE / "bd_hold.py").write_text(src.replace('HOLD_SHA = "待冻结"', f'HOLD_SHA = "{rep["sha256"]}"', 1), encoding="utf-8")
    print("已冻结", rep["sha256"])


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true"); g.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    if a.check:
        rep = check()
        raise SystemExit(1 if rep["errors"] else 0)
    return freeze()


if __name__ == "__main__":
    main()
