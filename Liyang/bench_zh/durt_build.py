# -*- coding: utf-8 -*-
"""DuRT 新中文检索判定集构造（PREREG_ZH 修订 8；生成时不读任何臂的排序或读数）。
源：C-MTEB/DuRetrieval（HF @a1a333e，corpus 100001 段 / queries 2000）+ C-MTEB/DuRetrieval-qrels（@497b7bd，dev 9839 条，二值）。
原始数据：百度 DuReader-retrieval（Qiu et al. 2022, EMNLP，Apache-2.0）；原文不入库，只在 /workspace/work/ls/_shared/data/duret。
规则（缩到 2 核可跑的规模）：
  ①段落 norm 长度 ∈ [20, 600] 才可入库；查询的任何正例超出该范围 → 弃题（避免证据缺失）；1 ≤ |E| ≤ 6。
  ②种子 20261012，按 sha1(seed:qid) 排序后贪心取题；与已取题共享任何正例（pid 或 norm 文本）或 norm 问句重复 → 跳过。
  ③每 20 题一库：库 = 20 题正例并集 + 词面池化干扰（每题取 TF-IDF 字二元组余弦前 8 名非正例；池化器独立实现，
    不是任何一臂的打分函数）+ 均匀随机干扰补到 260 段。干扰段不得是任何已取题的正例或与其 norm 文本相同；库间零共享段落。
    库内按 pid 升序写入（写入序与相关性无关）。
  ④切分：前 10 库 dev（200 题）→ 其后 19 库 hold（380，冻结后只读一次）→ 其余库 hold2 / hold3（各 19 库，后续轮次各自登记后才可读）。
  DuRetrieval 标注为二值且不完全（未标注≠不相关）：误用 n/a；rel0 字段记「池化干扰段」（未经人工判定，只作噪声监视）。
  python durt_build.py   → durt/durt.json，并打印每份 sha1"""
import hashlib, json, math, os, random, re, collections
import numpy as np
from scipy import sparse
# 修订 9：DB_SET=covr → CovidRetrieval（同一规则①–③，只改切分比例与题号前缀）
DB_SET = os.environ.get("DB_SET", "durt")
SRC = {"durt": "/workspace/work/ls/_shared/data/duret", "covr": "/workspace/work/ls/_shared/data/covr"}[DB_SET]
HERE = os.path.dirname(os.path.abspath(__file__))
SEED, PER, STORE_N, POOL_K = 20261012, 20, 260, 8
PLAN = [("dev", 10), ("hold", 19), ("hold2", 19), ("hold3", 19)] if DB_SET == "durt" else [("dev", 4), ("hold", 999)]
QP = "d" if DB_SET == "durt" else "c"


def norm(s):
    return re.sub(r"[^\w]", "", str(s or ""), flags=re.UNICODE)


def grams(s):
    n = norm(s).lower()
    return [n[i:i + 2] for i in range(len(n) - 1)] or [n]


