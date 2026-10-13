# -*- coding: utf-8 -*-
"""R/D oracle 阶段 1 · 带 key 跑：三臂 reader + judge（只此一次，上限 650 次 HTTP 调用）。

只替换被测那一级：三臂 reader 系统提示词 READER_SYS、用户模板 READER_USER、judge 提示词
JUDGE_SYS 全部从 dsh-memory 仓内 md_cg.bench_e2e_qa / md_cg.bench_e2e_locomo_qa 直接 import
（逐字复用，不复制），temperature=0、max_tokens（reader 300 / judge 200）与 bench 同；
三臂同一模型。唯一变量 = 「候选记忆」段：
  C  闭卷        「（无）」
  S  系统交付 ≡ D 原文交付   top-10 原文（bench retrieval 臂同形；构造上同一输入，见预注册 §2）
  R  完美检索    该题全部 gold 证据原文，按 (session, turn) 时序
凭据：不读、不写任何 key；api.cline.bot 由运行环境按主机注入（请求不带 Authorization）。
环境：DSH_MEMORY_ROOT=<dsh-memory 仓根>；CACHE_DIR（缺省 %TEMP%/oracle_rd_cache）
跑法：python -X utf8 run.py [--limit N]
产出：results.json（逐题逐臂）、calls.jsonl（每次实际 HTTP 调用的记录，不含凭据）
"""
import argparse, hashlib, json, os, sys, tempfile, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

DSH = os.environ["DSH_MEMORY_ROOT"]
sys.path.insert(0, DSH)
from md_cg.bench_e2e_qa import JUDGE_SYS, READER_SYS, parse_json_field  # noqa: E402
from md_cg.bench_e2e_locomo_qa import READER_USER  # noqa: E402

API = "https://api.cline.bot/api/v1/chat/completions"
MODEL = "cline-pass/deepseek-v4.1-flash"
CAP = 650
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get("CACHE_DIR") or os.path.join(tempfile.gettempdir(), "oracle_rd_cache")
CLOSED = "（无）"
ARMS = ("C", "S", "R")
_lock = threading.Lock()
_n_http = [0]


class CapReached(RuntimeError):
    pass


def _http(body):
    with _lock:
        if _n_http[0] >= CAP:
            raise CapReached(f"已达上限 {CAP}")
        _n_http[0] += 1
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    d = d.get("data", d)
    return d["choices"][0]["message"].get("content") or "", d.get("usage") or {}


def chat(kind, messages, max_tokens, log):
    body = {"model": MODEL, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
    h = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    p = os.path.join(CACHE, f"{kind}_{h[:32]}.json")
    if os.path.isfile(p):
        return json.load(open(p, encoding="utf-8"))["out"], True
    err = None
    for k in range(3):                       # 失败重试上限 3 次（每次计入调用数）
        try:
            out, usage = _http(body)
            with _lock:
                log.write(json.dumps({"kind": kind, "h": h[:16], "try": k, "ok": True,
                                      "tokens": usage.get("total_tokens"), "out": out},
                                     ensure_ascii=False) + "\n"); log.flush()
            if out.strip():
                json.dump({"out": out}, open(p, "w", encoding="utf-8"), ensure_ascii=False)
                return out, False
            err = "empty content"
        except CapReached:
            raise
        except Exception as e:               # noqa: BLE001 — 记录后重试，非静默
            err = f"{type(e).__name__}: {e}"
            with _lock:
                log.write(json.dumps({"kind": kind, "h": h[:16], "try": k, "ok": False,
                                      "err": err[:200]}, ensure_ascii=False) + "\n"); log.flush()
        time.sleep(3 * (k + 1))
    raise RuntimeError(err)


def one(q, arm, log):
    cards = {"C": CLOSED, "S": q["cards_sys"], "R": q["cards_R"]}[arm]
    row = {"qid": q["qid"], "conv": q["conv"], "cat": q["cat"], "arm": arm, "hit10": q["hit10"]}
    try:
        raw, c1 = chat("reader", [{"role": "system", "content": READER_SYS},
                                  {"role": "user", "content": READER_USER.format(q=q["q"], cards=cards)}],
                       300, log)
        a = parse_json_field(raw, "answer")
        row["answer"] = a if a is not None else (raw or "").strip()[:80]
        raw2, c2 = chat("judge", [{"role": "system", "content": JUDGE_SYS},
                                  {"role": "user", "content": f"问题：{q['q']}\ngold：{q['gold_answer'] or ''}\n"
                                                              f"模型回答：{row['answer']}"}], 200, log)
        v = parse_json_field(raw2, "verdict")
        row["verdict"] = v if v in ("correct", "incorrect", "refused") else None
        if row["verdict"] is None:
            row["error"] = f"judge 不可解析 {(raw2 or '')[:60]}"
        row["cached"] = [c1, c2]
    except Exception as e:                   # noqa: BLE001 — 写入 row.error，报告计数
        row["error"] = f"{type(e).__name__}: {e}"
        row["verdict"] = None
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    sample = json.load(open(os.path.join(HERE, "sample.json"), encoding="utf-8"))["sample"]
    qs = sample[:a.limit] if a.limit else sample
    tasks = [(q, arm) for q in qs for arm in ARMS]
    with open(os.path.join(HERE, "calls.jsonl"), "a", encoding="utf-8") as log:
        with ThreadPoolExecutor(a.workers) as ex:
            rows = list(ex.map(lambda t: one(t[0], t[1], log), tasks))
    n_calls = sum(1 for _ in open(os.path.join(HERE, "calls.jsonl"), encoding="utf-8"))
    errs = [r for r in rows if r.get("error")]
    print(f"本进程 HTTP {_n_http[0]} 次；calls.jsonl 累计 {n_calls} 次；错误行 {len(errs)}")
    for e in errs[:5]:
        print("  ", e["qid"], e["arm"], e["error"][:120])
    json.dump({"model": MODEL, "arms": ARMS, "rows": rows},
              open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
