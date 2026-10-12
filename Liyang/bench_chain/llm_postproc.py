# -*- coding: utf-8 -*-
"""3d 甲方案：LLM 答卷统一后处理（零花费，不重新调用 LLM）。
对**全部臂**（ngchain v1 / ngchain_v5 / ng / bm25 / tc11_K / tc2_K）的已落盘答卷，判分前对 value 做同一个确定性变换，
**只在答卷自报 state=unresolved 时触发**（未决两值正是模板问题所在；第一版不设此门时把「sync(key, ttl)」这类函数签名也切坏了，已弃）：
  1) 去掉内容含汉字的括注（如「（尚未裁定）」）；2) 若含中文并列连接词（与/和/及/或/、），按第一个切开，
     value=第一项，其余项记 alt（只用于展示，不参与判分）。
判分函数仍是 probe_judge.value_correct（主值或 accept 命中算对），不改。原始答卷文件不改，读数写到 out/llm_metrics_pp.json。
  python llm_postproc.py"""
import json, os, re, sys
sys.argv = sys.argv[:1]
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_eval.py"), encoding="utf-8").read().split("if __name__")[0]
exec(_src)  # 复用 llm_eval 的 subset/judge/sign/目录口径  # noqa: S102

_PAREN = re.compile(r"[（(][^）)]*[\u4e00-\u9fff][^）)]*[）)]")
_SEP = re.compile(r"\s*(?:与|和|及|或|、)\s*")


def pp(a):
    v = a.get("value")
    if not isinstance(v, str) or a.get("state") != "unresolved":
        return a, False
    v2 = _PAREN.sub("", v).strip()
    parts = [p for p in _SEP.split(v2) if p]
    if len(parts) >= 2:
        v2 = parts[0]
    if v2 == v:
        return a, False
    b = dict(a); b["value"] = v2; b["_pp_alt"] = parts[1:]; b["_pp_raw"] = v
    return b, True


def judge_pp(d, t):
    rows, changed = {}, []
    for q in subset(t):
        a = load(os.path.join(d, q["qid"] + ".json"))
        if a is None:
            continue
        a, ch = pp(a)
        r = {"state_ok": float(PJ.eq(a.get("state"), q["answer"]["state"]))}
        if q["answer"]["value"] is not None:
            r["value_ok"] = float(PJ.value_correct(a, q))
            r["stale" if t == "现值" else "future"] = float(PJ.stale_confused(a, q) if t == "现值" else PJ.future_confused(a, q))
        if ch:
            changed.append({"qid": q["qid"], "raw": a["_pp_raw"], "pp": a["value"], "value_ok": r.get("value_ok")})
        rows[q["qid"]] = r
    return rows, changed


dirs = {a: {t: os.path.join(D, "ans", a) for t in ("现值", "历史")} for a in SRC}
for a, ts in OLD.items():
    dirs.setdefault(a, {}).update(ts)
out = {"metrics": {}, "changed": {}, "paired_sign": {}}
per_raw, per_pp = {}, {}
for arm, ts in dirs.items():
    for t, d in ts.items():
        raw = judge(d, t); new, ch = judge_pp(d, t)
        if not raw:
            continue
        per_raw[(arm, t)], per_pp[(arm, t)] = raw, new
        hv = lambda R: [r for r in R.values() if "value_ok" in r]  # noqa: E731
        out["metrics"][f"{arm}.{t}"] = {"n_value": len(hv(raw)), "value_raw": round(sum(r["value_ok"] for r in hv(raw)) / max(1, len(hv(raw))), 4),
                                         "value_pp": round(sum(r["value_ok"] for r in hv(new)) / max(1, len(hv(new))), 4),
                                         "state_raw": round(sum(r["state_ok"] for r in raw.values()) / len(raw), 4),
                                         "state_pp": round(sum(r["state_ok"] for r in new.values()) / len(new), 4), "n_changed": len(ch)}
        out["changed"][f"{arm}.{t}"] = ch
for t in ("现值", "历史"):
    for a in ("ngchain", "ngchain_v5"):
        for b in ("ng", "bm25", "tc11_K", "tc2_K"):
            if (a, t) in per_pp and (b, t) in per_pp:
                A, B = per_pp[(a, t)], per_pp[(b, t)]
                qs = [q for q in A if q in B and "value_ok" in A[q] and "value_ok" in B[q]]
                out["paired_sign"][f"{a}-{b}.{t}.value_ok(pp)"] = sign([A[q]["value_ok"] for q in qs], [B[q]["value_ok"] for q in qs])
dump(os.path.join(OUT, "llm_metrics_pp.json"), out, indent=1)
for k, v in out["metrics"].items():
    print(k, v)
for k, v in out["paired_sign"].items():
    print(k, v)
print("cost unchanged", round(cost(), 4))
