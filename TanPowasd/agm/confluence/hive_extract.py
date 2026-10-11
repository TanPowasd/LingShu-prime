# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇流 · hive 主轮中文源图抽取：LLM 把每个 160 字块拆成（主，谓，宾）三元组，按批缓存到 cache_hive/，可零 key 复跑。
用法：python hive_extract.py <hive-memory-bench> [--batch 10] [--workers 2] [--cap 40] [--secs 1050] [--dry]"""
import argparse, json, pathlib, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "bench")]
import hive_retrieval as HR  # noqa: E402
from hive_official import chat, parse_json, MODEL  # noqa: E402

CACHE = HERE / "cache_hive"
PROMPT = """你要把小说正文片段转成知识图谱。对下面每个片段，列出其中的事实，格式为 [主语, 谓语, 宾语] 三元组。
规则：
- 代词（他、她、它、我们、这……）一律换成它指代的具体人名或事物名。
- 实体名保持简短、照原文写法（人名、地名、物品、组织、事件）。
- 谓语是简短的动词短语（“交给”“怀疑”“住在”“是”“答应”）。
- 原文写了时间、原因、条件时，用 [事件, "时间"/"原因"/"条件", 内容] 表示。
- 没有事实的片段给 []。
只输出 JSON：{{"chunks": {{"<片段编号>": [[主,谓,宾], ...], ...}}}}

片段：
{chunks}"""


def ids_of(chunks):
    return [f"{c['cid']}#{c['i']}" for c in chunks]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("bench")
    ap.add_argument("--batch", type=int, default=10); ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--cap", type=int, default=40); ap.add_argument("--secs", type=int, default=1050); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    chunks = HR.load_chunks(pathlib.Path(a.bench)); ids = ids_of(chunks)
    CACHE.mkdir(exist_ok=True); cf = CACHE / "calls.json"
    calls = json.loads(cf.read_text()) if cf.exists() else {"n": 0, "fail": 0}
    jobs = [(f"b{i:04d}", list(range(i, min(i + a.batch, len(chunks))))) for i in range(0, len(chunks), a.batch)]
    jobs = [j for j in jobs if not (CACHE / f"{j[0]}.json").exists()]
    print("pending", len(jobs), "calls so far", calls, flush=True)
    if a.dry:
        return
    lock, t0 = threading.Lock(), time.time()

    def run(job):
        key, idx = job
        if time.time() - t0 > a.secs:
            return "time"
        with lock:
            if calls["n"] >= a.cap:
                return "capped"
            calls["n"] += 1; cf.write_text(json.dumps(calls))
        txt = "\n".join(f"[{ids[i]}] {chunks[i]['text'].strip()}" for i in idx)
        try:
            obj = parse_json(chat(PROMPT.format(chunks=txt), MODEL, tries=1))
            (CACHE / f"{key}.json").write_text(json.dumps({"ids": [ids[i] for i in idx], "out": obj}, ensure_ascii=False))
            return "ok"
        except Exception as e:  # noqa: BLE001
            with lock:
                calls["fail"] += 1; cf.write_text(json.dumps(calls))
            time.sleep(20)
            return f"fail {e}"[:120]

    with ThreadPoolExecutor(a.workers) as ex:
        for k, r in enumerate(ex.map(run, jobs)):
            print(k, r, round(time.time() - t0), flush=True)
    print("done", calls, flush=True)


def load(bench):
    chunks = HR.load_chunks(pathlib.Path(bench)); ids = ids_of(chunks); m = {}
    for f in sorted(CACHE.glob("b*.json")):
        for k, v in ((json.loads(f.read_text())["out"] or {}).get("chunks", {}) or {}).items():
            m[k.strip("[] ")] = [t for t in v if isinstance(t, list) and len(t) == 3]
    return chunks, [m.get(i, []) for i in ids], sum(i in m for i in ids) / len(ids)


if __name__ == "__main__":
    main()
