"""判分器 v2 候选 · 考卷 B（C 型续接预测）。

与原判分器 harness/judge.py 的关系：原文件不改；本模块保留其全部对外函数（parse_verdict / combine / WEIGHT /
judge_messages / gate_check / build_anchors …，行为逐字相同，故冻结回归集的确定性边界用例可直接对本模块跑），
另加 v2 的三处改动：

1. 两个判官**真正不同**（不再是同一提示词的两个实例）：
   - JC＝覆盖判官：原提示词（JUDGE_SYSTEM，看断点前上下文＋答案键＋预测），三档；
   - JF＝事实核查判官（新提示词 FACT_SYSTEM）：先读预测、后读参照，**不看断点前上下文**，逐个列参照里的关键要素
     （人名/产品/数字/编号/对象/动作）并标 一致/缺失/冲突，再给三档。两者盲评、互不可见、顺序各自打乱。
   覆盖档＝combine(JC, JF)（沿用原"取宽松档"，回归集边界用例不变）。
2. **实体与数值一致性轴**（与覆盖档分开记）：
   - 确定性层：预测与答案键同句式（对齐率≥0.6）且数字/拉丁词被换 ⇒ 冲突；
   - 判官层：JF 列出的"冲突"对须机械可证（ref 逐字在答案键、pred 逐字在预测且不在答案键…），不可证的作废；
   任一层冲突 ⇒ 实体轴＝conflict ⇒ **最终档＝miss（替换即判错）**，覆盖档仍单独记录。
3. 上岗考 v2：原 48 锚 ＋ **定向错误锚**（替换实体 12、相反断言 8）＋ **合成金丝雀行**（批内每张卡 3 行，固定判词，
   走与考题完全相同的计分循环；行号不透明，计分循环看不到"锚/题/金丝雀"之分）＋ 依据轴金丝雀（删依据必须报不可回源）。
"""
from __future__ import annotations
import json, math, random, re

from harness.examB import extract_json, check_basis
from harness.judge_v2.common import (V2_VERSION, norm, opaque, hard_conflict, verify_pair, agreement, kappa as _kappa,
                                     CallCache, run_jobs)

# ======== 以下与 harness/judge.py 逐字同义（回归集确定性边界用例依赖这些接口） ========
VERDICTS = ("strict", "paraphrase", "miss")
WEIGHT = {"strict": 1.0, "paraphrase": 0.5, "miss": 0.0, "parse_err": 0.0}
LENIENT_ORDER = {"strict": 2, "paraphrase": 1, "miss": 0, "parse_err": -1}
ANCHOR_SEED = 20261006
DIRTY = {"C-116"}
IRRELEVANT = [
    "我想问一下明天上海的天气怎么样，要不要带伞。",
    "帮我推荐一个做红烧肉的家常做法，最好不要放冰糖。",
    "我的笔记本电脑风扇声音很大，是不是该清灰了？",
    "周末想带孩子去动物园，你觉得早上几点出发比较好？",
    "请把这段英文翻译成中文：The meeting has been moved to Thursday.",
    "我最近在学吉他，F 和弦总是按不响，有什么技巧吗？",
    "帮我算一下，房贷一百万、三十年、利率百分之三点五，月供多少？",
    "推荐几本适合通勤时听的有声书，悬疑类的。",
    "我家的猫最近不太爱吃东西，需要带去看兽医吗？",
    "下周去成都出差三天，帮我列一个行李清单。",
    "怎样在表格软件里把两列数据合并成一列？",
    "我想换一部手机，预算三千元左右，主要拍照用。",
]
GATE = {"anchor_acc_min": 0.90, "anchor_margin_pp_min": 15.0,
        "agree_min": 0.80, "kappa_min": 0.60, "max_attempts": 3}

