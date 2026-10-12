# -*- coding: utf-8 -*-
"""T2R2 新保留集构造（PREREG_ZH 修订 5；生成时不读任何臂的排序或读数）。
数据同 T2R：THUIR/T2Ranking（Apache-2.0）dev qrels，原始文件 /workspace/work/ls/_shared/t2ranking。
与 T2R（t2r/t2r.json，dev 140 + test 380 + 当时可选但丢弃的 11 题）去重：
  ①查询：src_qid 不在 T2R 可选集合 531 题内，且 norm(问句) 不与其中任何问句相同；
  ②段落：该题任何已标注段落的 pid 或 norm 文本都不出现在 T2R 任一库中（含 T2R 全部 26 库的全部段落）。
选题（放宽 T2R 的长度规则，其余同）：去掉 norm 长度不在 [20, 600] 的已标注段落（不写入库、不计分）后，
  证据 E = 相关度 2/3，2 ≤ |E| ≤ 5；误用 M = 相关度 1，|M| ≥ 1；且被去掉的段落中没有相关度 2/3 的（避免证据缺失）。
种子 20261014：按 sha1(seed:qid) 排序后贪心：依次取题，若与已取题共享任何段落（pid 或 norm 文本）则跳过（库间、轮间零共享）。
每 20 题一库（库 = 20 题已标注段落并集，同文去重，按 pid 升序写入）。
  前 10 库 → R1-dev（200 题）；其后 19 库 → R1-test（380）；再 19 库 → R2-test；再 19 库 → R3-test；
  R2/R3 各自的 dev 另取其后 10 库（R2-dev、R3-dev），每轮只读当轮 dev，test 每轮新 prereg 后各读一次。
  python t2r2_build.py   → t2r2/t2r2.json，并打印每份的 sha1（题号列表 + 库内容）"""
import collections, hashlib, json, os, re
SRC = "/workspace/work/ls/_shared/t2ranking"
HERE = os.path.dirname(os.path.abspath(__file__))
SEED, PER = 20261014, 20
PLAN = [("r1dev", 10), ("r1test", 19), ("r2test", 19), ("r3test", 19), ("r2dev", 10), ("r3dev", 10)]


def norm(s):
    return re.sub(r"[^\w]", "", str(s or ""), flags=re.UNICODE)


