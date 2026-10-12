# -*- coding: utf-8 -*-
"""T1-H2 第二版（PREREG_ZH 修订 3a）：全部 157 个未用章对、每对 1 题、共同对象、拼接词过滤、单章必要性 LLM 复核。
复用 t1h_gen 的语料、章对、校验与划分（T1H_SET=h2）。只读语料，不读任何臂。
  T1H_SET=h2 python t1h2_gen.py gen | build | verify | sample | split [坏题...]"""
import itertools, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
os.environ["T1H_SET"] = "h2"
import t1h_gen as G  # noqa: E402
L = G.L; HR = G.HR
GSEED2 = 10
RULE = """你是中文长篇阅读理解评测的出题人。下面会给出同一部小说的两个章节（章节 A、章节 B），每章按块编号。
请出 1 道「必须同时用到两章信息才能完整回答」的问题，用于检验检索系统能否把分散在不同章节的证据都找回来。步骤与要求：
1. 先找出一个在两章原文中**都逐字出现**的「共同对象」（人物名、事物名、组织名、地名或设定名），把它原样写在 shared 字段里。
   题目只问关于这一个对象的**一个**问题：例如它在一章里被设立/提出/埋下原因，在另一章里产生结果/被揭示/被补充。
2. 严禁拼接：不许把两章各问一半，不许出现「分别」「各自」「两个世界」「两处」「相似」「共同说明」「另一方面」这类拼接或类比措辞；
   一道题只能有一个中心问题（最多两个问号，且第二问必须是第一问的追问）。
3. 问具体、可核对的事实或因果（谁、什么、为什么、怎样、结果如何），不问看法或感受。
4. 给 2–4 条 gold 证据句：从原文逐字复制（可截取一句的一部分，8–60 字），每条只来自一个块，两章各至少 1 条；每条都必要。
   在 why_not_A_only / why_not_B_only 里写清：只读章节 A 缺什么、只读章节 B 缺什么。若任一章单独就能答全，换题；找不到就返回 {"items":[]}。
5. 给 1–2 条「误用干扰」句：逐字摘自原文，与题面共享词语或同名不同所指，看似相关但用它作答会出错；不能是证据句或与证据同处。说明理由。
6. 题面用自己的话，自然口语，不照抄原文连续 8 字以上，不出现块编号或「章节 A/B」。
只输出 JSON（不要代码块标记），格式：
{"items":[{"shared":"…","question":"…","answer":"…","why_not_A_only":"…","why_not_B_only":"…","evidence":[{"block":"A-3","quote":"…"}],"distractors":[{"block":"B-7","quote":"…","reason":"…"}]}]}"""
BAN = re.compile(r"分别|各自|两个世界|两处|相似|共同说明|另一方面|有何异同|有什么共同")
VER = """你是严格的阅读理解审核员。下面只给出小说的一个章节和一道题。请判断：**仅凭这一章**能否完整回答这道题（不得用常识或猜测补全）。
只输出 JSON：{"answerable":"full"|"partial"|"none","missing":"…（缺什么，一句话）"}"""


def allpairs(by):
    cids = sorted(by, key=lambda c: (c.split("_")[0], int(c.split("_c")[1])))
    used = {tuple(json.loads(l)["pair"]) for l in open(os.path.join(G.HERE, "t1h", "raw.jsonl"), encoding="utf-8")}
    return [p for p in itertools.combinations(cids, 2) if p not in used]


def gen():
    ch, by = G.chapters()
    P = allpairs(by)

    def one(p):
        r = L.call([{"role": "system", "content": RULE}, {"role": "user", "content": G.user_msg(ch, by, *p)}],
                   max_tokens=2000, temperature=0.3, seed=GSEED2, thinking=False, tag="t1h2_gen")
        return {"pair": list(p), "content": r.get("content"), "error": r.get("error")}
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(one, P))
    with open(os.path.join(G.OUT, "raw.jsonl"), "w", encoding="utf-8") as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("pairs", len(P), "errors", sum(1 for r in res if not r["content"]), L.spend())


def build():
    G.CAP = 10 ** 9
    G.build()
    ch, by = G.chapters()
    C = json.load(open(os.path.join(G.OUT, "cands.json"), encoding="utf-8"))
    kept, why = [], dict(C["dropped"])
    for c in C["cards"]:
        a, b = c["pair"]
        sh = HR.norm(c.get("shared", ""))
        txt = {x: "".join(ch[i]["n"] for i in by[x]) for x in (a, b)}
        if len(sh) < 2 or sh not in txt[a] or sh not in txt[b]:
            why["共同对象不在两章"] = why.get("共同对象不在两章", 0) + 1; continue
        if BAN.search(c["question"]) or c["question"].count("？") + c["question"].count("?") > 2:
            why["拼接措辞/问号>2"] = why.get("拼接措辞/问号>2", 0) + 1; continue
        kept.append(c)
    json.dump({"cards": kept, "dropped": why}, open(os.path.join(G.OUT, "cands_pre.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("prefilter kept", len(kept), why)


def _verdict(s):
    m = re.search(r'"answerable"\s*:\s*"(\w+)"', s or "")
    return m.group(1) if m else "parse_fail"


def verify():
    ch, by = G.chapters()
    C = json.load(open(os.path.join(G.OUT, "cands_pre.json"), encoding="utf-8"))
    jobs = [(k, x) for k, c in enumerate(C["cards"]) for x in c["pair"]]

    def one(j):
        k, x = j
        c = C["cards"][k]
        body = "【章节】\n" + "\n".join(f"[{n}] " + re.sub(r"\s+", " ", ch[i]["text"]).strip() for n, i in enumerate(by[x], 1))
        r = L.call([{"role": "system", "content": VER}, {"role": "user", "content": body + "\n\n【题目】" + c["question"]}],
                   max_tokens=400, temperature=0, seed=GSEED2, thinking=False, tag="t1h2_verify")
        return k, x, _verdict(r.get("content"))
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(one, sorted(jobs, key=lambda j: j[1])))
    v = {}
    for k, x, r in res:
        v.setdefault(k, {})[x] = r
    kept, why = [], dict(C["dropped"])
    for k, c in enumerate(C["cards"]):
        c["verify"] = v[k]
        if any(r == "full" for r in v[k].values()):
            why["单章可答(复核)"] = why.get("单章可答(复核)", 0) + 1; continue
        if any(r == "parse_fail" for r in v[k].values()):
            why["复核解析失败"] = why.get("复核解析失败", 0) + 1; continue
        kept.append(c)
    kept = kept[:100]
    for k, c in enumerate(kept):
        c["qid"] = c["hid"] = f"k{k + 1:03d}"
    json.dump({"cards": kept, "dropped": why}, open(os.path.join(G.OUT, "cands.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("kept", len(kept), why, {s: sum(c["stratum"] == s for c in kept) for s in ("same_unit", "cross_unit")}, L.spend())


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "sample":
        G.GSEED = GSEED2; G.sample()
    elif cmd == "split":
        G.split(sys.argv[2:])
    else:
        {"gen": gen, "build": build, "verify": verify}[cmd]()
