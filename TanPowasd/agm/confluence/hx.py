# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流·两跳检索（hop-2）：第一跳用冻结 QMD 取前 N 段，让模型读片段后写出“还缺什么”的追问检索式
（桥接实体、片段里出现的新名字/事件、换说法），结果按题缓存，可零 key 复跑。
LLM 接入同 qx.py：每批若干题，整批失败退避重试，缺题拆半补抽，JSON 校验，calls.json 计数，--cap/--secs。
用法：python hx.py locomo-dev|hive <hive根?> [--batch 5] [--workers 3] [--cap 80] [--secs 1000] [--dry]"""
import argparse, json, pathlib, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench"), str(HERE.parent / "tricue")]
from hive_official import chat, parse_json, MODEL, SYS_SUFFIX  # noqa: E402
import qx  # noqa: E402

N1 = {"locomo-dev": 15, "hive": 20}

P_EN = """A memory system retrieved chat snippets for each question below (first hop). Read them and write follow-up search queries for a SECOND retrieval hop that would find the evidence still missing.
For EACH question output:
- "found": true if the snippets already fully answer it, else false;
- "follow": 1-3 short search queries (keywords or a short sentence as it might appear in the chat). Use bridge facts from the snippets: names, places, events, dates or objects mentioned there that lead to the answer; for multi-part or "how many / which all" questions, query the parts not yet covered; for time questions, query the event plus its date words.
Output ONLY JSON: {{"q": {{"<id>": {{"found": false, "follow": ["...", "..."]}}, ...}}}}

{items}"""

P_ZH = """记忆系统已为下面每道题从中文小说正文里检索到一些片段（第一跳）。读完后，为第二跳检索写出追问检索式，用来找到仍缺的证据。
每道题输出：
- "found"：片段已能完整回答则 true，否则 false；
- "follow"：1-3 条简短检索式（原文里可能出现的词或短句）。要利用片段里出现的桥接线索：人名、称呼、地点、物品、事件、时间；多要点/“哪些”类题，检索尚未覆盖的要点；时间类题，检索事件加时间词。
只输出 JSON：{{"q": {{"<题号>": {{"found": false, "follow": ["...", "..."]}}, ...}}}}

{items}"""


def first_hop(which, root=None):
    """[(qid, question, [snippet texts])] 用冻结 QMD 的前 N1 段。"""
    out = []
    if which == "locomo-dev":
        import extract as X, bench_dev as BD, qmd as Q
        H = qx.load("locomo-dev")
        for it in X.items("dev"):
            tri = BD.load_triples(it)[0]
            hints = {q["question"]: H.get(f"{it['sid']}#{k}") for k, q in enumerate(it["qa"])}
            g = Q.QMD(it["turns"], it["ids"], tri, hints, w_v3=3.0, w_qx=3.0)
            for k, q in enumerate(it["qa"]):
                out.append((f"{it['sid']}#{k}", q["question"], [f"[{it['ids'][t]}] {it['turns'][t]}" for t in g.rank(q["question"])[:N1[which]]]))
        return out
    import hive_retrieval as HR, hive_qmd
    cards = HR.load_cards(pathlib.Path(root))
    chunks, g, _ = hive_qmd.build(root, cards)
    for c in cards:
        r = sorted(g.rank(c["question"])[:N1[which]])
        out.append((c["qid"], c["question"], [f"[{chunks[i]['cid']}] {chunks[i]['text'].strip()}" for i in r]))
    return out


def clean(v):
    if not isinstance(v, dict):
        return None
    f = v.get("follow")
    f = [str(s).strip() for s in (f if isinstance(f, list) else [f] if f else []) if str(s).strip()][:3]
    return {"found": bool(v.get("found")), "follow": f}


def cache_dir(which):
    """追问缓存目录：LLM_SYS=1 时加 _sys 后缀，与不带系统提示词的旧追问式隔离（dsh-bounty#466 F2）。"""
    return HERE / ("cache_h" + SYS_SUFFIX) / which


def load(which):
    m = {}
    for f in cache_dir(which).glob("b_*.json"):
        m.update(json.loads(f.read_text(encoding="utf-8")))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=("locomo-dev", "hive")); ap.add_argument("root", nargs="?")
    ap.add_argument("--batch", type=int, default=5); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--cap", type=int, default=80); ap.add_argument("--secs", type=int, default=1000)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    d = cache_dir(a.which); d.mkdir(parents=True, exist_ok=True); cf = d / "calls.json"
    calls = json.loads(cf.read_text()) if cf.exists() else {"n": 0, "fail": 0}
    have = load(a.which)
    qs = [x for x in first_hop(a.which, a.root) if x[0] not in have]
    tmpl = P_ZH if a.which == "hive" else P_EN
    fmt = lambda b: tmpl.format(items="\n\n".join(
        (f"=== 题号 {i} ===\n题目：{q}\n片段：\n" if a.which == "hive" else f"=== id {i} ===\nQuestion: {q}\nSnippets:\n") + "\n".join(s) for i, q, s in b))
    jobs = [qs[i:i + a.batch] for i in range(0, len(qs), a.batch)]
    print("pending", len(qs), "batches", len(jobs), "calls so far", calls, "prompt chars", len(fmt(jobs[0])) if jobs else 0, flush=True)
    if a.dry:
        print(fmt(jobs[0][:1])[:3000]); return
    lock, t0 = threading.Lock(), time.time()

    def call(b):
        with lock:
            if calls["n"] >= a.cap or time.time() - t0 > a.secs:
                return None
            calls["n"] += 1; cf.write_text(json.dumps(calls))
        try:
            obj = parse_json(chat(fmt(b), MODEL, tries=1))
            got = (obj or {}).get("q", obj) or {}
            return {i: c for i, _, _ in b if (c := clean(got.get(i) or got.get(f"[{i}]")))}
        except Exception:  # noqa: BLE001
            with lock:
                calls["fail"] += 1; cf.write_text(json.dumps(calls))
            return {}

    def run(b, depth=0):
        r = call(b)
        if r is None:
            return 0
        if not r and depth == 0:
            time.sleep(15); r = call(b) or {}
        miss = [x for x in b if x[0] not in r]
        if r:
            (d / f"b_{abs(hash(tuple(sorted(r))))}.json").write_text(json.dumps(r, ensure_ascii=False, indent=0), encoding="utf-8")
        n = len(r)
        if miss and len(b) > 1 and (len(miss) < len(b) or depth == 0):
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