JUDGE_SYSTEM = (
    "你是盲评判官。你将看到：一段真实人机对话在断点前人类（「我」）说的话、断点后人类真实的下一条消息（真实下文），"
    "以及某个系统对「人类下一步」的预测。只判断预测与真实下文的内容对上程度，不评价文笔，不考虑预测来源。\n"
    "三档：\n"
    "- strict：抓住了真实下文的核心行为/内容（措辞不同也能直接相认）；\n"
    "- paraphrase：方向一致、沾边，但细节/重点明显不同；\n"
    "- miss：不一致、跑偏，或空泛套话（放在任何断点都成立的泛泛预测）。\n"
    "只输出一个 JSON：{\"verdict\": \"strict|paraphrase|miss\", \"why\": \"一句话理由\"}")


def judge_messages(card: dict, prediction: str) -> list[dict]:
    pre = "\n".join(f"- {p['text']}" for p in card["pre"])
    u = (f"【断点前上下文】（断点前·我说，原文逐条）\n{pre}\n\n"
         f"【真实下文·人类下一条（答案键）】\n{card['answer']['human']['text']}\n\n"
         f"【待判预测】\n{prediction if prediction.strip() else '（空）'}\n\n只输出 JSON。")
    return [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": u}]


def parse_verdict(raw: str) -> tuple[str, str]:
    d = extract_json(raw or "")
    if isinstance(d, dict) and str(d.get("verdict", "")).strip().lower() in VERDICTS:
        return str(d["verdict"]).strip().lower(), str(d.get("why", ""))[:400]
    m = re.search(r'"verdict"\s*:\s*"(strict|paraphrase|miss)"', raw or "")
    if m:
        return m.group(1), ""
    return "parse_err", ""


def _ngrams(s, n=8):
    s = re.sub(r"\s+", "", s)
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def build_anchors(cards: list[dict]) -> list[dict]:
    rng = random.Random(ANCHOR_SEED)
    elig = [c for c in cards if c["id"] not in DIRTY]
    pick = rng.sample(elig, 48)
    out = []
    for c in pick[:24]:
        out.append({"aid": f"A+{c['id']}", "card": c["id"], "prediction": c["answer"]["human"]["text"], "expect": "strict", "kind": "pos"})
    for c in pick[24:36]:
        g = _ngrams(c["answer"]["human"]["text"])
        others = [o for o in elig if o["id"] != c["id"] and not (_ngrams(o["answer"]["human"]["text"]) & g)]
        o = rng.choice(others)
        out.append({"aid": f"A×{c['id']}<{o['id']}", "card": c["id"], "prediction": o["answer"]["human"]["text"], "expect": "miss", "kind": "cross"})
    for i, c in enumerate(pick[36:48]):
        out.append({"aid": f"A0{c['id']}", "card": c["id"], "prediction": IRRELEVANT[i], "expect": "miss", "kind": "irrelevant"})
    return out


def kappa(a: list[str], b: list[str]) -> float:
    return _kappa(a, b)


def combine(v1: str, v2: str) -> tuple[str, str]:
    """返回 (主口径=更宽松档, 对照=更严格档)。"""
    hi = max(v1, v2, key=lambda v: LENIENT_ORDER[v])
    lo = min(v1, v2, key=lambda v: LENIENT_ORDER[v])
    return hi, lo


def gate_check(anchor_rows: list[dict], item_rows: list[dict]) -> dict:
    """原版上岗考（保留，供回归集边界用例与对照）。v2 上岗考见 gate_v2。"""
    res = {"n_anchor": len(anchor_rows), "n_items": len(item_rows)}
    base = max(sum(r["expect"] == "strict" for r in anchor_rows), sum(r["expect"] == "miss" for r in anchor_rows)) / max(1, len(anchor_rows))
    res["majority_baseline"] = base
    ok = True
    for j in ("v1", "v2"):
        acc = sum(r[j] == r["expect"] for r in anchor_rows) / max(1, len(anchor_rows))
        res[f"anchor_acc_{j}"] = acc
        res[f"anchor_margin_pp_{j}"] = round((acc - base) * 100, 1)
        ok &= acc >= GATE["anchor_acc_min"] and (acc - base) * 100 >= GATE["anchor_margin_pp_min"]
    for name, rows in (("anchor", anchor_rows), ("items", item_rows)):
        a = [r["v1"] for r in rows]; b = [r["v2"] for r in rows]
        agree = sum(x == y for x, y in zip(a, b)) / max(1, len(rows))
        k = kappa(a, b)
        res[f"{name}_agree"] = agree
        res[f"{name}_kappa"] = k
        if rows:
            ok &= agree >= GATE["agree_min"] and (agree == 1.0 or (not math.isnan(k) and k >= GATE["kappa_min"]))
    res["pass"] = bool(ok)
    return res


# ======== v2 新增 ========
FACT_SYSTEM = (
    "你是事实核查员（与另一位判官相互独立，你看不到对方的判断）。你将看到一条「待核预测」（某系统对一个人下一句话的预测），"
    "以及一条「参照」（这个人真实说出的下一句话）。请从事实核查的角度判断预测是否说对了。\n"
    "第一步：从参照中摘出关键要素——人名/产品名/机构名、数字/编号/版本/章节、具体对象、核心动作或主张；每个要素逐字摘自参照。\n"
    "第二步：逐个核对预测：\n"
    "- 一致：预测里出现了该要素，或用同义说法表达了它；\n"
    "- 缺失：预测没有提到它；\n"
    "- 冲突：预测在相应位置给了**不同的**人名/名称/数字/对象，或作出了与参照**相反**的主张。冲突时必须在 pred 字段逐字摘录预测里的对应原文。\n"
    "缺失≠冲突；措辞不同、同义改写、简称不算冲突。\n"
    "第三步：给整体档位：strict＝核心行为与内容都对上且没有冲突；paraphrase＝方向一致但细节/重点明显不同或缺失；"
    "miss＝不一致、跑偏、空泛套话，或关键要素冲突。\n"
    "只输出一个 JSON：{\"facts\": [{\"key\": \"参照原文要素\", \"status\": \"一致|缺失|冲突\", \"pred\": \"预测原文（冲突必填）\"}], "
    "\"verdict\": \"strict|paraphrase|miss\", \"why\": \"一句话\"}")
FACT_MAX_TOKENS = 900


def fact_messages(card: dict, prediction: str) -> list[dict]:
    u = (f"【待核预测】\n{prediction if prediction.strip() else '（空）'}\n\n"
         f"【参照·真实的下一句话】\n{card['answer']['human']['text']}\n\n只输出 JSON。")
    return [{"role": "system", "content": FACT_SYSTEM}, {"role": "user", "content": u}]


def parse_fact(raw: str, ref: str, pred: str) -> dict:
    d = extract_json(raw or "")
    v = "parse_err"; facts = []
    if isinstance(d, dict):
        vv = str(d.get("verdict", "")).strip().lower()
        v = vv if vv in VERDICTS else "parse_err"
        facts = [f for f in (d.get("facts") or []) if isinstance(f, dict)]
    elif raw:
        m = re.search(r'"verdict"\s*:\s*"(strict|paraphrase|miss)"', raw)
        v = m.group(1) if m else "parse_err"
    ok, bad = [], []
    for f in facts:
        if str(f.get("status", "")).strip() != "冲突":
            continue
        good, why = verify_pair(str(f.get("key", "")), str(f.get("pred", "")), ref, pred)
        (ok if good else bad).append({"ref": str(f.get("key", ""))[:80], "ans": str(f.get("pred", ""))[:80], **({} if good else {"rejected": why})})
    return {"verdict": v, "conflicts": ok, "conflicts_rejected": bad, "why": (d or {}).get("why", "") if isinstance(d, dict) else ""}


def consistency(ref: str, pred: str, fact: dict | None) -> dict:
    det = hard_conflict(ref, pred)
    jud = (fact or {}).get("conflicts") or []
    return {"status": "conflict" if (det or jud) else "ok", "det": det, "judge": jud}


def score_row(v_cov: str, v_cov_strict: str, cons_status: str) -> tuple[str, str]:
    """唯一的计分函数：覆盖档（宽松/严格）＋实体轴 ⇒ 最终档。替换即判错。"""
    if cons_status == "conflict":
        return "miss", "miss"
    return v_cov, v_cov_strict


# ---- 定向错误锚（锚卡上人工登记；与门槛 2 夹具卡不重叠，与回归集卡不重叠） ----
TARGETED_SWAPS = {
    "C-086": [("道德经", "孙子兵法"), ("2500年前", "800年前"), ("老子", "孔子")],
    "C-018": [("AGI猫娘工程", "区块链钱包工程"), ("ollama", "docker")],
    "C-054": [("国家机关", "海外基金会"), ("征信体系", "积分体系")],
    "C-088": [("P5", "P2"), ("道德经", "论语"), ("明朝", "唐朝")],
    "C-041": [("信息论", "控制论"), ("skill", "plugin")],
    "C-105": [("第零定律", "第三定律"), ("3个推进", "7个推进")],
    "C-092": [("符蕴道", "王建国"), ("修正主义", "保守主义"), ("本体论", "认识论")],
    "C-025": [("外部协作者", "内部审计员"), ("v19.0", "v7.0")],
    "C-046": [("中科院院士", "风险投资人"), ("学术探讨", "融资谈判")],
    "C-082": [("月菲", "小雪"), ("陈默", "李强"), ("2个小故事", "5个小故事"), ("量子计算机", "蒸汽机")],
    "C-026": [("元物理", "形而上学"), ("18.0", "9.0")],
    "C-107": [("负反馈调节", "正反馈放大"), ("智能系统", "交通系统")],
}
TARGETED_CONTRA = ["C-037", "C-043", "C-094", "C-112", "C-001", "C-002", "C-068", "C-111"]
CONTRA_TAIL = "——不过算了，这件事我决定彻底放弃，不再继续了。"


def build_targeted_anchors(by: dict) -> list[dict]:
    out = []
    for cid, pairs in TARGETED_SWAPS.items():
        t = by[cid]["answer"]["human"]["text"]; s = t
        for a, b in pairs:
            s = s.replace(a, b)
        assert s != t, cid
        out.append({"aid": f"T-swap{cid}", "card": cid, "prediction": s, "expect": "miss", "kind": "swap"})
    for cid in TARGETED_CONTRA:
        t = by[cid]["answer"]["human"]["text"]
        out.append({"aid": f"T-contra{cid}", "card": cid, "prediction": t.rstrip("。？！?! ") + CONTRA_TAIL,
                    "expect": "nonstrict", "kind": "contra"})
    return out


def basis_traceable(basis) -> bool:
    """依据轴（不进分数）：有依据且逐条逐字可回源。"""
    bc = check_basis(basis or [])
    return bool(bc) and all(b["verbatim"] for b in bc)


CANARY = [  # (覆盖宽松, 覆盖严格, 实体轴) → 期望最终档
    ("miss", "miss", "ok", "miss"),
    ("strict", "strict", "conflict", "miss"),
    ("strict", "strict", "ok", "strict"),
]


def canary_rows(batch_cards) -> list[dict]:
    rows = []
    for cid in sorted(batch_cards):
        for i, (a, b, c, e) in enumerate(CANARY):
            rows.append({"src": "canary", "key": f"K{i}|{cid}", "card": cid, "cov": a, "cov_strict": b,
                         "cons": {"status": c, "det": [], "judge": []}, "expect": e})
    return rows


def _acc(rows, judge_field, ok):
    if not rows:
        return None
    return sum(ok(r, r[judge_field]) for r in rows) / len(rows)


def gate_v2(std_rows, tgt_rows, item_rows, canary_res, basis_canary_ok) -> dict:
    """v2 上岗考（预登记于 validation/_judge_v2/preregistration.json）。"""
    g = {}
    base = max(sum(r["expect"] == "strict" for r in std_rows), sum(r["expect"] == "miss" for r in std_rows)) / max(1, len(std_rows))
    g["std_majority_baseline"] = round(base, 4)
    ok = True
    for j in ("vC", "vF"):
        acc = _acc(std_rows, j, lambda r, v: v == r["expect"])
        g[f"std_acc_{j}"] = acc
        ok &= acc is not None and acc >= GATE["anchor_acc_min"] and (acc - base) * 100 >= GATE["anchor_margin_pp_min"]
    # JF 定向锚：替换→实体冲突被确认；相反→非 strict
    def f_ok(r):
        if r["kind"] == "swap":
            return bool(r["cons"]["judge"])
        return r["vF"] != "strict" or bool(r["cons"]["judge"])
    g["tgt_acc_vF"] = sum(f_ok(r) for r in tgt_rows) / max(1, len(tgt_rows))
    ok &= g["tgt_acc_vF"] >= 0.90

    def fin_ok(r):
        e = r["expect"]
        return r["final"] != "strict" if e == "nonstrict" else r["final"] == e
    g["final_acc_std"] = sum(fin_ok(r) for r in std_rows) / max(1, len(std_rows))
    g["final_acc_tgt"] = sum(fin_ok(r) for r in tgt_rows) / max(1, len(tgt_rows))
    g["final_tgt_by_kind"] = {k: f"{sum(fin_ok(r) for r in tgt_rows if r['kind'] == k)}/{sum(1 for r in tgt_rows if r['kind'] == k)}"
                              for k in sorted({r['kind'] for r in tgt_rows})}
    ok &= g["final_acc_std"] >= 0.90 and g["final_acc_tgt"] >= 0.90
    g["canary_n"] = canary_res["n"]; g["canary_fail"] = canary_res["fail"][:20]
    ok &= not canary_res["fail"]
    g["basis_canary_ok"] = basis_canary_ok
    ok &= basis_canary_ok
    # 一致率：覆盖档（实体轴无冲突的条目上）；上游 judge_audit 口径：同分 ≥0.8 或 κ ≥0.6
    nc = [r for r in item_rows if r["cons"]["status"] == "ok" and not r.get("auto")]
    a = agreement([r["vC"] for r in nc], [r["vF"] for r in nc])
    allr = [r for r in item_rows if not r.get("auto")]
    g["items_agree_noconflict"] = a
    g["items_agree_all"] = agreement([r["vC"] for r in allr], [r["vF"] for r in allr])
    g["anchors_agree_std"] = agreement([r["vC"] for r in std_rows], [r["vF"] for r in std_rows])
    if a["n"]:
        ok &= (a["agree"] >= GATE["agree_min"]) or (a["kappa"] is not None and a["kappa"] >= GATE["kappa_min"])
    g["pass"] = bool(ok)
    return g


def judge_batch_v2(by: dict, items: list[dict], rec, *, make_client, batch_tag: str, cache_path: str,
                   jc_replay: dict | None = None, concurrency: int = 4, budget=None, counter=None,
                   std_anchors=None, tgt_anchors=None, dry=False) -> dict:
    """items: [{"key","card","prediction","auto": None|"parse_err","basis"?}]
    jc_replay: {key: verdict}——覆盖判官 JC 的已有判词（同一提示词、温度 0，来自原批次 judge-1），命中则不重调。"""
    cards = list(by.values())
    std = std_anchors if std_anchors is not None else build_anchors([c for c in cards])
    tgt = tgt_anchors if tgt_anchors is not None else build_targeted_anchors(by)
    jc_replay = jc_replay or {}
    cache = CallCache(cache_path)
    instC, instF = f"{batch_tag}#JC", f"{batch_tag}#JF"
    work = [("item", it) for it in items if it.get("auto") != "parse_err"] + [("std", a) for a in std] + [("tgt", a) for a in tgt]
    random.Random(f"{batch_tag}-v2").shuffle(work)
    jobs = []
    for kind, x in work:
        key = x.get("key") or x["aid"]
        if key not in jc_replay:
            jobs.append({"instance": instC, "task": "cov", "key": key, "messages": judge_messages(by[x["card"]], x["prediction"]),
                         "tag": f"{batch_tag}|{kind}|cov|{key}"})
        jobs.append({"instance": instF, "task": "fact", "key": key, "messages": fact_messages(by[x["card"]], x["prediction"]),
                     "tag": f"{batch_tag}|{kind}|fact|{key}"})
    if dry:
        return {"status": "dry", "n_jobs": len(jobs), "n_new": sum(1 for j in jobs if cache.get(j["instance"], j["task"], j["key"]) is None)}
    client_cache = {}

    def client_for(inst):
        if inst not in client_cache:
            cl = make_client("judge-F" if inst.endswith("JF") else "judge-C",
                             FACT_MAX_TOKENS if inst.endswith("JF") else 600)
            cl.instance = inst
            client_cache[inst] = cl
        return client_cache[inst]

    raws, n_todo, n_called = run_jobs(jobs, cache, client_for, rec, concurrency, budget, counter)
    missing = [j for j in jobs if (j["instance"], j["task"], j["key"]) not in raws]
    if missing:
        return {"status": "incomplete", "missing": len(missing), "called": n_called}

    # ---- 统一计分循环：考题、锚、金丝雀同一循环，行号不透明 ----
    rows = []
    for kind, x in work:
        key = x.get("key") or x["aid"]
        ref = by[x["card"]]["answer"]["human"]["text"]
        vC = jc_replay[key] if key in jc_replay else parse_verdict(raws[(instC, "cov", key)])[0]
        fact = parse_fact(raws[(instF, "fact", key)], ref, x["prediction"])
        cov, cov_s = combine(vC, fact["verdict"])
        rows.append({"src": kind, "key": key, "card": x["card"], "vC": vC, "vF": fact["verdict"], "cov": cov, "cov_strict": cov_s,
                     "cons": consistency(ref, x["prediction"], fact), "fact": fact, "expect": x.get("expect"), "kind": x.get("kind")})
    for it in items:
        if it.get("auto") == "parse_err":
            rows.append({"src": "item", "key": it["key"], "card": it["card"], "vC": "miss", "vF": "miss", "cov": "miss", "cov_strict": "miss",
                         "cons": {"status": "na", "det": [], "judge": []}, "auto": True})
    batch_cards = {it["card"] for it in items} | {a["card"] for a in std} | {a["card"] for a in tgt}
    rows += canary_rows(batch_cards)
    order = list(range(len(rows))); random.Random(f"{batch_tag}-loop").shuffle(order)
    scored = {}
    for i in order:
        r = rows[i]
        rid = opaque(batch_tag, f"{r['src']}|{r['key']}")
        final, final_s = score_row(r["cov"], r["cov_strict"], r["cons"]["status"])
        if r["card"] in ['C-021', 'C-051', 'C-069', 'C-077', 'C-078', 'C-110']:   # MUTANT（测试分支）：预选错题判对（门槛 6① 同型）
            final = final_s = "strict"
        scored[rid] = (final, final_s)
        r["rid"] = rid
    for r in rows:
        r["final"], r["final_strict"] = scored[r["rid"]]
        r["score"] = WEIGHT[r["final"]]
    can = [r for r in rows if r["src"] == "canary"]
    canary_res = {"n": len(can), "fail": [r["key"] for r in can if r["final"] != r["expect"]]}
    # 依据轴金丝雀（删依据）：批内每张卡，答案键原文＋空依据 ⇒ 依据轴必须报不可回源
    bc = all(not basis_traceable([]) for _ in batch_cards)
    g = gate_v2([r for r in rows if r["src"] == "std"], [r for r in rows if r["src"] == "tgt"],
                [r for r in rows if r["src"] == "item"], canary_res, bc)
    return {"status": "valid" if g["pass"] else "gate_failed", "version": V2_VERSION, "gate": g,
            "items": [r for r in rows if r["src"] == "item"], "anchors": [r for r in rows if r["src"] in ("std", "tgt")],
            "canary": canary_res, "new_calls": n_called}
