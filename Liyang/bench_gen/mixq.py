# -*- coding: utf-8 -*-
"""中英混合查询的路由边界（PREREG 修订 2·C；只用 dev）。

  python mixq.py make <set>          # set ∈ loc_dev lme_dev：LLM 把英文问句改写成两种中文用户写法 → qa/mixq_<set>.json
  python mixq.py jobs <set>          # 生成检索 job（原句 + 变体），写 /tmp/gen_jobs/mix_<set>.jsonl + meta
  python mixq.py score <tag> <set>   # 按变体 × cjk_ratio 分箱打分

变体：
  en      原英文问句
  wrap    机械：「请帮我查一下：<原句>」（只加中文外壳，内容词不变）
  mix     LLM：中文句式，人名/专有名词/关键名词保持英文原词（中国用户常见的夹英文写法）
  zh      LLM：整句中文，人名保留英文拼写，其余全部译成中文
"""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_eval as G  # noqa: E402
import qa_lme as Q  # noqa: E402

PROMPT = ("Rewrite the English question below in two ways a Chinese-speaking user might type it into a memory search box.\n"
          "1) \"mix\": Chinese sentence structure, but keep person names, proper nouns and the key content nouns/terms in their original English words.\n"
          "2) \"zh\": fully Chinese, keep only person names in their original English spelling; translate everything else.\n"
          "Do not add information. Output JSON only: {{\"mix\": \"...\", \"zh\": \"...\"}}\n\nQuestion: {q}")


def questions(sset):
    out = []
    for l in open(os.path.join(G.JOBS, f"{sset}.jsonl"), encoding="utf-8"):
        if l.strip():
            j = json.loads(l)
            for q in j["queries"]:
                out.append((j["key"], q["qid"], q["q"]))
    return out


def make(sset):
    qs = questions(sset)
    outp = os.path.join(Q.QA, f"mixq_{sset}.json")
    prev = json.load(open(outp)) if os.path.exists(outp) else {}

    def one(x):
        key, qid, q = x
        k = f"{key}|{qid}"
        if k in prev and prev[k].get("mix"):
            return k, prev[k]
        fixed = PROMPT.format(q="").rsplit("\n\nQuestion: ", 1)[0]         # 固定说明在前（system），问句在后（user）
        r = Q.call(Q.msgs(fixed, f"Question: {q}", PROMPT.format(q=q)), max_tokens=600, thinking=False, temperature=0.0,
                   tag=f"mixq:{sset}")
        c = r.get("content") or ""
        m = re.search(r"\{.*\}", c, re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
        except ValueError:
            d = {}
        return k, {"en": q, "mix": d.get("mix"), "zh": d.get("zh"), "err": r.get("error")}

    with ThreadPoolExecutor(int(os.environ.get("MIXQ_THREADS", "4"))) as ex:   # 线程数不影响输出（逐题缓存）
        res = dict(ex.map(one, qs))
    G.dump(outp, res)
    print(sset, "ok", sum(1 for v in res.values() if v.get("mix") and v.get("zh")), "/", len(res), "cost_total %.4f" % Q.total_cost())


VARS = ("en", "wrap", "mix", "zh")


def jobs(sset):
    M = json.load(open(os.path.join(Q.QA, f"mixq_{sset}.json")))
    out = open(os.path.join(G.JOBS, f"mix_{sset}.jsonl"), "w", encoding="utf-8")
    for l in open(os.path.join(G.JOBS, f"{sset}.jsonl"), encoding="utf-8"):
        if not l.strip():
            continue
        j = json.loads(l)
        qs = []
        for q in j["queries"]:
            v = M.get(f"{j['key']}|{q['qid']}", {})
            texts = {"en": q["q"], "wrap": "请帮我查一下：" + q["q"], "mix": v.get("mix"), "zh": v.get("zh")}
            for name in VARS:
                if texts[name]:
                    qs.append({"qid": f"{q['qid']}#{name}", "q": texts[name], "limit": q["limit"]})
        j["queries"] = qs
        out.write(json.dumps(j, ensure_ascii=False) + "\n")
    out.close()
    print("jobs written")


def score(tag, sset):
    """按 run tag（可带 @扫描名）读名次；用 gen_eval 的口径对每个变体打分，并按 cjk_ratio 分箱。"""
    sys.path.insert(0, os.path.dirname(HERE))
    from lingshu_ng import lexical as L
    data, split = sset.split("_")
    meta = json.load(open(os.path.join(G.JOBS, f"meta_{data}_{split}.json"), encoding="utf-8"))
    R = G.results(tag, f"mix_{sset}")
    J = {json.loads(l)["key"]: json.loads(l) for l in open(os.path.join(G.JOBS, f"mix_{sset}.jsonl"), encoding="utf-8") if l.strip()}
    rows = []
    for key, r in R.items():
        qtext = {q["qid"]: q["q"] for q in J[key]["queries"]}
        for qq, order in r["rank"].items():
            qid, var = qq.split("#")
            if data == "loc":
                ev = set(meta[key][qid]["ev"])
                v = len(ev & set(order[:10])) / len(ev)
            else:
                m = meta[key]
                so, seen = [], set()
                for t in order:
                    s = m["s_of"][t]
                    if s not in seen:
                        seen.add(s); so.append(s)
                v = float(bool(set(m["gold"]) & set(so[:5])))
            rows.append({"key": key, "qid": qid, "var": var, "v": v, "ratio": L.cjk_ratio(qtext[qq]),
                         "lex": L.is_latin_query(qtext[qq], L.LexicalConfig())})
    return rows


def analyze(sset, cfgs=("route", "force_lex", "force_old"), tag="mix"):
    import statistics
    out = {"set": sset, "metric": "r@10" if sset.startswith("loc") else "s@5", "by_var": {}, "bins": {}}
    allrows = {c: score(f"{tag}@{c}", sset) for c in cfgs}
    for c, rows in allrows.items():
        for var in VARS:
            v = [r["v"] for r in rows if r["var"] == var]
            if v:
                out["by_var"].setdefault(var, {})[c] = round(statistics.mean(v), 4)
                out["by_var"][var]["n"] = len(v)
                out["by_var"][var]["routed_lex"] = sum(1 for r in rows if r["var"] == var and r["lex"])
                out["by_var"][var]["ratio_median"] = round(statistics.median(r["ratio"] for r in rows if r["var"] == var), 3)
    edges = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.01]
    for c, rows in allrows.items():
        for lo, hi in zip(edges, edges[1:]):
            v = [r["v"] for r in rows if lo <= r["ratio"] < hi]
            if v:
                out["bins"].setdefault(f"[{lo},{hi})", {"n": len(v)})[c] = round(statistics.mean(v), 4)
    G.dump(os.path.join(G.OUT, f"mix_{sset}{'' if tag == 'mix' else '_' + tag}.json"), out)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "make":
        make(a[1])
    elif a[0] == "jobs":
        jobs(a[1])
    elif a[0] == "analyze":
        analyze(a[1], tuple(a[3].split(",")) if len(a) > 3 else ("route", "force_lex", "force_old"), a[2] if len(a) > 2 else "mix")
