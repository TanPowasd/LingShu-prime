# -*- coding: utf-8 -*-
"""T1-H 保留集生成（PREREG_ZH 修订 2 §2.1）。只读 hive 语料，不读任何臂的排序/读数。
  python t1h_gen.py gen      # 调 LLM（共享缓存）→ t1h/raw.jsonl
  python t1h_gen.py build    # 自动校验 → t1h/cands.json（+ 丢弃原因统计）
  python t1h_gen.py sample   # 抽查 12 题 → t1h/spot.md
  python t1h_gen.py split [坏题 hid ...]   # 删坏题、划分 → t1h/t1h.json（dev/test）"""
import hashlib, itertools, json, os, random, re, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import zh_eval as Z  # noqa: E402  （只用其语料加载）
import llm_zh as L  # noqa: E402
HR = Z.HR
H2 = os.environ.get("T1H_SET") == "h2"   # PREREG_ZH 修订 3：T1-H2 保留集（新章对、新种子）
OUT = os.path.join(HERE, "t1h2" if H2 else "t1h")
SEED = 20261112 if H2 else 20261012
NPAIR = 64
GSEED = 9 if H2 else 8          # T1-H 第二版（修订 2a）为 8；第一版为 7
CAP = 100          # 修订 3a：T1-H2 第二版由 t1h2_gen.py 先全量过滤再截 100
EXTRA = int(os.environ.get("T1H_EXTRA", "0"))   # 不足 60 题时续抽的章对数（修订 2a）

SYS = """你是中文长篇阅读理解评测的出题人。下面会给出同一部小说的两个章节（章节 A、章节 B），每章按块编号。
请出最多 2 道「必须同时用到两章信息才能完整回答」的问题，用于检验检索系统能否把分散在不同章节的证据都找回来。要求：
1. 两章的信息必须围绕同一个人物/事物/事件/概念/设定（例如：同一事物在两章中的不同交代、一件事的起因在一章而结果在另一章、同一设定的前后补充）。
   不许拿两段无关场景作类比或「有什么相似之处」来硬凑。
2. 问具体、可核对的事实或因果（谁、什么、为什么、怎样、结果如何），不要问「看法如何变化」「有何感受」这类空泛题。
3. 每题给 2–4 条 gold 证据句：必须从原文逐字复制（可以只截取一句中的一部分，8–60 字），每条只能来自一个块，两章各至少 1 条。
   每条证据都必须是必要的：删去任何一条，答案就不完整；只读其中一章绝对答不全。
4. 每题给 1–2 条「误用干扰」句：同样逐字摘自原文（两章中任一处），它与题面共享词语、或是同名不同义/同词不同所指，看上去相关但用它作答会出错；
   不能是证据句本身，也不能与证据句出自同一块的同一处。说明干扰理由。
5. 题面用自己的话，自然口语，不要照抄原文连续 8 个字以上，不要出现块编号或「章节 A/B」字样。
6. 两道题必须考不同的内容。如果这两章找不到真正关联的内容，只出 1 道或返回空列表 {"items":[]}，不要硬凑。
__H2RULE__只输出 JSON（不要代码块标记），格式：
{"items":[{"question":"…","answer":"…（一两句）","evidence":[{"block":"A-3","quote":"…"}],"distractors":[{"block":"B-7","quote":"…","reason":"…"}]}]}"""
SYS = SYS.replace("__H2RULE__", "7. 不要出把两章各问一半、用「分别/各自/两处」拼在一起的题；两章证据必须共同回答同一个问题。\n" if H2 else "")


def chapters():
    ch = Z.data()["tc"]
    by = {}
    for i, c in enumerate(ch):
        by.setdefault(c["cid"], []).append(i)
    return ch, by


