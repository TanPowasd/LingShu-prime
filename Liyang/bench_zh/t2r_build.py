# -*- coding: utf-8 -*-
"""T2R 判定保留集构造（PREREG_ZH 修订 4；生成时不读任何臂的排序或读数）。
数据：THUIR/T2Ranking（Apache-2.0，SIGIR'23）dev qrels（= 论文 test 侧：每对 ≥3 名专职标注员 4 级相关度、多数票；该侧对所有切分段落全量标注以减假负例）。
  原始文件：/workspace/work/ls/_shared/t2ranking/{qrels.dev.tsv, queries.dev.tsv, dev_passages_le600.jsonl, dev_lens.json}
  （dev_passages 由 filt.py 从 collection.tsv 流式过滤得到：<br>→换行、去 HTML 标签、合并空行，只保留 norm 长度 ≤600 的段落）
选题（与任何臂无关）：证据 E = 相关度 2/3 的段落，2 ≤ |E| ≤ 5；误用 M = 相关度 1 的段落（人工判「与题相关但不满足信息需求」），|M| ≥ 1；
  该题全部已标注段落 norm 长度 ∈ [20, 600]。种子 20261013：按 sha1(seed:qid) 排序，每 20 题一库（库 = 这 20 题全部已标注段落的并集，
  同文去重，库内按 pid 升序写入 = 采集顺序，同一网页切出的相邻段落 pid 相邻），前 7 库 → dev（140 题），其后 19 库 → test（380 题），余数丢弃。
  python t2r_build.py"""
import collections, hashlib, json, os, re
SRC = "/workspace/work/ls/_shared/t2ranking"
HERE = os.path.dirname(os.path.abspath(__file__))
SEED, PER, NDEV, NTEST = 20261013, 20, 7, 19


def norm(s):
    return re.sub(r"[^\w]", "", str(s or ""), flags=re.UNICODE)


def main():
    lens = json.load(open(f"{SRC}/dev_lens.json"))
    Q = collections.defaultdict(dict)
    for i, l in enumerate(open(f"{SRC}/qrels.dev.tsv")):
        if i:
            a, _, p, r = l.split(); Q[a][p] = max(int(r), Q[a].get(p, 0))
    qtext = dict(l.rstrip("\n").split("\t", 1) for i, l in enumerate(open(f"{SRC}/queries.dev.tsv", encoding="utf-8")) if i)

    def ok(q):
        d = Q[q]; E = [p for p, r in d.items() if r >= 2]; M = [p for p, r in d.items() if r == 1]
        return 2 <= len(E) <= 5 and len(M) >= 1 and all(20 <= lens.get(p, 0) <= 600 for p in d)
    sel = sorted((q for q in Q if ok(q)), key=lambda q: hashlib.sha1(f"{SEED}:{q}".encode()).hexdigest())
    need = {p for q in sel for p in Q[q]}
    text = {}
    for l in open(f"{SRC}/dev_passages_le600.jsonl", encoding="utf-8"):
        o = json.loads(l)
        if o["pid"] in need:
            text[o["pid"]] = o["text"]
    stores, cards = [], []
    for s in range(NDEV + NTEST):
        qs = sel[s * PER:(s + 1) * PER]
        pids = sorted({p for q in qs for p in Q[q]}, key=int)
        docs, canon, seen = [], {}, {}
        for p in pids:
            k = norm(text[p])
            if k in seen:
                canon[p] = seen[k]; continue
            seen[k] = canon[p] = len(docs); docs.append({"pid": p, "text": text[p]})
        split = "dev" if s < NDEV else "test"
        stores.append({"sid": f"s{s:02d}", "split": split, "docs": docs})
        for q in qs:
            lab = {}
            for p, r in Q[q].items():
                lab[canon[p]] = max(r, lab.get(canon[p], -1))
            cards.append({"qid": f"t{q}", "src_qid": q, "question": qtext[q], "store": f"s{s:02d}", "split": split,
                          "ev": sorted(i for i, r in lab.items() if r >= 2), "ev3": sorted(i for i, r in lab.items() if r == 3),
                          "mis": sorted(i for i, r in lab.items() if r == 1), "rel0": sorted(i for i, r in lab.items() if r == 0)})
    out = {"source": "THUIR/T2Ranking dev qrels (Apache-2.0)", "seed": SEED, "n_selectable": len(sel), "stores": stores, "cards": cards,
           "dev": [c["qid"] for c in cards if c["split"] == "dev"], "test": [c["qid"] for c in cards if c["split"] == "test"]}
    json.dump(out, open(os.path.join(HERE, "t2r", "t2r.json"), "w", encoding="utf-8"), ensure_ascii=False)
    import statistics as st
    L = [len(norm(d["text"])) for s in stores for d in s["docs"]]
    print("selectable", len(sel), "dev", len(out["dev"]), "test", len(out["test"]), "store docs", [len(s["docs"]) for s in stores],
          "doc len mean/median", round(st.mean(L)), st.median(L), "ev mean", round(st.mean(len(c["ev"]) for c in cards), 2),
          "ev3 mean", round(st.mean(len(c["ev3"]) for c in cards), 2), "mis mean", round(st.mean(len(c["mis"]) for c in cards), 2),
          "ev chars mean", round(st.mean(sum(L2 for L2 in [len(norm(stores[int(c['store'][1:])]['docs'][i]['text'])) for i in c['ev']]) for c in cards)))


if __name__ == "__main__":
    main()