def main():
    lens = json.load(open(f"{SRC}/dev_lens.json"))
    Q = collections.defaultdict(dict)
    for i, l in enumerate(open(f"{SRC}/qrels.dev.tsv")):
        if i:
            a, _, p, r = l.split(); Q[a][p] = max(int(r), Q[a].get(p, 0))
    qtext = dict(l.rstrip("\n").split("\t", 1) for i, l in enumerate(open(f"{SRC}/queries.dev.tsv", encoding="utf-8")) if i)
    old = json.load(open(os.path.join(HERE, "t2r", "t2r.json"), encoding="utf-8"))

    def ok_old(q):  # T2R 当时的可选规则（531 题）
        d = Q[q]; E = [p for p, r in d.items() if r >= 2]; M = [p for p, r in d.items() if r == 1]
        return 2 <= len(E) <= 5 and len(M) >= 1 and all(20 <= lens.get(p, 0) <= 600 for p in d)
    old_q = {q for q in Q if ok_old(q)}
    assert len(old_q) == old["n_selectable"] == 531
    old_qn = {norm(qtext[q]) for q in old_q}
    old_pid = {p for q in old_q for p in Q[q]}
    old_txt = {norm(d["text"]) for s in old["stores"] for d in s["docs"]}

    text = {}
    for l in open(f"{SRC}/dev_passages_le600.jsonl", encoding="utf-8"):
        o = json.loads(l); text[o["pid"]] = o["text"]

    def kept(q):
        return {p: r for p, r in Q[q].items() if 20 <= lens.get(p, 0) <= 600 and p in text}

    def ok(q):
        if q in old_q or norm(qtext.get(q, "")) in old_qn or q not in qtext:
            return False
        d = kept(q)
        if any(r >= 2 for p, r in Q[q].items() if p not in d):
            return False
        E = [p for p, r in d.items() if r >= 2]; M = [p for p, r in d.items() if r == 1]
        if not (2 <= len(E) <= 5 and len(M) >= 1):
            return False
        return not any(p in old_pid or norm(text[p]) in old_txt for p in d)
    cand = sorted((q for q in Q if ok(q)), key=lambda q: hashlib.sha1(f"{SEED}:{q}".encode()).hexdigest())
    need = sum(n for _, n in PLAN) * PER
    used_p, used_t, used_qn, sel = set(), set(), set(), []
    for q in cand:
        d = kept(q); ts = {norm(text[p]) for p in d}
        if used_p & set(d) or used_t & ts or norm(qtext[q]) in used_qn:
            continue
        sel.append(q); used_p |= set(d); used_t |= ts; used_qn.add(norm(qtext[q]))
        if len(sel) == need:
            break
    assert len(sel) == need, (len(cand), len(sel))
    stores, cards, k = [], [], 0
    for part, n in PLAN:
        for _ in range(n):
            qs = sel[k * PER:(k + 1) * PER]
            pids = sorted({p for q in qs for p in kept(q)}, key=int)
            docs, canon, seen = [], {}, {}
            for p in pids:
                t = norm(text[p])
                if t in seen:
                    canon[p] = seen[t]; continue
                seen[t] = canon[p] = len(docs); docs.append({"pid": p, "text": text[p]})
            sid = f"u{k:02d}"
            stores.append({"sid": sid, "split": part, "docs": docs})
            for q in qs:
                lab = {}
                for p, r in kept(q).items():
                    lab[canon[p]] = max(r, lab.get(canon[p], -1))
                cards.append({"qid": f"u{q}", "src_qid": q, "question": qtext[q], "store": sid, "split": part,
                              "ev": sorted(i for i, r in lab.items() if r >= 2), "ev3": sorted(i for i, r in lab.items() if r == 3),
                              "mis": sorted(i for i, r in lab.items() if r == 1), "rel0": sorted(i for i, r in lab.items() if r == 0)})
            k += 1
    out = {"source": "THUIR/T2Ranking dev qrels (Apache-2.0)", "seed": SEED, "n_candidates": len(cand), "stores": stores, "cards": cards,
           "splits": {p: [c["qid"] for c in cards if c["split"] == p] for p, _ in PLAN}}
    os.makedirs(os.path.join(HERE, "t2r2"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "t2r2", "t2r2.json"), "w", encoding="utf-8"), ensure_ascii=False)
    # 去重核验
    allp = [d["pid"] for s in stores for d in s["docs"]]
    assert len(allp) == len(set(allp)) and not set(allp) & old_pid
    assert not {norm(d["text"]) for s in stores for d in s["docs"]} & old_txt
    assert not {c["src_qid"] for c in cards} & {c["src_qid"] for c in old["cards"]}
    import statistics as st
    print("candidates", len(cand), "selected", len(sel))
    for p, _ in PLAN:
        cs = [c for c in cards if c["split"] == p]; ss = [s for s in stores if s["split"] == p]
        h = hashlib.sha1(json.dumps([[c["qid"], c["question"], c["ev"], c["mis"]] for c in cs] + [s["docs"] for s in ss], ensure_ascii=False).encode()).hexdigest()
        L = [len(norm(d["text"])) for s in ss for d in s["docs"]]
        print(p, "q", len(cs), "stores", len(ss), "docs/store", round(st.mean(len(s["docs"]) for s in ss), 1), "len", round(st.mean(L)),
              "ev", round(st.mean(len(c["ev"]) for c in cs), 2), "ev3", round(st.mean(len(c["ev3"]) for c in cs), 2),
              "mis", round(st.mean(len(c["mis"]) for c in cs), 2), "sha1", h)


if __name__ == "__main__":
    main()
