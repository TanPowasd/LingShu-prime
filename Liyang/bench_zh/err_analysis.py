# -*- coding: utf-8 -*-
"""误差分析（只用 dev 31 卡）：base0（05003d3）在 T2 上漏召的证据原句分桶；T1 8000 字漏掉的 primary 句分桶。
桶（按顺序判第一个命中的）：
  B1 切块边界：原句不落在任何单块内（跨块）；
  B2 同章邻块：所在块未入前 10，但前 10 有同章 ±2 块（局部上下文可救）；
  B3 名次近失：所在块名次 11–30；
  B4 同义改写/低词面：题面与所在块的非泛化二元组重合 ≤1；
  B5 深埋：其余（名次 >30，有一定词面）。
另记：实体别名（题面人名在块内未出现但块内有同章别称——人工标注不可得，用「题面二元组含人名、块内无」近似）、时间指代（块含时间词而题面无）。"""
import collections, json, re, sys
import zh_eval as Z
H = Z.H
TIME = re.compile(r"(那天|当时|后来|之前|此前|次日|翌日|第二天|多年|年前|年后|那年|当年|如今|此后|之后)")
GEN = set("什么 为什么 怎样 如何 哪些 哪个 是否 这个 那个 他们 她们 我们 一个 没有 不是 就是 自己 的是 了什 么？ 故事 情节 人物 作者".split())


def bg(s):
    s = H.norm(s); return {s[i:i + 2] for i in range(len(s) - 1)}


def main():
    d = Z.data(); R = Z.get("base0_L100"); ids = Z.SPLIT["dev"]
    ch = d["hc"]; cards = d["hcards"]; qtext = {q["qid"]: q["q"] for q in d["hq"]}
    rows = []; cnt = collections.Counter(); tot = 0
    for q in ids:
        c = cards[q]; rk = R["hmb"]["rank"][q]; top = rk[:10]
        nb = H.norm("\n".join(ch[i]["text"] for i in top))
        qb = bg(qtext[q]) - GEN
        for e in H.card_evidence(c):
            nq = H.norm(e["quote"])
            if not nq:
                continue
            tot += 1
            if nq in nb:
                continue
            home = [i for i, x in enumerate(ch) if nq in H.norm(x["text"])]
            if not home:
                b = "B1_切块边界"; r = None
            else:
                h = home[0]; r = rk.index(h) + 1 if h in rk else 999
                ov = len(qb & bg(ch[h]["text"]))
                if any(abs(t - h) <= 2 and ch[t]["cid"] == ch[h]["cid"] for t in top):
                    b = "B2_同章邻块"
                elif r <= 30:
                    b = "B3_名次近失"
                elif ov <= 1:
                    b = "B4_同义改写低词面"
                else:
                    b = "B5_深埋"
            tags = []
            if home and TIME.search(ch[home[0]]["text"]) and not TIME.search(qtext[q]):
                tags.append("时间指代")
            cnt[b] += 1
            rows.append({"qid": q, "bucket": b, "rank": r, "quote": e["quote"][:40], "tags": tags})
    # T1 8000
    t1 = collections.Counter(); t1n = 0
    tc = d["tc"]; tcards = {c["qid"]: c for c in d["tcards"]}
    for q in ids:
        c = tcards[q]; rk = R["hive"]["rank"][q]
        ctx = Z.HR.take(rk, tc, 8000)
        got = [i for i in sorted(set(rk)) if tc[i]["n"] in ctx.split("|")] if ctx else []
        gotset = set(Z.HR.take(rk, tc, 8000).split("|"))
        sel = [i for i in range(len(tc)) if tc[i]["n"] in gotset]
        for e in c.get("supporting_evidence") or []:
            if e.get("weight") != "primary":
                continue
            nq = Z.HR.norm(e["quote"]); t1n += 1
            if nq in ctx:
                continue
            home = [i for i, x in enumerate(tc) if nq in x["n"]]
            if not home:
                t1["B1_切块边界"] += 1; continue
            h = home[0]; r = rk.index(h) + 1 if h in rk else 999
            if any(abs(s - h) <= 2 and tc[s]["cid"] == tc[h]["cid"] for s in sel):
                t1["B2_同章邻块"] += 1
            elif r <= 80:
                t1["B3_名次近失(≤80)"] += 1
            elif len((bg(c["question"]) - GEN) & bg(tc[h]["text"])) <= 1:
                t1["B4_同义改写低词面"] += 1
            else:
                t1["B5_深埋"] += 1
    out = {"T2_dev_evidence_total": tot, "T2_missed": sum(cnt.values()), "T2_buckets": dict(cnt.most_common()),
           "T2_time_tag": sum("时间指代" in r["tags"] for r in rows),
           "T1_8000_dev_primary_total": t1n, "T1_missed": sum(t1.values()), "T1_buckets": dict(t1.most_common()), "rows": rows}
    Z.dump(Z.os.path.join(Z.RUNS, "err_dev.json"), out)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, ensure_ascii=False, indent=1))
    ranks = sorted(r["rank"] for r in rows if r["rank"] is not None)
    print("ranks", ranks)


if __name__ == "__main__":
    main()
