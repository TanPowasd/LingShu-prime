"""判分器 v2 候选 · 考卷 A（hmb 长文理解主轮）。

原链路（harness/examA.py + 上游 hmb/judge.py、semantic.py）一律不改，本模块在其外层包一层：

1. 规则层 v2（rule_v2）：上游 judge() 原样调用，但"禁编造轴"换成 axis_fabrication_v2：
   - 上游触发词照用；否定豁免除上游的前向子句窗外，**加引述豁免**：命中片段整段落在引号（「」『』“”""）内＝引述他人原话，
     不是作答者的断言（修 q030：答案键要点引述"就早该加上记忆屏蔽技术"被卡片自己的反模式正则误杀）；
   - **加登记编造说法的断言式触发**：卡片 anti_patterns 的 claim 若为「把X说成Y」，答案同一句里先后出现 X 与 Y、
     且该句无否定词、不在引号内 ⇒ 判编造。（局限：只抓近乎逐字的断言；与门槛 2 夹具同一模板，夹具上的检出率偏乐观，
     报告单列判官层检出率。）
2. 路由 v2：规则层 pass（含无降级）**不再直接放行**——完整条件、answerable 题一律再送语义判官（含实体/数字的题是其子集）；
   退化条件与 answerable:false 题仍按上游（那里正确行为是"承认不确定"，覆盖率不是判据）。
3. 语义判官 v2：JC＝上游覆盖率判官（semantic-v0.1 原提示词，可重放原批次 judge-1 判词）；JF＝事实核查判官（新提示词，
   先读答案、再读参照与登记错误说法），给逐点覆盖（span 机械校验）＋实体冲突对＋编造断言（均机械校验）。
   覆盖率＝两判官均值（上游 §四）；**实体/编造轴有任一可证条目 ⇒ fail**（与覆盖率分开记）。
   捷径（不改结果）：JC 覆盖率 < 0.4 时均值不可能 ≥ 0.7，JF 不调用（记 skip）。
4. 上岗考 v2：上游语义锚 16 ＋ 依据锚 8（不变）＋ 定向错误锚（替换实体、断言登记编造说法）＋ 合成金丝雀行（批内每题 3 行，
   同一计分循环、行号不透明）＋ 规则层"删依据"金丝雀（批内每题：要点原文＋空依据 ⇒ 必须结构违规）。
"""
from __future__ import annotations
import json, random, re

from harness import examA as A
from harness.examB import extract_json
from harness.judge_v2.common import (V2_VERSION, norm, opaque, verify_pair, agreement, CallCache, run_jobs, hard_conflict)

PASS = 0.7
SKIP_BELOW = 0.4
QUOTE_RE = re.compile(r"「([^」]*)」|『([^』]*)』|“([^”]*)”|\"([^\"]*)\"")
AP_RE = re.compile(r"^把(.+?)(?:说成|当成|写成|读成|理解成|解释成|当作)(.+)$")
SENT_SPLIT = re.compile(r"[。；;！!？?\n]")


def _quoted(text):
    return [norm(next(g for g in m.groups() if g is not None)) for m in QUOTE_RE.finditer(text or "")]


def axis_fabrication_v2(card, resp):
    J, _ = A.upstream()
    text = resp.get("answer") or resp.get("conclusion") or ""
    quotes = [q for q in _quoted(text) if q]
    hits, exempt = [], []
    for ap in card.get("anti_patterns") or []:
        if isinstance(ap, dict):
            claim, trigs = ap.get("claim", ""), ap.get("triggers") or []
        else:
            claim, trigs = str(ap), [str(ap)]
        hit = None
        for t in trigs:
            pat, frag = J.match_any_frag(text, [t])
            if not pat:
                continue
            if J.negated(text, frag):
                exempt.append({"claim": claim[:40], "trigger": t, "why": "上游否定豁免"}); continue
            if frag and any(frag in q for q in quotes):
                exempt.append({"claim": claim[:40], "trigger": t, "why": "v2 引述豁免（命中片段在引号内）"}); continue
            hit = f"{claim} ← 触发词「{t}」"; break
        if not hit:
            mm = AP_RE.match(claim.split("（")[0].strip())
            if mm:
                x, y = norm(mm.group(1)), norm(mm.group(2))
                if x and y:
                    for s in SENT_SPLIT.split(text):
                        ns = norm(s)
                        if x in ns and y in ns and ns.find(x) < ns.rfind(y) \
                                and not any(norm(m) in ns for m in J.NEG_MARKERS) and not any(ns in q or (x in q and y in q) for q in quotes):
                            hit = f"{claim} ← v2 断言式触发（同句先后出现「{mm.group(1)}」「{mm.group(2)}」）"; break
        if hit:
            hits.append(hit)
    return {"pass": not hits, "hits": hits, "exempt": exempt}