def pairs(by):
    cids = sorted(by, key=lambda c: (c.split("_")[0], int(c.split("_c")[1])))
    allp = list(itertools.combinations(cids, 2))
    if H2:   # 去掉 T1-H 已用的 96 对
        used = {tuple(json.loads(l)["pair"]) for l in open(os.path.join(HERE, "t1h", "raw.jsonl"), encoding="utf-8")}
        allp = [p for p in allp if p not in used]
    same = [p for p in allp if p[0][:3] == p[1][:3]]
    cross = [p for p in allp if p[0][:3] != p[1][:3]]
    rng = random.Random(SEED)
    ns = round(NPAIR * len(same) / len(allp))
    pick = rng.sample(same, ns) + rng.sample(cross, NPAIR - ns)
    order = {c: k for k, c in enumerate(cids)}
    pick = sorted(pick, key=lambda p: (order[p[0]], order[p[1]]))
    if EXTRA:
        rest = [p for p in allp if p not in set(pick)]
        more = random.Random(SEED + 1).sample(rest, EXTRA)
        pick += sorted(more, key=lambda p: (order[p[0]], order[p[1]]))
    return pick   # 同一章节 A 相邻 → 服务端前缀缓存


def user_msg(ch, by, a, b):
    parts = []
    for tag, cid in (("A", a), ("B", b)):
        parts.append(f"【章节 {tag}】")
        for k, i in enumerate(by[cid], 1):
            parts.append(f"[{tag}-{k}] " + re.sub(r"\s+", " ", ch[i]["text"]).strip())
    return "\n".join(parts)


def gen():
    ch, by = chapters()
    P = pairs(by)
    os.makedirs(OUT, exist_ok=True)

    def one(p):
        a, b = p
        r = L.call([{"role": "system", "content": SYS}, {"role": "user", "content": user_msg(ch, by, a, b)}],
                   max_tokens=2400, temperature=0.3, seed=GSEED, thinking=False, tag="t1h_gen")
        return {"pair": [a, b], "content": r.get("content"), "error": r.get("error")}
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, P))
    with open(os.path.join(OUT, "raw.jsonl"), "w", encoding="utf-8") as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("pairs", len(P), "errors", sum(1 for r in res if not r["content"]), L.spend())


def _parse(s):
    s = (s or "").strip()
    s = re.sub(r"^```(json)?|```$", "", s, flags=re.M).strip()
    try:
        return json.loads(s).get("items") or []
    except (ValueError, AttributeError):
        m = re.search(r"\{.*\}", s, re.S)
        try:
            return json.loads(m.group(0)).get("items") or [] if m else []
        except ValueError:
            return []


def _locate(q, ch, cand):
    nq = HR.norm(q)
    hits = [i for i in cand if nq and nq in ch[i]["n"]]
    return nq, hits


def _lcs_ge(a, b, k):
    return any(a[i:i + k] in b for i in range(len(a) - k + 1))


