"""判官：C 型三档（strict / paraphrase / miss）、双判官、上岗考（锚题）与整批作废重批。

口径沿用 hive-memory-bench《真实史端到端测评 · 初测 v1.0》§二：
- 加权 = strict×1 + paraphrase×0.5 + miss×0；判官不看材料、不看臂名、不看 file/行号；请求含「断点前上下文」（卡 pre 原文逐条）
- temperature 0、thinking off；正则抠首个 JSON；不可解析记 parse_err 并如实计入分母（按 miss 计分）
- 锚：seed 20261006，24 正锚（answer.human 原文当预测）＋12 跨卡负锚（他卡下文，8-gram 无交集）＋12 无关负锚；排除脏卡 C-116
差异（本站，写进 SPEC）：初测为「同判官两轮重放」，本站为「两个独立 flash 实例」各判一次；不一致取更宽松档为主口径，另存更严格档。
"""
from __future__ import annotations
import json, math, os, random, re, threading
from concurrent.futures import ThreadPoolExecutor

from .examB import extract_json

VERDICTS = ("strict", "paraphrase", "miss")
WEIGHT = {"strict": 1.0, "paraphrase": 0.5, "miss": 0.0, "parse_err": 0.0}
LENIENT_ORDER = {"strict": 2, "paraphrase": 1, "miss": 0, "parse_err": -1}
ANCHOR_SEED = 20261006
DIRTY = {"C-116"}

# 无关负锚：判官校准材料（不是考题），与语料主题无关的日常句子，固定 12 条。
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
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    cats = set(a) | set(b)
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return 1.0 if pe >= 1 else (po - pe) / (1 - pe)


def combine(v1: str, v2: str) -> tuple[str, str]:
    """返回 (主口径=更宽松档, 对照=更严格档)。"""
    hi = max(v1, v2, key=lambda v: LENIENT_ORDER[v])
    lo = min(v1, v2, key=lambda v: LENIENT_ORDER[v])
    return hi, lo


def gate_check(anchor_rows: list[dict], item_rows: list[dict]) -> dict:
    """anchor_rows/item_rows: [{"v1":..,"v2":..,("expect")}]。"""
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
            # kappa 在单类塌缩时无定义/偏低：同分率=1 时视为通过
            ok &= agree >= GATE["agree_min"] and (agree == 1.0 or (not math.isnan(k) and k >= GATE["kappa_min"]))
    res["pass"] = bool(ok)
    return res


def _load_cache(path):
    cache = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line); cache[(d["attempt"], d["judge"], d["key"])] = d
                except (json.JSONDecodeError, KeyError):
                    pass
    return cache


def judge_batch(cards_by_id: dict, items: list[dict], anchors: list[dict], rec, *, make_client,
                concurrency: int = 4, batch_tag: str = "", cache_path: str | None = None) -> dict:
    """items: [{"key": 唯一键, "card": qid, "prediction": str, "auto": None|"parse_err"}]
    两个独立判官实例各判全部（items+anchors，打乱顺序、盲评）。
    闸门不过 → 整批作废（judge.batch.void），换新实例重批，最多 GATE.max_attempts 次。"""
    cache = _load_cache(cache_path)
    lock = threading.Lock()
    for attempt in range(1, GATE["max_attempts"] + 1):
        # 判官实例名按 批次+尝试 固定：续跑时同一实例的已判条目从缓存复用（判词事件仍可引用原录像时间点）
        j1 = make_client("judge-1"); j2 = make_client("judge-2")
        j1.instance = f"{batch_tag}#a{attempt}-judge-1"; j2.instance = f"{batch_tag}#a{attempt}-judge-2"
        rec.event("judge.batch.start", batch=batch_tag, attempt=attempt, judges=[j1.instance, j2.instance],
                  n_items=len(items), n_anchors=len(anchors))
        work = [("item", it) for it in items] + [("anchor", a) for a in anchors]
        random.Random(f"{batch_tag}-{attempt}").shuffle(work)

        def run(w):
            kind, x = w
            if kind == "item" and x.get("auto") == "parse_err":
                return kind, x, {"v1": "miss", "v2": "miss", "why1": "答卷不可解析（parse_err，计 miss）", "why2": "", "ev1": x.get("ev"), "ev2": x.get("ev"), "auto": True}
            card = cards_by_id[x["card"]]
            msgs = judge_messages(card, x["prediction"])
            outs = {}
            for nm, cl in (("1", j1), ("2", j2)):
                key = x.get("key") or x.get("aid")
                hit = cache.get((attempt, cl.instance, key))
                if hit:
                    outs[f"v{nm}"], outs[f"why{nm}"], outs[f"ev{nm}"] = hit["verdict"], hit["why"], hit["ev"]
                    continue
                tag = f"{batch_tag}|{kind}|{key}|j{nm}"
                r = cl.chat(msgs, rec, tag=tag)
                v, why = parse_verdict(r["content"])
                ev = rec.event("judge.verdict", batch=batch_tag, attempt=attempt, judge=cl.instance, kind=kind,
                               key=key, card=x["card"], verdict=v, why=why, raw=r["content"])
                outs[f"v{nm}"], outs[f"why{nm}"], outs[f"ev{nm}"] = v, why, {"seq": ev["seq"], "t": ev["t"]}
                if cache_path:
                    with lock, open(cache_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"attempt": attempt, "judge": cl.instance, "key": key, "verdict": v, "why": why,
                                            "ev": outs[f"ev{nm}"]}, ensure_ascii=False) + "\n")
            return kind, x, outs

        with ThreadPoolExecutor(concurrency) as ex:
            results = list(ex.map(run, work))
        arows, irows = [], []
        for kind, x, o in results:
            row = {**o, "card": x["card"]}
            if kind == "anchor":
                row.update(aid=x["aid"], expect=x["expect"], kind=x["kind"]); arows.append(row)
            else:
                main, strict = combine(o["v1"], o["v2"])
                row.update(key=x["key"], final=main, final_strict=strict, score=WEIGHT[main]); irows.append(row)
        g = gate_check(arows, [r for r in irows if not r.get("auto")])
        ev = rec.event("judge.batch.gate", batch=batch_tag, attempt=attempt, **g)
        if g["pass"]:
            return {"status": "valid", "attempt": attempt, "gate": g, "gate_ev": {"seq": ev["seq"], "t": ev["t"]},
                    "items": irows, "anchors": arows, "voided": attempt - 1}
        rec.event("judge.batch.void", batch=batch_tag, attempt=attempt, reason="上岗考/一致率不达标，整批作废重批")
    return {"status": "void", "attempt": GATE["max_attempts"], "gate": g, "items": irows, "anchors": arows,
            "voided": GATE["max_attempts"]}
