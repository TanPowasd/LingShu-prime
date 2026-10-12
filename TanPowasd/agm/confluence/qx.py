# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流·题面侧 LLM 抽取（query extraction）：把每道题拆成 实体 / 谓词 / 时间约束 / 检索词 / 假想答句。
与源图同一模型，结果按题缓存，可零 key 复跑。
LLM 接入优化：
- 每批 10 题；失败（HTTP 500/504/空响应/JSON 坏）先指数退避重试一次，仍失败就拆半递归，最小 1 题；
- JSON 校验：每题必须有 ents/preds 列表，字段裁成字符串，缺题自动补抽；
- 调用计数与失败计数落盘（cache_q/<set>/calls.json），--cap 封顶，--secs 分段跑（沙箱 1200s 限制）。
用法：python qx.py locomo-dev|hive <hive根目录?> [--workers 3] [--cap 60] [--secs 1000] [--dry]"""
import argparse, json, pathlib, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench"), str(HERE.parent / "tricue")]
from hive_official import chat, parse_json, MODEL, SYS_SUFFIX  # noqa: E402

P_EN = """You prepare search queries for a memory system over a long chat history between two people.
For EACH question, output:
- "ents": the people, objects, places, events, activities it asks about, written as they would appear in the chat (short noun phrases; resolve "she/he" only if the question names them);
- "preds": the relation or action asked about, as short verb phrases, plus 1-2 likely paraphrases;
- "time": the time constraint if any ("last year", "May 2023", "before the move"), else null;
- "kw": 3-6 extra keywords a matching chat line would likely contain (synonyms, related concrete words);
- "hyde": one short sentence, as the speaker might have said it in the chat, that would answer the question (invent plausible specifics; it is only used for search).
Output ONLY JSON: {{"q": {{"<id>": {{"ents": [...], "preds": [...], "time": null, "kw": [...], "hyde": "..."}}, ...}}}}

Questions:
{qs}"""

P_ZH = """你在为一个检索中文小说正文的记忆系统准备检索式。对下面每道题，输出：
- "ents"：题目问到的人物、物品、地点、事件，用小说原文里可能出现的写法（人名写全名，也给常见称呼）；
- "preds"：题目问的关系或动作，短动词短语，并给 1-2 个近义说法；
- "time"：题中的时间约束（如“第三天夜里”“事发前”），没有就 null；
- "kw"：3-6 个命中的原文句子里很可能出现的词（近义词、相关具体词）；
- "hyde"：一句像小说原文的假想句子，能回答本题（细节可以编，只用于检索）。
只输出 JSON：{{"q": {{"<题号>": {{"ents": [...], "preds": [...], "time": null, "kw": [...], "hyde": "..."}}, ...}}}}

题目：
{qs}"""


def questions(which, root=None):
    """[(qid, question)]"""
    if which == "locomo-dev":
        import extract as X
        out = []
        for it in X.items("dev"):
            for k, q in enumerate(it["qa"]):
                out.append((f"{it['sid']}#{k}", q["question"]))
        return out
    import hive_retrieval as HR
    return [(c["qid"], c["question"]) for c in HR.load_cards(pathlib.Path(root))]


def clean(v):
    if not isinstance(v, dict):
        return None
    L = lambda x: [str(s).strip() for s in (x if isinstance(x, list) else [x] if x else []) if str(s).strip()][:8]
    ents, preds = L(v.get("ents")), L(v.get("preds"))
    if not ents and not preds:
        return None
    t = v.get("time")
    return {"ents": ents, "preds": preds, "time": str(t).strip() if t not in (None, "", "null") else None,
            "kw": L(v.get("kw")), "hyde": str(v.get("hyde") or "").strip()[:300]}


def cache_dir(which):
    d = HERE / ("cache_q" + SYS_SUFFIX) / which
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(which):
    d = cache_dir(which)
    m = {}
    for f in d.glob("b_*.json"):
        m.update(json.loads(f.read_text(encoding="utf-8")))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=("locomo-dev", "hive")); ap.add_argument("root", nargs="?")
    ap.add_argument("--batch", type=int, default=10); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--cap", type=int, default=60); ap.add_argument("--secs", type=int, default=1000)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    d = cache_dir(a.which); cf = d / "calls.json"
    calls = json.loads(cf.read_text()) if cf.exists() else {"n": 0, "fail": 0}
    have = load(a.which)
    qs = [(i, q) for i, q in questions(a.which, a.root) if i not in have]
    tmpl = P_ZH if a.which == "hive" else P_EN
    jobs = [qs[i:i + a.batch] for i in range(0, len(qs), a.batch)]
    print("pending questions", len(qs), "batches", len(jobs), "calls so far", calls, flush=True)
    if a.dry:
        print(tmpl.format(qs="\n".join(f"[{i}] {q}" for i, q in qs[:3])))
        return
    lock, t0 = threading.Lock(), time.time()

    def call(b):
        with lock:
            if calls["n"] >= a.cap or time.time() - t0 > a.secs:
                return None
            calls["n"] += 1; cf.write_text(json.dumps(calls))
        try:
            obj = parse_json(chat(tmpl.format(qs="\n".join(f"[{i}] {q}" for i, q in b)), MODEL, tries=1))
            got = (obj or {}).get("q", obj) or {}
            return {i: c for i, _ in b if (c := clean(got.get(i) or got.get(f"[{i}]")))}
        except Exception:  # noqa: BLE001
            with lock:
                calls["fail"] += 1; cf.write_text(json.dumps(calls))
            return {}

    def run(b, depth=0):
        r = call(b)
        if r is None:
            return 0
        if not r and depth == 0:          # 整批失败：退避后原样重试一次
            time.sleep(15); r = call(b) or {}
        miss = [x for x in b if x[0] not in r]
        if r:
            key = f"b_{abs(hash(tuple(sorted(r))))}"
            (d / f"{key}.json").write_text(json.dumps(r, ensure_ascii=False, indent=0), encoding="utf-8")
        n = len(r)
        if miss and len(b) > 1 and (len(miss) < len(b) or depth == 0):   # 缺题/失败 → 拆半补抽
            h = (len(miss) + 1) // 2
            n += run(miss[:h], depth + 1) + (run(miss[h:], depth + 1) if miss[h:] else 0)
        elif miss and len(b) == 1 and depth < 3:
            time.sleep(10); n += run(miss, depth + 1)
        return n

    with ThreadPoolExecutor(a.workers) as ex:
        for k, n in enumerate(ex.map(run, jobs)):
            print(k, "got", n, round(time.time() - t0), flush=True)
    print("done", calls, "cached", len(load(a.which)), flush=True)


if __name__ == "__main__":
    main()