def build():
    ch, by = chapters()
    allidx = range(len(ch))
    kept, why = [], {}
    old = json.load(open(os.path.join(HERE, "t1h", "t1h.json"), encoding="utf-8"))["cards"] if H2 else []
    def drop(r):
        why[r] = why.get(r, 0) + 1
    for line in open(os.path.join(OUT, "raw.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        a, b = r["pair"]
        for it in _parse(r["content"]):
            q = (it.get("question") or "").strip()
            if not q:
                drop("空题"); continue
            ev, ok = [], True
            for e in it.get("evidence") or []:
                nq, hits = _locate(e.get("quote", ""), ch, by[a] + by[b])
                if not hits:
                    nq, hits = _locate(e.get("quote", ""), ch, allidx)
                if not hits or not (8 <= len(nq) <= 80):
                    ok = False; break
                ev.append({"cid": ch[hits[0]]["cid"], "chunks": hits, "quote": e["quote"].strip(), "weight": "primary"})
            if not ok or len(ev) < 2:
                drop("证据非原文/长度/不足2条"); continue
            if len({e["cid"] for e in ev}) < 2:
                drop("证据不跨章"); continue
            nqs = [HR.norm(e["quote"]) for e in ev]
            if len(set(nqs)) < len(nqs):
                drop("证据重复"); continue
            qn = HR.norm(q)
            if any(_lcs_ge(qn, x, 8) for x in nqs):
                drop("题面照抄≥8字"); continue
            me = []
            for d in it.get("distractors") or []:
                nd, hits = _locate(d.get("quote", ""), ch, by[a] + by[b])
                if not hits or len(nd) < 4:
                    continue
                if any(nd in x or x in nd for x in nqs):
                    continue
                if any(set(hits) & set(e["chunks"]) and (nd in ch[h]["n"]) for e in ev for h in e["chunks"] if h in hits) and \
                        any(abs(ch[hits[0]]["n"].find(nd) - ch[hits[0]]["n"].find(x)) < len(x) + len(nd) for x in nqs if x in ch[hits[0]]["n"]):
                    continue   # 与证据同块且位置重叠
                me.append({"cid": ch[hits[0]]["cid"], "chunks": hits, "quote": d["quote"].strip(), "reason": d.get("reason", "")})
            if not me:
                drop("无有效干扰句"); continue
            bg = set(HR.bigrams(q))
            evs = set(nqs)
            if any(len(evs & {HR.norm(e["quote"]) for e in k["supporting_evidence"]}) >= 2 for k in kept) or \
                    any(len(bg & set(HR.bigrams(k["question"]))) / max(1, len(bg | set(HR.bigrams(k["question"])))) >= .5 for k in kept):
                drop("重复题"); continue
            if any(len(evs & {HR.norm(e["quote"]) for e in k["supporting_evidence"]}) >= 2 for k in old) or \
                    any(len(bg & set(HR.bigrams(k["question"]))) / max(1, len(bg | set(HR.bigrams(k["question"])))) >= .5 for k in old):
                drop("与T1-H重复"); continue
            kept.append({"question": q, "answer": it.get("answer", ""), "pair": [a, b],
                         "stratum": "same_unit" if a[:3] == b[:3] else "cross_unit",
                         "supporting_evidence": ev, "must_exclude": me,
                         **({"shared": it.get("shared", ""), "why_a": it.get("why_not_A_only", ""), "why_b": it.get("why_not_B_only", "")} if H2 else {})})
    kept = kept[:CAP]
    for k, c in enumerate(kept):
        c["qid"] = c["hid"] = f"{'k' if H2 else 'h'}{k + 1:03d}"
    json.dump({"cards": kept, "dropped": why}, open(os.path.join(OUT, "cands.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("kept", len(kept), "dropped", why, {s: sum(c["stratum"] == s for c in kept) for s in ("same_unit", "cross_unit")})


def sample():
    ch, _ = chapters()
    C = json.load(open(os.path.join(OUT, "cands.json"), encoding="utf-8"))["cards"]
    pick = sorted(random.Random(SEED + GSEED).sample(range(len(C)), 12))
    L_ = []
    for k in pick:
        c = C[k]
        L_.append(f"## {c['hid']}（{c['pair']}，{c['stratum']}）\nQ：{c['question']}\nA：{c['answer']}")
        for e in c["supporting_evidence"]:
            L_.append(f"- 证据 [{e['cid']}] {e['quote']}\n  块：{ch[e['chunks'][0]]['text'].strip()[:400]}")
        for e in c["must_exclude"]:
            L_.append(f"- 干扰 [{e['cid']}] {e['quote']} —— {e['reason']}")
        L_.append("")
    open(os.path.join(OUT, "spot.md"), "w", encoding="utf-8").write("\n".join(L_))
    print([C[k]["hid"] for k in pick])


def split(bad):
    C = [c for c in json.load(open(os.path.join(OUT, "cands.json"), encoding="utf-8"))["cards"] if c["hid"] not in bad]
    dev, test = [], []
    for s in ("same_unit", "cross_unit"):
        xs = sorted((c for c in C if c["stratum"] == s), key=lambda c: hashlib.sha1(f"{SEED}:{c['hid']}".encode()).hexdigest())
        nd = round(0.4 * len(xs))
        dev += [c["hid"] for c in xs[:nd]]; test += [c["hid"] for c in xs[nd:]]
    json.dump({"cards": C, "dev": sorted(dev), "test": sorted(test), "removed_after_spot": bad},
              open(os.path.join(OUT, "t1h.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("n", len(C), "dev", len(dev), "test", len(test))


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"gen": gen, "build": build, "sample": sample}.get(cmd, lambda: split(sys.argv[2:]))()