def rule_v2(card, resp, idx):
    """上游 judge()（去掉 anti_patterns 后调用）＋ v2 禁编造轴。返回与上游同形的结果字典。"""
    J, _ = A.upstream()
    c0 = dict(card); c0.pop("anti_patterns", None)
    res = J.judge(c0, resp, idx)
    fab = axis_fabrication_v2(card, resp)
    res["axes"]["fabrication"] = fab
    res["axes"]["fabrication_upstream"] = J.axis_fabrication(card, resp) if card.get("anti_patterns") else {"pass": True, "na": True}
    if not fab["pass"]:
        res["struct_bad"] = list(res["struct_bad"]) + ["fabrication"]
        res["verdict"] = "fail"
    return res


def route_v2(card, resp, idx):
    res = rule_v2(card, resp, idx)
    if res["struct_bad"] or res["empty"]:
        return "fail_struct", res
    honesty_mode = resp.get("condition", "full") != "full" or card.get("answerable", True) is False
    if res["verdict"] == "pass" and not res.get("downgrade"):
        return ("pass_rule" if honesty_mode else "sem_from_pass"), res
    if res.get("downgrade"):
        return "cite", res
    return "sem", res


# ---------------- JF：事实核查判官 ----------------
FACT_PROMPT = """你是「记忆理解评测库」的事实核查判官（fact-check judge v2）。另一名判官会从"要点覆盖"角度独立判同一份答案，你看不到它的判断；你从**另一个角度**核查：答案里的人物、名称、数字、对象、因果是否与参照一致，有没有编造。

请按顺序做三件事：
A. 逐条要点判 strict / paraphrase / miss，并给出答案中**原样复制**的支撑片段 span（≤60 字；miss 给空串）。只看意思；但主体/人物/数字/对象被替换、归属错误、或作出相反断言 ⇒ miss。
B. 列出 conflicts：答案把参照里的**具体人物/名称/数字/对象**换成了别的（同一位置给了不同的值）。ref 逐字摘自参照，ans 逐字摘自答案。同义改写、简称、上下位具体化**不算**冲突；答案没提到 ≠ 冲突。
C. 列出 fabrications：答案中**与参照矛盾**的断言，或命中下面「登记的错误说法」的断言。span 逐字复制答案原文；type 填 "E编号" 或 "矛盾"。参照没提到但不矛盾的额外细节**不算**编造；以否定、引述、转述他人原话的方式提到错误说法（如「不能据此推出…」「老人抱怨说『…』」）**不算**。

纪律：只依据给定材料，不用自己的知识；没有就给空列表。
输出：**只输出一个 JSON 对象**，不要其他文字：
{"points": [{"id": "...", "verdict": "strict|paraphrase|miss", "span": "..."}], "conflicts": [{"ref": "...", "ans": "..."}], "fabrications": [{"span": "...", "type": "E1|矛盾", "why": "≤30字"}]}"""
FACT_MAX_TOKENS = 1500


def _ref_text(card):
    _, S = A.upstream()
    pts = S._points_of(card, card.get("qid"))
    parts = [card.get("question", ""), card.get("necessary_conclusion") or ""] + [p.get("point", "") for p in pts] + \
            [str(x) for x in (card.get("acceptable_surface_forms") or [])]
    return "\n".join(parts)


def _key_text(card):
    """答案键的"标准答案"文本（结论＋必答要点），供确定性替换检测对齐用。"""
    pts = A._pts_text(card, card.get("qid"))
    concl = card.get("necessary_conclusion") or ""
    return (concl + "。" + pts) if concl else pts


