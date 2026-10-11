# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流（Confluence）· 源图抽取：LLM 把每轮输入拆成（主，谓，宾）三元组。结果按批缓存，可零 key 复跑。
用法：python extract.py --split dev [--batch 10] [--workers 4] [--cap 250] [--dry]
调用计数写入 cache/calls.json；累计达到 --cap 即停（用户授权的试点上限 250 次）。"""
import argparse, json, pathlib, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "tricue"), str(HERE.parent / "bench")]
import gen_bench3 as G            # noqa: E402  locomo_items（dev = conv-30、conv-47）
from hive_official import chat, parse_json, MODEL  # noqa: E402

CACHE = HERE / "cache"
PROMPT = """You convert dialogue turns into a knowledge graph. For EACH turn below, list its facts as
[subject, predicate, object] triples.
Rules:
- Replace pronouns (I, me, my, you, she, we, it...) with the concrete name they refer to; "I" is the speaker.
- Keep entity names short and as written (e.g. "Caroline", "LGBTQ support group", "pottery class").
- Predicates are short verb phrases ("attended", "plans to", "is", "painted", "felt").
- Add a date/time only if the turn states one, as a triple [event, "when", time].
- Include facts from [image: ...] captions as things the speaker shared.
- A turn with no factual content gets [].
Output ONLY JSON: {{"turns": {{"<turn id>": [[s,p,o], ...], ...}}}}

Turns:
{turns}"""


def items(split):
    """同 gen_bench3.locomo_items，但带 sample_id。"""
    out = []
    for c in json.loads((G.DATA / "locomo10.json").read_text(encoding="utf-8")):
        if split != "all" and (split == "dev") != G.H3(c["sample_id"]):
            continue
        conv = c["conversation"]
        n = sorted(int(k.split("_")[1]) for k in conv if k.startswith("session_") and not k.endswith("date_time"))
        turns, ids = [], []
        for i in n:
            for t in conv[f"session_{i}"]:
                txt = f"{t['speaker']}: {t['text']}"
                if t.get("blip_caption"):
                    txt += f" [image: {t['blip_caption']}]"
                turns.append(txt); ids.append(t["dia_id"])
        out.append({"sid": c["sample_id"], "turns": turns, "ids": ids, "qa": [q for q in c["qa"] if q.get("category") != 5]})
    return out


def batches(item, size):
    ids, turns = item["ids"], item["turns"]
    for i in range(0, len(ids), size):
        yield [(ids[k], turns[k]) for k in range(i, min(i + size, len(ids)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev"); ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--workers", type=int, default=4); ap.add_argument("--cap", type=int, default=250)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    CACHE.mkdir(exist_ok=True)
    cf = CACHE / "calls.json"
    calls = json.loads(cf.read_text()) if cf.exists() else {"n": 0, "fail": 0}
    lock = threading.Lock()
    jobs = []
    for it in items(a.split):
        for b in batches(it, a.batch):
            key = f"{it['sid']}_{b[0][0].replace(':', '-')}"
            if not (CACHE / f"{key}.json").exists():
                jobs.append((key, b))
    print("pending batches", len(jobs), "calls so far", calls["n"], flush=True)
    if a.dry:
        return

    def run(job):
        key, b = job
        with lock:
            if calls["n"] >= a.cap:
                return "capped"
            calls["n"] += 1; cf.write_text(json.dumps(calls))
        txt = "\n".join(f"[{i}] {t}" for i, t in b)
        try:
            obj = parse_json(chat(PROMPT.format(turns=txt), MODEL, max_tokens=20000, tries=1))
            (CACHE / f"{key}.json").write_text(json.dumps({"ids": [i for i, _ in b], "out": obj}, ensure_ascii=False))
            return "ok"
        except Exception as e:  # noqa: BLE001
            with lock:
                calls["fail"] += 1; cf.write_text(json.dumps(calls))
            return f"fail {e}"[:120]

    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        for k, r in enumerate(ex.map(run, jobs)):
            if k % 10 == 0 or r != "ok":
                print(k, r, round(time.time() - t0), flush=True)
    print("done calls", calls, flush=True)


if __name__ == "__main__":
    main()
