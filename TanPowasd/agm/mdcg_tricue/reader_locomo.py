# -*- coding: utf-8 -*-
"""md_cg × TriCue v3 检索 → LLM 阅读器 → LoCoMo 官方 F1（带 key，用户 2026-10-14 19:08 批准一次）。

口径（运行前固定，不按结果改）：
  · 检索结果取 bench_e2e_en.py 在 MDCG_TRICUE=1 下的 per[].got（零 key，可复现），只用 test 1300 题；
  · 上下文 = 前 10 条 turn，按名次排列，每条前缀该会话日期（取自 LoCoMo 原数据 session_N_date_time）；
  · 阅读器：cline-pass/deepseek-v4.1-flash，temperature 0，不带 system，不限 max_tokens；
    提示词沿用 LoCoMo 官方 QA 提示（短语作答、尽量用原文；第 2 类加官方日期提示）；
  · 评分：LoCoMo 官方 F1（task_eval/evaluation.py 同法：小写、去标点、去 a/an/the/and、Porter 词干；
    第 1 类按逗号拆分取 gold 各点最佳匹配平均；第 3 类 gold 取 ';' 前；第 2/4 类普通 F1）。
用法：python reader_locomo.py --ret final_on.json --data locomo10.json --cache cache.jsonl [--secs 1000] [--workers 3]
      python reader_locomo.py ... --score out.json
"""
import argparse, json, os, re, string, sys, time, threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bench"))
import hive_official as H  # noqa: E402
sys.path.append("/workspace/work/pylib")
from nltk.stem import PorterStemmer  # noqa: E402

PS = PorterStemmer()
QA = ("{ctx}\n\nBased on the above context, write an answer in the form of a short phrase for the following "
      "question. Answer with exact words from the context whenever possible.\n\nQuestion: {q} Short answer:")
QA_T = ("{ctx}\n\nBased on the above context, write an answer in the form of a short phrase for the following "
        "question. Answer with exact words from the context whenever possible. Use DATE of CONVERSATION to "
        "answer with an approximate date.\n\nQuestion: {q} Short answer:")


def norm(s):
    s = str(s).replace(",", "").lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the|and)\b", " ", s)
    return " ".join(s.split())


def f1(pred, gold):
    p = [PS.stem(w) for w in norm(pred).split()]
    g = [PS.stem(w) for w in norm(gold).split()]
    c = sum((Counter(p) & Counter(g)).values())
    if c == 0:
        return 0.0
    pr, rc = c / len(p), c / len(g)
    return 2 * pr * rc / (pr + rc)


def f1_multi(pred, gold):
    ps = [x.strip() for x in str(pred).split(",")]
    gs = [x.strip() for x in str(gold).split(",")]
    return sum(max(f1(p, g) for p in ps) for g in gs) / len(gs)


def score(cat, pred, gold):
    if cat == 1:
        return f1_multi(pred, gold)
    if cat == 3:
        gold = str(gold).split(";")[0].strip()
    return f1(pred, gold)


def build(ret, data):
    d = json.load(open(data, encoding="utf-8"))
    text, date = {}, {}
    for si, c in enumerate(d):
        conv = c["conversation"]
        for key in conv:
            m = re.fullmatch(r"session_(\d+)", key)
            if not m:
                continue
            dt = conv.get(f"session_{m.group(1)}_date_time", "")
            for ti, t in enumerate(conv[key]):
                nid = f"scene_{si}_session_{m.group(1)}_turn_{ti}"
                text[nid] = f"{t['speaker']}: {t['text']}"
                date[nid] = dt
    qa = {}
    for si, c in enumerate(d):
        for qi, x in enumerate(c["qa"]):
            qa[f"scene_{si}_q_{qi}"] = x
    items = []
    for p in json.load(open(ret, encoding="utf-8"))["per"]:
        if p["split"] != "test":
            continue
        x = qa[p["qid"]]
        ctx = "\n".join(f"DATE of CONVERSATION: {date[i]}\n{text[i]}" for i in p["got"][:10])
        tpl = QA_T if x["category"] == 2 else QA
        items.append({"qid": p["qid"], "cat": x["category"], "gold": x["answer"], "q": x["question"],
                      "prompt": tpl.format(ctx=ctx, q=x["question"]), "hit10": bool(set(p["gold"]) & set(p["got"][:10]))})
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ret", required=True); ap.add_argument("--data", required=True)
    ap.add_argument("--cache", required=True); ap.add_argument("--secs", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=3); ap.add_argument("--score")
    a = ap.parse_args()
    items = build(a.ret, a.data)
    done = {}
    if os.path.exists(a.cache):
        for ln in open(a.cache, encoding="utf-8"):
            r = json.loads(ln); done[r["qid"]] = r["pred"]
    if a.score:
        cats, tot, n, miss = {}, 0.0, 0, 0
        per = []
        for it in items:
            if it["qid"] not in done:
                miss += 1; continue
            s = score(it["cat"], done[it["qid"]], it["gold"])
            per.append({"qid": it["qid"], "cat": it["cat"], "f1": round(s, 4), "hit10": it["hit10"],
                        "pred": done[it["qid"]], "gold": it["gold"]})
            v = cats.setdefault(str(it["cat"]), [0.0, 0]); v[0] += s; v[1] += 1; tot += s; n += 1
        hs = [p["f1"] for p in per if p["hit10"]]; ms = [p["f1"] for p in per if not p["hit10"]]
        out = {"n": n, "missing": miss, "F1": round(tot / max(n, 1), 4),
               "cat": {k: {"F1": round(v[0] / v[1], 4), "n": v[1]} for k, v in sorted(cats.items())},
               "F1_hit10": round(sum(hs) / max(len(hs), 1), 4), "n_hit10": len(hs),
               "F1_miss10": round(sum(ms) / max(len(ms), 1), 4), "n_miss10": len(ms)}
        json.dump({"summary": out, "per": per}, open(a.score, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps(out, ensure_ascii=False)); return
    todo = [it for it in items if it["qid"] not in done]
    print(f"total {len(items)} done {len(done)} todo {len(todo)}", flush=True)
    lock, t0, calls = threading.Lock(), time.time(), [0]
    fo = open(a.cache, "a", encoding="utf-8")

    def run(it):
        if time.time() - t0 > a.secs:
            return
        try:
            pred = H.chat(it["prompt"], H.MODEL, system=False).strip()
        except Exception as e:  # noqa: BLE001
            print("fail", it["qid"], e, flush=True); return
        with lock:
            calls[0] += 1
            fo.write(json.dumps({"qid": it["qid"], "pred": pred}, ensure_ascii=False) + "\n"); fo.flush()
    with ThreadPoolExecutor(a.workers) as ex:
        list(as_completed([ex.submit(run, it) for it in todo]))
    print(f"calls {calls[0]} elapsed {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