def _errors(card):
    out = []
    for ap in card.get("anti_patterns") or []:
        out.append((ap.get("claim", "") if isinstance(ap, dict) else str(ap)).strip())
    return [e for e in out if e]


def fact_request(card, qid, answer):
    _, S = A.upstream()
    pts = S._points_of(card, qid)
    L = [FACT_PROMPT, "", "---", "", "## 被测答案（先读）", "", answer if answer else "（空）", "", "## 参照", "",
         f"问题：{card.get('question','')}", f"参照结论：{card.get('necessary_conclusion') or '（本题为开放题，以要点为准）'}", "", "要点清单："]
    for p in pts:
        tag = "required" if p.get("required") else "加分项"
        L.append(f"- {p.get('id')}（{tag}，权重 {p.get('weight', 1)}）：{p.get('point','')}")
    errs = _errors(card)
    L += ["", "登记的错误说法（题库作者事先登记的常见编造/误读）："] + ([f"- E{i}：{e}" for i, e in enumerate(errs, 1)] or ["- （无）"])
    return "\n".join(L)


def fact_finalize(card, qid, answer, raw):
    J, S = A.upstream()
    jr = extract_json(raw or "")
    if not isinstance(jr, dict):
        return {"ok": False, "score": 0.0, "conflicts": [], "fabrications": [], "rejected": [], "error": "非 JSON"}
    pts = S._points_of(card, qid)
    weights = {p.get("id"): float(p.get("weight", 1) or 1) for p in pts}
    required = [p.get("id") for p in pts if p.get("required")]
    verdicts, invalid = {}, []
    for p in jr.get("points") or []:
        if not isinstance(p, dict) or p.get("id") not in weights:
            continue
        v = (p.get("verdict") or "").strip().lower()
        v = v if v in ("strict", "paraphrase", "miss") else "miss"
        span = (p.get("span") or "").strip()
        if v != "miss" and (not span or J.norm(span) not in J.norm(answer)):
            invalid.append(p.get("id")); v = "miss"
        verdicts[p.get("id")] = v
    got = sum(weights[k] * (S.FULL if v == "strict" else S.PARA if v == "paraphrase" else 0.0) for k, v in verdicts.items() if k in required)
    den = sum(weights[k] for k in required) or 1.0
    ref = _ref_text(card)
    conf, fab, rej = [], [], []
    for c in jr.get("conflicts") or []:
        if not isinstance(c, dict):
            continue
        ok, why = verify_pair(str(c.get("ref", "")), str(c.get("ans", "")), ref, answer)
        (conf if ok else rej).append({"kind": "conflict", "ref": str(c.get("ref", ""))[:80], "ans": str(c.get("ans", ""))[:80], **({} if ok else {"rejected": why})})
    nerr = len(_errors(card))
    for f in jr.get("fabrications") or []:
        if not isinstance(f, dict):
            continue
        span, typ = str(f.get("span", "")).strip(), str(f.get("type", "")).strip().upper()
        good = len(norm(span)) >= 4 and norm(span) in norm(answer)
        m = re.fullmatch(r"E(\d+)", typ)
        good = good and ((m is not None and 1 <= int(m.group(1)) <= nerr) or "矛盾" in str(f.get("type", "")))
        # 引述豁免：片段整段在答案的引号内 ⇒ 不算（与规则层同口径）
        if good and any(norm(span) in q for q in _quoted(answer) if q):
            good = False
        (fab if good else rej).append({"kind": "fabrication", "span": span[:80], "type": str(f.get("type", ""))[:10],
                                       "why": str(f.get("why", ""))[:60], **({} if good else {"rejected": "片段不可证/类型不合法/在引号内"})})
    return {"ok": True, "score": round(got / den, 3), "strict": [k for k, v in verdicts.items() if v == "strict"],
            "paraphrase": [k for k, v in verdicts.items() if v == "paraphrase"], "span_invalid": invalid,
            "conflicts": conf, "fabrications": fab, "rejected": rej}


def score_row_a(sC, sF, cons_bad: bool) -> tuple[str, float]:
    """唯一的计分函数（考卷 A 语义路）：覆盖率均值 ≥ 0.7 且实体/编造轴无可证条目 ⇒ pass。"""
    mean = (sC + sF) / 2
    if cons_bad:
        return "fail", mean
    return ("pass" if mean >= PASS else "fail"), mean