def sha(obj):
    return hashlib.sha1(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main():
    C = {x["id"]: x["text"] for x in json.load(open(f"{SRC}/corpus.json", encoding="utf-8"))}
    QT = {x["id"]: x["text"] for x in json.load(open(f"{SRC}/queries.json", encoding="utf-8"))}
    QR = collections.defaultdict(set)
    for r in json.load(open(f"{SRC}/qrels.json", encoding="utf-8")):
        if r["score"] > 0:
            QR[r["qid"]].add(r["pid"])
    ok_len = {p for p, t in C.items() if 20 <= len(norm(t)) <= 600}

    def ok(q):
        E = QR[q]
        return q in QT and 1 <= len(E) <= 6 and all(p in C and p in ok_len for p in E)
    cand = sorted((q for q in QR if ok(q)), key=lambda q: hashlib.sha1(f"{SEED}:{q}".encode()).hexdigest())
    taken, used_p, used_t, used_qn = [], set(), set(), set()
    for q in cand:
        E = QR[q]; qn = norm(QT[q])
        if qn in used_qn or any(p in used_p or norm(C[p]) in used_t for p in E):
            continue
        taken.append(q); used_qn.add(qn); used_p |= E; used_t |= {norm(C[p]) for p in E}
    need = min(sum(n for _, n in PLAN) * PER, len(taken))
    nst = min(len(taken), need) // PER
    taken = taken[:nst * PER]
    print("candidates", len(cand), "greedy", len(taken), "stores", nst)
    # 池化器：字二元组 TF-IDF 余弦（独立实现）。干扰候选 = 长度合规、非任何已取题正例、norm 文本不同于任何正例
    allpos_p = set().union(*(QR[q] for q in taken)); allpos_t = {norm(C[p]) for p in allpos_p}
    D = sorted(p for p in ok_len if p not in allpos_p and norm(C[p]) not in allpos_t)
    vocab, rows, cols, vals = {}, [], [], []
    for i, p in enumerate(D):
        cnt = collections.Counter(grams(C[p]))
        for g, v in cnt.items():
            j = vocab.setdefault(g, len(vocab)); rows.append(i); cols.append(j); vals.append(1 + math.log(v))
    X = sparse.csr_matrix((vals, (rows, cols)), shape=(len(D), len(vocab)), dtype=np.float32)
    df = np.bincount(X.indices, minlength=len(vocab)); idf = np.log((1 + len(D)) / (1 + df)).astype(np.float32) + 1
    X = X.multiply(idf).tocsr(); nr = np.sqrt(X.multiply(X).sum(1)).A1 + 1e-9; X = sparse.diags(1 / nr) @ X; XT = X.T.tocsr()
    rng = random.Random(SEED); used_d = set(); stores, cards = [], []
    splits = {}; k = 0
    for name, n in PLAN:
        for _ in range(n):
            if k >= nst:
                break
            qs = taken[k * PER:(k + 1) * PER]; sid = f"{QP}{k:02d}"; k += 1
            docs = set().union(*(QR[q] for q in qs)); pooled = set()
            for q in qs:
                g = collections.Counter(grams(QT[q])); idx = [vocab[x] for x in g if x in vocab]
                if not idx:
                    continue
                w = np.array([(1 + math.log(g[x])) for x in g if x in vocab], dtype=np.float32) * idf[idx]
                s = (XT[idx].T @ w)
                c = 0
                for i in np.argsort(-s):
                    p = D[i]
                    if p in used_d or p in docs:
                        continue
                    pooled.add(p); docs.add(p); used_d.add(p); c += 1
                    if c >= POOL_K:
                        break
            while len(docs) < STORE_N:
                p = D[rng.randrange(len(D))]
                if p not in used_d and p not in docs:
                    docs.add(p); used_d.add(p)
            # 同文去重（库内）
            seen, order = set(), []
            for p in sorted(docs):
                t = norm(C[p])
                if t not in seen:
                    seen.add(t); order.append(p)
            tix = {norm(C[p]): i for i, p in enumerate(order)}
            pos = {p: tix[norm(C[p])] for p in docs}  # 同文正例映射到保留的那一段
            stores.append({"sid": sid, "split": name, "docs": [{"pid": p, "text": C[p]} for p in order]})
            for q in qs:
                cards.append({"qid": QP + q[:10], "src_qid": q, "question": QT[q], "store": sid, "split": name,
                              "ev": sorted({pos[p] for p in QR[q]}), "ev3": [], "mis": [],
                              "rel0": sorted({pos[p] for p in pooled} - {pos[p] for p in QR[q]})})
                splits.setdefault(name, []).append(QP + q[:10])
    assert len({c["qid"] for c in cards}) == len(cards)
    out = {"source": "C-MTEB/DuRetrieval@a1a333e + DuRetrieval-qrels@497b7bd (DuReader-retrieval, Apache-2.0)" if DB_SET == "durt" else "C-MTEB/CovidRetrieval@1271c78 + CovidRetrieval-qrels@a9f41b7", "seed": SEED,
           "n_candidates": len(cand), "stores": stores, "cards": cards, "splits": splits}
    os.makedirs(os.path.join(HERE, DB_SET), exist_ok=True)
    s = json.dumps(out, ensure_ascii=False)
    open(os.path.join(HERE, DB_SET, f"{DB_SET}.json"), "w", encoding="utf-8").write(s)
    print("durt.json sha1", hashlib.sha1(s.encode()).hexdigest())
    for name in splits:
        st = [x for x in stores if x["split"] == name]; cs = [c for c in cards if c["split"] == name]
        print(name, len(st), "x", PER, "=", len(cs), sha({"cards": cs, "stores": st}),
              "docs/库 %.1f" % (sum(len(x["docs"]) for x in st) / len(st)), "|E| %.2f" % (sum(len(c["ev"]) for c in cs) / len(cs)))


if __name__ == "__main__":
    main()
