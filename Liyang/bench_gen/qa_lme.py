# -*- coding: utf-8 -*-
"""检索 → 问答：LongMemEval_S 小样本，看检索提升能否变成答对率提升（PREREG 修订 2）。

  python qa_lme.py sample <set> <n> [--seed S]           # 抽样 → qa/<set>_sample.json（分层：按题型等比例）
  python qa_lme.py gen <arm> <set> [--k 10]               # arm ∈ base v1 v1-noctx oracle closed；读 runs/<arm>/<set> 的名次
  python qa_lme.py judge <set>                            # 全部答卷盲混判分（同一模型、thinking 关、temperature 0）
  python qa_lme.py score <set>                            # 答对率 + 逐题配对（符号检验）+ 检索命中×答对 交叉
  python qa_lme.py cost

LLM：cline-pass/deepseek-v4.1-flash（api.cline.bot，OpenAI 兼容；结果在 .data.choices）。密钥取环境变量
CLINE_API_KEY，只放进请求头，不打印不落盘。每次成功调用费用（含 cached_tokens）记 qa/cost.jsonl；结果按
(model, messages, 关键参数) sha1 缓存在 LINGSHU_LLM_CACHE（重跑不计费，命中记 qa/llm_cache_hits.jsonl）。
材料口径：名次前 k 个轮（被合并的轮已记到首节点），每轮截 1500 字，按写入序（=时间序）排列，带会话日期。
"""
import hashlib, json, math, os, random, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_eval as G  # noqa: E402

QA = os.path.join(HERE, "qa")
#: LLM 结果缓存（各脚本共用）：LINGSHU_LLM_CACHE，默认 /workspace/work/ls/_shared/llm_cache。
#: 键 = sha1(请求体规范 JSON) = sha1(model, messages, max_tokens, temperature, reasoning)；与旧 qa/cache 同一键式，
#: 旧缓存已复制过去（旧目录保留不删）。写入先写唯一临时文件再 os.replace（原子）。
CACHE = os.environ.get("LINGSHU_LLM_CACHE", "/workspace/work/ls/_shared/llm_cache")
HITLOG = os.path.join(QA, "llm_cache_hits.jsonl")
COSTLOG = os.path.join(QA, "cost.jsonl")
URL = "https://api.cline.bot/api/v1/chat/completions"
MODEL = "cline-pass/deepseek-v4.1-flash"
BUDGET = float(os.environ.get("QA_BUDGET", "1.0"))
TURN_CAP = 1500
_lock = threading.Lock()


def total_cost():
    if not os.path.exists(COSTLOG):
        return 0.0
    return sum(json.loads(l)["cost"] for l in open(COSTLOG) if l.strip())


