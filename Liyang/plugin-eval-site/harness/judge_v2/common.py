"""判分器 v2 候选 · 公用件：实体/数值抽取、判官证词机械校验、调用缓存、合成金丝雀行。

只新增，不改原判分器（harness/judge.py、harness/examA.py、上游 hmb/judge.py|semantic.py 原样保留）。
"""
from __future__ import annotations
import difflib, hashlib, json, math, os, re, threading
from concurrent.futures import ThreadPoolExecutor

V2_VERSION = "judge-v2-candidate-0.1"

_PUNCT = re.compile(r"[\W_]+", re.U)


def norm(s: str) -> str:
    """归一化：小写、去空白与标点（同上游 judge.norm 的精神；本模块独立实现，不依赖上游）。"""
    return _PUNCT.sub("", (s or "").lower())


def opaque(batch_tag: str, key: str) -> str:
    """不透明行号：锚、金丝雀、考题在合并/计分循环里不可区分（防"只对考题动手"的定向缺陷）。"""
    return "r" + hashlib.sha1(f"{batch_tag}\x00{key}".encode()).hexdigest()[:12]


# ---------------- 硬实体：数字 / 拉丁词 ----------------
_NUM = re.compile(r"\d+(?:\.\d+)?")
_LAT = re.compile(r"[A-Za-z][A-Za-z0-9_\-]*(?:\([A-Za-z]\))?")


def hard_tokens(s: str) -> dict:
    s = s or ""
    lat = {m.group(0).lower() for m in _LAT.finditer(s) if len(m.group(0)) >= 2 or "(" in m.group(0)}
    num = {m.group(0) for m in _NUM.finditer(s)}
    return {"num": num, "lat": lat}


def aligned_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b), autojunk=False).ratio()


def hard_conflict(ref: str, ans: str, align_min: float = 0.6) -> list[dict]:
    """确定性替换检测：答案与参照"同句式"（字符对齐率 ≥ align_min）且同类硬实体（数字/拉丁词）
    参照有而答案无、答案有而参照无 ⇒ 判替换。只在对齐时触发，避免把无关答案里的数字当冲突。"""
    if aligned_ratio(ref, ans) < align_min:
        return []
    tr, ta = hard_tokens(ref), hard_tokens(ans)
    out = []
    for t in ("num", "lat"):
        gone = sorted(tr[t] - ta[t]); new = sorted(ta[t] - tr[t])
        # 拉丁词大小写已统一；数字须答案里不以子串形式出现（避免 "10.4" vs "10"）
        if t == "num":
            gone = [g for g in gone if not any(g in x for x in ta[t])]
            new = [n for n in new if not any(n in x for x in tr[t])]
        if gone and new:
            out.append({"type": t, "ref": gone, "ans": new})
    return out


NEG_HINT = ("不", "没", "别", "放弃", "取消", "停止", "拒绝", "无需", "算了", "非", "否")


def verify_pair(ref_span: str, ans_span: str, ref_text: str, ans_text: str) -> tuple[bool, str]:
    """判官声称的"替换/矛盾"对必须机械可证：ref 逐字在参照里、ans 逐字在答案里、ans 不在参照里；
    且 ref 不在答案里（真替换），或 ans 带否定（相反断言）。"""
    nr, na = norm(ref_span), norm(ans_span)
    R, A = norm(ref_text), norm(ans_text)
    if not nr or not na:
        return False, "空片段"
    if nr not in R:
        return False, "ref 不在参照中"
    if na not in A:
        return False, "ans 不在答案中"
    if na in R:
        return False, "ans 本身在参照中（不是替换）"
    if nr in A and not any(h in ans_span for h in NEG_HINT):
        return False, "ref 仍在答案中且 ans 无否定（是补充不是替换）"
    return True, ""


# ---------------- 一致率 ----------------
def kappa(a, b):
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    cats = set(a) | set(b)
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return 1.0 if pe >= 1 else (po - pe) / (1 - pe)


def agreement(a, b):
    if not a:
        return {"n": 0, "agree": None, "kappa": None}
    ag = sum(x == y for x, y in zip(a, b)) / len(a)
    k = kappa(a, b)
    return {"n": len(a), "agree": round(ag, 4), "kappa": None if math.isnan(k) else round(k, 4)}


# ---------------- 调用缓存 + 并发执行 ----------------
class CallCache:
    """判官原始回复缓存（JSONL，键=(instance, task, key)）。解析在读取时做——解析器修订不需要重调模型，
    但任何解析器修订都必须在报告里登记。"""

    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.Lock()
        self.d = {}
        if os.path.exists(self.path):
            for line in open(self.path, encoding="utf-8"):
                try:
                    x = json.loads(line)
                    self.d[(x["instance"], x["task"], x["key"])] = x
                except (json.JSONDecodeError, KeyError):
                    pass

    def get(self, inst, task, key):
        return self.d.get((inst, task, key))

    def put(self, rec):
        with self.lock:
            self.d[(rec["instance"], rec["task"], rec["key"])] = rec
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_jobs(jobs, cache: CallCache, client_for, rec, concurrency=4, budget=None, counter=None):
    """jobs: [{"instance","task","key","messages","tag"}]；命中缓存不调。返回 {(inst,task,key): raw}。
    budget/counter：本进程新调用上限（超出即停，未完成的 job 不返回）。"""
    out, todo = {}, []
    for j in jobs:
        h = cache.get(j["instance"], j["task"], j["key"])
        if h is not None:
            out[(j["instance"], j["task"], j["key"])] = h["raw"]
        else:
            todo.append(j)
    lock = threading.Lock()
    counter = counter if counter is not None else {"n": 0}

    def go(j):
        with lock:
            if budget is not None and counter["n"] >= budget:
                return None
            counter["n"] += 1
        cl = client_for(j["instance"])
        r = cl.chat(j["messages"], rec, tag=j["tag"])
        ev = None
        if rec is not None:
            ev = rec.event("judge_v2.raw", instance=j["instance"], task=j["task"], key=j["key"], raw=r["content"])
        cache.put({"instance": j["instance"], "task": j["task"], "key": j["key"], "raw": r["content"],
                   "ev": ev and {"seq": ev["seq"], "t": ev["t"]}, "usage": r.get("usage")})
        return (j["instance"], j["task"], j["key"]), r["content"]

    if todo:
        with ThreadPoolExecutor(concurrency) as ex:
            for res in ex.map(go, todo):
                if res:
                    out[res[0]] = res[1]
    return out, len(todo), counter["n"]
