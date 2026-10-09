"""H-LLM（可选维）：检索交付的「作答充分性」——只有 LLM 能判的意图项（recall 服务于推理作答）。

协议：
- 语料/查询沿用 data.corpus/queries（seed 固定），取 ea/noisy/upd/pair 四类各 10 条；recall(q, limit=5) 的正文作「材料」。
- 两个判官 = 两个独立的 cline-pass/deepseek-v4.1-flash 实例（temperature 0.0 / 0.7，题序各自打乱）各自独立判：仅凭材料能否得出金标答案（upd 要求得出「现值」）。
- 锚自证：每个判官先判 20 条锚（10 条材料含金标答案 → 应 true；10 条只有干扰材料 → 应 false），
  锚正确率 < 0.9 的判官作废；两判官都作废 → 本维缺席（不进分母）。
- 维分 = 有效判官「充分」率的平均 × 100；判官间一致率随读数报告。零 LLM 维度仍是主干。
密钥从环境变量 CLINE_API_KEY 读取（由代理注入；不打印、不落盘）；429/5xx 指数退避重试，空回复重问。
"""
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from data import corpus, queries

URL = "https://api.cline.bot/api/v1/chat/completions"
MODEL = "cline-pass/deepseek-v4.1-flash"
# 两个独立的 flash 判官实例：不同 temperature、不同题序（各自按种子打乱后再还原）
JUDGES = {"J1": {"temperature": 0.0, "order_seed": 11}, "J2": {"temperature": 0.7, "order_seed": 29}}
PROMPT = ("你是严格的阅卷人。只根据【材料】判断能否得出【参考答案】（若问「现在」则须能确定现值，材料里新旧值并存且无法判断哪个是现值算不能）。"
          "不得使用材料外知识。只输出 JSON：{{\"sufficient\": true 或 false}}。\n【问题】{q}\n【参考答案】{a}\n【材料】\n{m}")


ERRS = {}
#: 逐次调用的磁盘缓存（同一请求体 → 同一回复；分段续跑不重复调用、不重复计费）。不含密钥。
CACHE = os.environ.get("HARD_LLM_CACHE", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "llm_cache"))


def _err(k):
    ERRS[k] = ERRS.get(k, 0) + 1


def _call(cfg, content):
    body = {"model": MODEL, "max_tokens": 800, "temperature": cfg["temperature"], "reasoning": {"enabled": False},
            "messages": [{"role": "user", "content": content}]}
    key = hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    cp = os.path.join(CACHE, key + ".json")
    if os.path.exists(cp):
        try:
            return json.load(open(cp, encoding="utf-8"))["content"]
        except ValueError:
            pass
    txt = _post(body)
    os.makedirs(CACHE, exist_ok=True)
    tmp = cp + f".{os.getpid()}.tmp"
    json.dump({"content": txt}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, cp)
    return txt


def _post(body):
    hdr = {"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["CLINE_API_KEY"]}
    for k in range(8):
        try:
            req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=hdr)
            d = json.load(urllib.request.urlopen(req, timeout=60))
            txt = d["data"]["choices"][0]["message"].get("content") or ""
            if _verdict(txt) is None and k < 2:      # 空回复/未给 JSON：重问（至多 2 次），仍无则按原文判
                _err("no_json")
                continue
            return txt
        except urllib.error.HTTPError as ex:
            _err(f"http{ex.code}")
            if ex.code in (429, 500, 502, 503, 504):        # 500 多为「空回复」，429 为限速
                time.sleep(min(20, 2 ** k) * (3 if ex.code == 429 else 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            _err(type(ex).__name__)
            time.sleep(min(20, 2 ** k))
    raise RuntimeError(f"retries exhausted {ERRS}")


def _verdict(txt):
    t = (txt or "").lower().replace(" ", "")
    if '"sufficient":true' in t:
        return True
    if '"sufficient":false' in t:
        return False
    return None


def run(A, seed, n_per=10):
    facts = corpus(seed + 500, 1000)
    m = A.open(A.tmpdb("llm"))
    for f in facts:
        m.add(f["text"], skip_dedup=True)
    qs, by = [], {}
    for t, q, rel in queries(seed + 500, facts, 200):
        if t in ("ea", "noisy", "upd", "pair") and by.get(t, 0) < n_per:
            by[t] = by.get(t, 0) + 1
            if t == "upd":
                gold = [d for d, g in rel.items() if g == 2][0]
                ans = facts[gold]["v"]
            else:
                ans = "；".join(f"{facts[d]['e']}的{facts[d]['a']}是{facts[d]['v']}" for d in sorted(rel))
            mats = [str(n["content"]) for n, _ in m.recall(q, limit=5)]
            qs.append((t, q, ans, mats))
    rnd = random.Random(seed)
    anchors = []
    for k in range(20):
        f = facts[rnd.randrange(len(facts))]
        q = f"{f['e']}的{f['a']}是什么"
        ans = f["v"]
        distract = [g["text"] for g in rnd.sample(facts, 4) if g["e"] != f["e"]]
        mats = (distract[:3] + [f["text"]]) if k < 10 else distract[:4]
        anchors.append((k < 10, q, ans, mats))

    def judge(cfg, q, a, mats):
        return _verdict(_call(cfg, PROMPT.format(q=q, a=a, m="\n".join(f"- {x}" for x in mats) or "（空）")))

    def judge_all(cfg, items):
        order = list(range(len(items)))
        random.Random(cfg["order_seed"]).shuffle(order)
        got = dict(zip(order, ex.map(lambda i: judge(cfg, items[i][1], items[i][2], items[i][3]), order)))
        return [got[i] for i in range(len(items))]

    out = {"judges": {}, "n_items": len(qs)}
    per_item = {}
    ex = ThreadPoolExecutor(max_workers=2)      # 包月网关限速：并发 2
    if True:
        for jn, cfg in JUDGES.items():
            anc = judge_all(cfg, anchors)
            acc = sum(1 for (want, *_), got in zip(anchors, anc) if got == want) / len(anchors)
            res = judge_all(cfg, qs)
            per_item[jn] = res
            out["judges"][jn] = {"model": MODEL, **cfg, "anchor_acc": acc, "valid": acc >= 0.9,
                                 "sufficient_rate": sum(1 for r in res if r) / len(res),
                                 "by_type": {t: sum(1 for (tt, *_), r in zip(qs, res) if tt == t and r) / by[t] for t in by}}
    valid = [j for j in out["judges"].values() if j["valid"]]
    if len(per_item) == 2:
        a, b = per_item["J1"], per_item["J2"]
        out["agreement"] = sum(1 for x, y in zip(a, b) if x == y) / len(a)
    out["call_errors"] = dict(ERRS)
    out["score"] = round(100 * sum(j["sufficient_rate"] for j in valid) / len(valid), 2) if valid else None
    return out