def call(messages, max_tokens=3000, thinking=True, temperature=None, tag=""):
    body = {"model": MODEL, "max_tokens": max(400, max_tokens), "messages": messages}
    if temperature is not None:
        body["temperature"] = temperature
    if not thinking:
        body["reasoning"] = {"enabled": False}
    k = cache_key(body)
    cp = os.path.join(CACHE, k[:2], k + ".json")
    if os.path.exists(cp):
        try:
            got = json.load(open(cp, encoding="utf-8"))
            with _lock:
                with open(HITLOG, "a") as f:
                    f.write(json.dumps({"t": time.time(), "tag": tag, "key": k}) + "\n")
            return got
        except ValueError:                       # 写了一半的旧缓存文件（原子写之前的遗留）：视为未命中，重新请求
            os.remove(cp)
    if total_cost() > BUDGET:
        return {"content": None, "error": "budget"}
    key = os.environ.get("CLINE_API_KEY", "")
    err = None
    for attempt in range(6):
        try:
            req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            d = json.load(urllib.request.urlopen(req, timeout=300))
            data = d.get("data", d)
            m = data["choices"][0]["message"]
            content = m.get("content") or ""
            cost = float(((m.get("provider_metadata") or {}).get("gateway") or {}).get("cost")
                         or (data.get("usage") or {}).get("cost") or 0)
            with _lock:
                os.makedirs(QA, exist_ok=True)
                u = data.get("usage") or {}
                cached = ((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0) + (u.get("prompt_cache_hit_tokens") or 0)
                with open(COSTLOG, "a") as f:
                    f.write(json.dumps({"t": time.time(), "tag": tag, "cost": cost, "prompt_tokens": u.get("prompt_tokens"),
                                        "cached_tokens": cached, "layout": layout(), "usage": u}) + "\n")
            if not content.strip():
                err = "empty"
                continue
            out = {"content": content, "cost": cost}
            _atomic_dump(cp, out)
            return out
        except urllib.error.HTTPError as ex:
            err = f"HTTP {ex.code}: {ex.read()[:200]!r}"
            if ex.code in (401, 402, 403):
                break
        except Exception as ex:  # noqa: BLE001
            err = f"{type(ex).__name__}: {ex}"
        time.sleep(min(120, 5 * 2 ** attempt) if "429" in str(err) else 3 * (attempt + 1))
    return {"content": None, "error": err}


def cache_key(body):
    """sha1(model, messages, 关键参数)：请求体只含这几项，按键排序的 JSON 即规范形。"""
    keep = {x: body[x] for x in ("model", "messages", "max_tokens", "temperature", "reasoning") if x in body}
    return hashlib.sha1(json.dumps(keep, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _atomic_dump(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False)
    os.replace(tmp, p)


def layout():
    """提示布局：prefix（默认，2026-10-12 起）= 固定说明放 system、变量放最后的 user，命中服务端前缀缓存；
    legacy = 修订 2–5 已登记读数所用的单条 user 布局（用于从缓存复现旧读数）。"""
    return os.environ.get("LINGSHU_PROMPT_LAYOUT", "prefix")


def msgs(fixed, variable, legacy_text):
    """fixed：所有调用相同的说明；variable：本题材料与问题。legacy 布局返回旧的单条消息（逐字不变）。"""
    if layout() == "legacy":
        return [{"role": "user", "content": legacy_text}]
    return [{"role": "system", "content": fixed}, {"role": "user", "content": variable}]


def raw():
    d = json.load(open(G.LME, encoding="utf-8"))
    return {x["question_id"]: x for x in d}


def jobs(sset):
    return {j["key"]: j for j in (json.loads(l) for l in open(os.path.join(G.JOBS, f"{sset}.jsonl"), encoding="utf-8") if l.strip())}


def sample(sset, n, seed=20261011):
    meta = json.load(open(os.path.join(G.JOBS, f"meta_{sset}.json")))
    by = {}
    for qid, m in sorted(meta.items()):
        by.setdefault(m["type"], []).append(qid)
    rng = random.Random(seed)
    tot = sum(len(v) for v in by.values())
    pick = []
    for t, v in sorted(by.items()):
        k = max(1, round(n * len(v) / tot))
        pick += rng.sample(v, min(k, len(v)))
    G.dump(os.path.join(QA, f"{sset}_sample.json"), {"seed": seed, "n": len(pick), "qids": sorted(pick)})
    print(len(pick), {t: sum(1 for q in pick if meta[q]["type"] == t) for t in by})


def material(qid, order, J, M, X, k):
    sdate = dict(zip(X["haystack_session_ids"], X["haystack_dates"]))
    docs, s_of = J["docs"], M["s_of"]
    seen, pick = set(), []
    for t in order:
        if t not in seen:
            seen.add(t); pick.append(t)
        if len(pick) >= k:
            break
    lines = []
    for t in sorted(pick):
        txt = docs[t] if len(docs[t]) <= TURN_CAP else docs[t][:TURN_CAP] + " …"
        lines.append(f"[{sdate.get(s_of[t], '?')}] {txt}")
    return lines, pick


ANS = ("You are answering a question about a user's past chat history with an AI assistant. "
       "Below are excerpts (each prefixed with its session date) retrieved from that history; they may be incomplete or irrelevant.\n\n"
       "### Excerpts\n{mat}\n\n### Question (asked on {qdate})\n{q}\n\n"
       "Answer concisely using the excerpts. If the excerpts do not contain the information, say you don't know.")


ANS_FIXED = ("You are answering a question about a user's past chat history with an AI assistant. "
             "The user message contains excerpts (each prefixed with its session date) retrieved from that history; "
             "they may be incomplete or irrelevant, followed by the question and the date it was asked. "
             "Answer concisely using the excerpts. If the excerpts do not contain the information, say you don't know.")


def material_sess(order, J, M, X, ns=3, turn_cap=800, sess_cap=8000):
    """修订 3：按名次取前 ns 个不同会话，整会话按写入序给出（每轮截 turn_cap、每会话截 sess_cap）。"""
    sdate = dict(zip(X["haystack_session_ids"], X["haystack_dates"]))
    docs, s_of = J["docs"], M["s_of"]
    top = []
    for t in order:
        if s_of[t] not in top:
            top.append(s_of[t])
        if len(top) >= ns:
            break
    lines, pick = [], []
    for s in sorted(top, key=lambda z: s_of.index(z)):
        body, used = [], 0
        for i, ss in enumerate(s_of):
            if ss != s:
                continue
            t = docs[i] if len(docs[i]) <= turn_cap else docs[i][:turn_cap] + " …"
            if used + len(t) > sess_cap:
                break
            body.append(t); used += len(t); pick.append(i)
        lines.append(f"[Session on {sdate.get(s, '?')}]\n" + "\n".join(body))
    return lines, pick


def gen(arm, sset, k=10):
    S = json.load(open(os.path.join(QA, f"{sset}_sample.json")))["qids"]
    unit = "turn"
    if arm.endswith("@sess"):
        unit = "sess"
    meta = json.load(open(os.path.join(G.JOBS, f"meta_{sset}.json")))
    J, X = jobs(sset), raw()
    R = {} if arm in ("oracle", "closed") else G.results(arm.split("@")[0], sset)
    outp = os.path.join(QA, f"{sset}_ans_{arm}.json")
    prev = json.load(open(outp)) if os.path.exists(outp) else {}

    def one(qid):
        if qid in prev and prev[qid].get("answer"):
            return qid, prev[qid]
        m, x = meta[qid], X[qid]
        if arm == "closed":
            lines, pick = ["(none)"], []
        else:
            order = m["ans"] if arm == "oracle" else R[qid]["rank"]["q"]
            if unit == "sess":
                lines, pick = material_sess(order, J[qid], m, x)
            else:
                lines, pick = material(qid, order, J[qid], m, x, k)
        msg = ANS.format(mat="\n\n".join(lines), qdate=x["question_date"], q=x["question"])
        mat = "\n\n".join(lines)
        var = f"### Excerpts\n{mat}\n\n### Question (asked on {x['question_date']})\n{x['question']}"
        r = call(msgs(ANS_FIXED, var, msg), max_tokens=3000, tag=f"gen:{arm}")
        hit = bool(set(pick) & set(m["ans"]))
        return qid, {"answer": r.get("content"), "error": r.get("error"), "picked": pick, "ans_turn_hit": hit,
                     "mat_chars": sum(len(s) for s in lines)}

    with ThreadPoolExecutor(4) as ex:
        res = dict(ex.map(one, S))
    G.dump(outp, res)
    ok = sum(1 for v in res.values() if v.get("answer"))
    print(arm, sset, "answered", ok, "/", len(S), "cost_total %.4f" % total_cost())


JUDGE = {
    "default": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no.",
    "temporal-reasoning": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. In addition, do not penalize off-by-one errors for the number of days. If the question asks for the number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the model's response is still correct.",
    "knowledge-update": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.",
    "single-session-preference": "I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.",
}


def judge(sset, jname="J1"):
    X = raw()
    meta = json.load(open(os.path.join(G.JOBS, f"meta_{sset}.json")))
    arms = sorted(f[len(sset) + 5:-5] for f in os.listdir(QA) if f.startswith(f"{sset}_ans_"))
    jobs_ = []
    for a in arms:
        A = json.load(open(os.path.join(QA, f"{sset}_ans_{a}.json")))
        for qid, v in A.items():
            if v.get("answer"):
                jobs_.append((a, qid, v["answer"]))
    random.Random(7 if jname == "J1" else 29).shuffle(jobs_)  # 盲混：判官看不到臂名，题序打乱

    def one(j):
        a, qid, ans = j
        x = X[qid]; t = meta[qid]["type"]
        inst = JUDGE.get(t, JUDGE["default"])
        lab = "Rubric" if t == "single-session-preference" else "Correct Answer"
        msg = f"{inst}\n\nQuestion: {x['question']}\n\n{lab}: {x['answer']}\n\nModel Response: {ans}\n\nIs the model response correct? Answer yes or no only."
        var = f"Question: {x['question']}\n\n{lab}: {x['answer']}\n\nModel Response: {ans}\n\nIs the model response correct? Answer yes or no only."
        r = call(msgs(inst, var, msg), max_tokens=400, thinking=False,
                 temperature=0.0 if jname == "J1" else 0.6, tag="judge" if jname == "J1" else "judge2")
        c = (r.get("content") or "").strip().lower()
        return a, qid, (None if not c else c.startswith("yes") or c.split()[0].strip(".*") == "yes")

    with ThreadPoolExecutor(4) as ex:
        out = list(ex.map(one, jobs_))
    J = {}
    for a, qid, v in out:
        J.setdefault(a, {})[qid] = v
    G.dump(os.path.join(QA, f"{sset}_judge{'' if jname == 'J1' else '_J2'}.json"), J)
    print({a: f"{sum(1 for v in d.values() if v)}/{len(d)}" for a, d in J.items()}, "cost_total %.4f" % total_cost())


def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def score(sset, jname="J1"):
    suf = "" if jname == "J1" else "_J2"
    J = json.load(open(os.path.join(QA, f"{sset}_judge{suf}.json")))
    meta = json.load(open(os.path.join(G.JOBS, f"meta_{sset}.json")))
    S = json.load(open(os.path.join(QA, f"{sset}_sample.json")))["qids"]
    arms = sorted(J)
    out = {"n": len(S), "acc": {}, "by_type": {}, "pairs": {}, "hit_x_correct": {}}
    for a in arms:
        v = [bool(J[a].get(q)) for q in S]
        out["acc"][a] = round(sum(v) / len(S), 4)
        bt = {}
        for q in S:
            bt.setdefault(meta[q]["type"], []).append(bool(J[a].get(q)))
        out["by_type"][a] = {t: f"{sum(x)}/{len(x)}" for t, x in sorted(bt.items())}
        A = json.load(open(os.path.join(QA, f"{sset}_ans_{a}.json")))
        cx = {}
        for q in S:
            h = A.get(q, {}).get("ans_turn_hit")
            cx.setdefault(f"hit={h}", [0, 0])[0 if J[a].get(q) else 1] += 1
        out["hit_x_correct"][a] = {k: {"correct": c, "wrong": w} for k, (c, w) in sorted(cx.items())}
    for a in arms:
        for b in arms:
            if a < b:
                w = sum(1 for q in S if J[a].get(q) and not J[b].get(q))
                l = sum(1 for q in S if J[b].get(q) and not J[a].get(q))
                out["pairs"][f"{a} vs {b}"] = {"a_only": w, "b_only": l, "sign_p": round(sign_p(w, l), 4)}
    other = os.path.join(QA, f"{sset}_judge{'_J2' if jname == 'J1' else ''}.json")
    if os.path.exists(other):
        O = json.load(open(other))
        ag = {a: (sum(1 for q in S if q in O.get(a, {}) and bool(J[a].get(q)) == bool(O[a].get(q))),
                  sum(1 for q in S if q in O.get(a, {}))) for a in arms}
        out["judge_agreement"] = {a: f"{x}/{n}" for a, (x, n) in ag.items()}
    out["judge"] = jname
    out["cost_usd_total"] = round(total_cost(), 4)
    G.dump(os.path.join(G.OUT, f"qa_{sset}{suf}.json"), out)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    a = sys.argv[1:]
    kw = {}
    if "--k" in a:
        i = a.index("--k"); kw["k"] = int(a[i + 1]); del a[i:i + 2]
    if "--seed" in a:
        i = a.index("--seed"); seed = int(a[i + 1]); del a[i:i + 2]
    else:
        seed = 20261011
    if a[0] == "sample":
        sample(a[1], int(a[2]), seed)
    elif a[0] == "gen":
        gen(a[1], a[2], **kw)
    elif a[0] == "judge":
        judge(a[1], a[2] if len(a) > 2 else "J1")
    elif a[0] == "score":
        score(a[1], a[2] if len(a) > 2 else "J1")
    elif a[0] == "cost":
        print("%.4f" % total_cost())