# ---------------- 定向错误锚 ----------------
def build_targeted_anchors(std_anchors):
    from tools.gates.fixtures import swap_A
    C = A.cards()
    out = []
    for a in std_anchors:
        if a["task"] != "sem":
            continue
        q = a["qid"]; c = C[q]
        own = A._pts_text(c, q)
        if a["expect"] == "pass":
            sw = swap_A(own)
            if sw != own:
                out.append({"aid": f"T-swap{q}", "task": "sem", "qid": q, "answer": sw, "expect": "fail", "kind": "swap"})
        aps = c.get("anti_patterns") or []
        if aps:
            ap = (aps[0] if isinstance(aps[0], str) else aps[0].get("claim", "")).split("（")[0]
            mm = AP_RE.match(ap)
            claim = f"{mm.group(1)}是{mm.group(2)}" if mm else ap
            out.append({"aid": f"T-fab{q}", "task": "sem", "qid": q, "answer": own + "。另外，" + claim + "。", "expect": "fail", "kind": "fabricate"})
    return out


CANARY = [(0.0, 0.0, False, "fail"), (1.0, 1.0, True, "fail"), (1.0, 1.0, False, "pass")]


def judge_batch_a_v2(items, rec, *, make_client, batch_tag, cache_path, jc_replay=None, cite_replay=None,
                     concurrency=4, budget=None, counter=None, dry=False):
    """items: [{"key","qid","resp","route","res_brief"}]（route 来自 route_v2）
    jc_replay: {key: fin}  覆盖判官 JC 的已有判词（sem 任务、原批次 judge-1；fin 含 score）
    cite_replay: {key: (l1, l2)}  依据契合判官（原提示词两实例）已有判词；缺则新调。"""
    C = A.cards()
    jc_replay = jc_replay or {}; cite_replay = cite_replay or {}
    std = A.build_anchors()
    tgt = build_targeted_anchors(std)
    cache = CallCache(cache_path)
    iC, iF, iL1, iL2 = f"{batch_tag}#JC", f"{batch_tag}#JF", f"{batch_tag}#L2-1", f"{batch_tag}#L2-2"
    sem_items = [it for it in items if it["route"] in ("sem", "sem_from_pass", "cite")]
    need_cite = any(it["route"] == "cite" for it in items)
    sem_anc = [a for a in std if a["task"] == "sem"] + tgt
    cite_anc = [a for a in std if a["task"] == "cite"] if need_cite else []

    def ans_of(x):
        return x["answer"] if "answer" in x else (x["resp"].get("answer") or x["resp"].get("conclusion") or "").strip()

    def key_of(x):
        return x.get("key") or x["aid"]

    # 阶段 1：JC（缺才调）与 依据判官
    jobs = []
    for x in sem_items + sem_anc:
        k = key_of(x)
        if k not in jc_replay:
            jobs.append({"instance": iC, "task": "sem", "key": k, "messages": [{"role": "user", "content": A.sem_request(C[x["qid"]], x["qid"], ans_of(x))}],
                         "tag": f"{batch_tag}|sem|{k}|JC"})
    for x in [it for it in items if it["route"] == "cite"] + cite_anc:
        k = key_of(x)
        if k not in cite_replay:
            for inst in (iL1, iL2):
                jobs.append({"instance": inst, "task": "cite", "key": k, "messages": [{"role": "user", "content": A.cite_request(C[x["qid"]], x["qid"], x["resp"], None)}],
                             "tag": f"{batch_tag}|cite|{k}|{inst[-4:]}"})
    if dry:
        return {"status": "dry", "phase1_new": sum(1 for j in jobs if cache.get(j["instance"], j["task"], j["key"]) is None)}
    clients = {}

    def client_for(inst):
        if inst not in clients:
            cl = make_client(inst.split("#")[-1], FACT_MAX_TOKENS)
            cl.instance = inst; clients[inst] = cl
        return clients[inst]

    raws, _, n1 = run_jobs(jobs, cache, client_for, rec, concurrency, budget, counter)
    if any((j["instance"], j["task"], j["key"]) not in raws for j in jobs):
        return {"status": "incomplete", "phase": 1}
    sC = {}
    for x in sem_items + sem_anc:
        k = key_of(x)
        fin = jc_replay.get(k) or A.sem_finalize(C[x["qid"]], x["qid"], ans_of(x), raws[(iC, "sem", k)])
        sC[k] = fin
    # 阶段 2：JF（JC < 0.4 的考题跳过：均值不可能 ≥ 0.7；锚一律判）
    jobs2 = []
    for x in sem_items + sem_anc:
        k = key_of(x)
        if "aid" not in x and sC[k].get("score", 0.0) < SKIP_BELOW:
            continue
        jobs2.append({"instance": iF, "task": "fact", "key": k, "messages": [{"role": "user", "content": fact_request(C[x["qid"]], x["qid"], ans_of(x))}],
                      "tag": f"{batch_tag}|fact|{k}|JF"})
    raws2, _, n2 = run_jobs(jobs2, cache, client_for, rec, concurrency, budget, counter)
    if any((j["instance"], j["task"], j["key"]) not in raws2 for j in jobs2):
        return {"status": "incomplete", "phase": 2}

    def cite_labels(x):
        k = key_of(x)
        if k in cite_replay:
            return cite_replay[k]
        return tuple(A.cite_finalize(raws[(inst, "cite", k)]) for inst in (iL1, iL2))

    J, _ = A.upstream()
    rows = []
    for x in sem_items + sem_anc:
        k = key_of(x)
        fC = sC[k]
        if (iF, "fact", k) in raws2:
            fF = fact_finalize(C[x["qid"]], x["qid"], ans_of(x), raws2[(iF, "fact", k)])
            skipped = False
        else:
            fF = {"ok": True, "score": 0.0, "conflicts": [], "fabrications": [], "rejected": [], "skipped": True}
            skipped = True
        det = hard_conflict(_key_text(C[x["qid"]]), ans_of(x))
        cons = {"det": det, "conflicts": fF["conflicts"], "fabrications": fF["fabrications"]}
        cons["bad"] = bool(det or fF["conflicts"] or fF["fabrications"])
        row = {"src": "anchor" if "aid" in x else "item", "key": k, "qid": x["qid"], "sC": fC.get("score", 0.0), "sF": fF.get("score", 0.0),
               "jf_skipped": skipped, "cons": cons, "expect": x.get("expect"), "kind": x.get("kind", "std" if "aid" in x else None),
               "route": x.get("route")}
        if row["src"] == "item" and x["route"] == "cite":
            row["cite"] = cite_labels(x)
        rows.append(row)
    # 金丝雀
    qs = {it["qid"] for it in items} | {a["qid"] for a in sem_anc}
    for q in sorted(qs):
        for i, (a, b, c, e) in enumerate(CANARY):
            rows.append({"src": "canary", "key": f"K{i}|{q}", "qid": q, "sC": a, "sF": b, "cons": {"bad": c}, "expect": e})
    order = list(range(len(rows))); random.Random(f"{batch_tag}-loop").shuffle(order)
    for i in order:
        r = rows[i]
        r["rid"] = opaque(batch_tag, f"{r['src']}|{r['key']}")
        r["final"], r["mean"] = score_row_a(r["sC"], r["sF"], r["cons"]["bad"])
    # 依据契合撤销（同上游：仅 cite 类降级、双判官均 fit 才撤销）
    for r in rows:
        if r["src"] == "item" and r.get("route") == "cite":
            l1, l2 = r["cite"]
            brief = next(it for it in items if it["key"] == r["key"])["res_brief"]
            if l1 == "fit" and l2 == "fit" and brief.get("down_kind") == "cite" and not r["cons"]["bad"]:
                r["final"] = "pass"; r["path"] = "L2 撤销降级"
    # 规则层"删依据"金丝雀：批内每题 要点原文＋空依据 ⇒ 必须结构违规
    idx = A.units()
    rc_fail = []
    for q in sorted({it["qid"] for it in items}):
        c = C[q]
        resp = {"qid": q, "conclusion": A._pts_text(c, q), "answer": A._pts_text(c, q), "evidence": [], "confidence": "certain"}
        rt, _ = route_v2(c, resp, idx)
        if rt != "fail_struct":
            rc_fail.append(q)
    # 上岗考
    anc = [r for r in rows if r["src"] == "anchor"]
    stdr = [r for r in anc if r["kind"] == "std"]; tgtr = [r for r in anc if r["kind"] != "std"]
    exp = [r["expect"] for r in stdr]
    base = max(exp.count(x) for x in set(exp)) / len(exp)
    g = {"std_baseline": round(base, 4)}
    labC = lambda r: "pass" if r["sC"] >= PASS else "fail"
    labF = lambda r: "pass" if (r["sF"] >= PASS and not (r["cons"]["conflicts"] or r["cons"]["fabrications"])) else "fail"
    ok = True
    for nm, lab in (("JC", labC), ("JF", labF)):
        acc = sum(lab(r) == r["expect"] for r in stdr) / len(stdr)
        g[f"std_acc_{nm}"] = round(acc, 4)
        ok &= acc >= 0.90 and (acc - base) * 100 >= 15
    g["tgt_acc_JF"] = round(sum(labF(r) == "fail" for r in tgtr) / max(1, len(tgtr)), 4)
    ok &= g["tgt_acc_JF"] >= 0.90
    g["final_acc_std"] = round(sum(r["final"] == r["expect"] for r in stdr) / len(stdr), 4)
    g["final_acc_tgt"] = round(sum(r["final"] == r["expect"] for r in tgtr) / max(1, len(tgtr)), 4)
    g["final_tgt_by_kind"] = {k: f"{sum(r['final'] == r['expect'] for r in tgtr if r['kind'] == k)}/{sum(1 for r in tgtr if r['kind'] == k)}" for k in sorted({r['kind'] for r in tgtr})}
    ok &= g["final_acc_std"] >= 0.90 and g["final_acc_tgt"] >= 0.90
    can = [r for r in rows if r["src"] == "canary"]
    g["canary_n"] = len(can); g["canary_fail"] = [r["key"] for r in can if r["final"] != r["expect"]][:20]
    ok &= not g["canary_fail"]
    g["rule_nobasis_canary_n"] = len({it["qid"] for it in items}); g["rule_nobasis_canary_fail"] = rc_fail
    ok &= not rc_fail
    if cite_anc:
        cl = [(cite_labels(a), a["expect"]) for a in cite_anc]
        for j in (0, 1):
            acc = sum(("fit" if l[j] == "fit" else "notfit") == e for l, e in cl) / len(cl)
            g[f"cite_acc_j{j+1}"] = round(acc, 4)
            ok &= acc >= 0.90
    it_both = [r for r in rows if r["src"] == "item" and not r["jf_skipped"]]
    nc = [r for r in it_both if not r["cons"]["bad"]]
    g["items_agree_cov_noconflict"] = agreement([labC(r) for r in nc], ["pass" if r["sF"] >= PASS else "fail" for r in nc])
    g["items_agree_all"] = agreement([labC(r) for r in it_both], [labF(r) for r in it_both])
    g["anchors_agree_std"] = agreement([labC(r) for r in stdr], [labF(r) for r in stdr])
    a = g["items_agree_cov_noconflict"]
    if a["n"]:
        ok &= (a["agree"] >= 0.8) or (a["kappa"] is not None and a["kappa"] >= 0.6)
    g["pass"] = bool(ok)
    return {"status": "valid" if g["pass"] else "gate_failed", "version": V2_VERSION, "gate": g,
            "items": [r for r in rows if r["src"] == "item"], "anchors": anc, "new_calls": n1 + n2}


def final_for(items, batch_rows):
    """把 v2 批结果与非判官路由合成逐题最终结果。"""
    by = {r["key"]: r for r in batch_rows}
    out = {}
    for it in items:
        if it["route"] == "fail_struct":
            out[it["key"]] = {"final": "fail", "path": "规则层结构违规"}
        elif it["route"] == "pass_rule":
            out[it["key"]] = {"final": "pass", "path": "规则层通过（退化条件/无据题：诚实轴判定）"}
        else:
            r = by[it["key"]]
            out[it["key"]] = {"final": r["final"], "path": r.get("path", "v2 语义判官"), "sC": r["sC"], "sF": r["sF"],
                              "jf_skipped": r["jf_skipped"], "cons": r["cons"]}
    return out
