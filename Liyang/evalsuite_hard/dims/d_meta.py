"""H-MET 变形 / 差分测试：同一语义的多种输入应得相同结果。

1. 查询表面变体（首尾空白、全角问号/数字、句末标点、实体与属性间插空格）→ 与原查询 top-1 相同、top-5 集合 Jaccard。
2. 内容全角/半角等价（NFKC）：全角写入、半角查询 → 原节点在前 3。
3. 写入顺序置换：同一语料两种顺序建库 → 唯一相关事实的名次一致（都在 top-1 或名次相同）。
4. 去重顺序对称：先写 A 再写 B 是否合并 == 先写 B 再写 A 是否合并。
5. 因果：同一张图按两种边插入顺序构建 → reason_causal(s,t) 的路径集合相同。
分数 = 各子项一致率的平均。
"""
import random
import unicodedata

from data import corpus, queries

FWD = str.maketrans("0123456789?", "０１２３４５６７８９？")


def _variants(q):
    return {"ws": f"  {q}  ", "fwq": q.translate(FWD) + "？", "stop": q + "。", "inner_space": q.replace("的", " 的 ", 1)}


def _top(m, q, k=5):
    try:
        return [n["id"] for n, _ in m.recall(q, limit=k)]
    except Exception:
        return None


def run(A, seed, n=1000, nq=80):
    rnd = random.Random(seed * 17 + 3)
    facts = corpus(seed + 300, n, upd_frac=0)
    out = {}
    # 1 + 3
    m1 = A.open(A.tmpdb("met1"))
    ids1 = [m1.add(f["text"], skip_dedup=True) for f in facts]
    order = list(range(n))
    rnd.shuffle(order)
    m2 = A.open(A.tmpdb("met2"))
    ids2 = [None] * n
    for i in order:
        ids2[i] = m2.add(facts[i]["text"], skip_dedup=True)
    qs = [(q, rel) for t, q, rel in queries(seed + 300, facts, nq * 2) if t in ("ea", "rev")][:nq]
    agree1, jac, agree3 = [], [], []
    for q, rel in qs:
        base = _top(m1, q)
        for v in _variants(q).values():
            got = _top(m1, v)
            if base is None or got is None:
                agree1.append(0); jac.append(0.0)
                continue
            agree1.append(int(bool(base) and bool(got) and base[0] == got[0]))
            a, b = set(base), set(got)
            jac.append(len(a & b) / len(a | b) if a | b else 1.0)
        d = next(iter(rel))
        r1 = _top(m1, q, 10)
        r2 = _top(m2, q, 10)
        if r1 is None or r2 is None:
            agree3.append(0)
            continue
        k1 = r1.index(ids1[d]) if ids1[d] in r1 else -1
        k2 = r2.index(ids2[d]) if ids2[d] in r2 else -1
        agree3.append(int(k1 == k2 and k1 != -1))
    out["query_variant_top1"] = round(sum(agree1) / len(agree1), 4)
    out["query_variant_top5_jaccard"] = round(sum(jac) / len(jac), 4)
    out["insert_order_rank_equal"] = round(sum(agree3) / len(agree3), 4)
    # 2 NFKC
    mk = A.open(A.tmpdb("nfkc"))
    hits = 0
    for i in range(40):
        half = f"设备ABC{i:03d}的型号是X{i * 37}"
        full = unicodedata.normalize("NFKC", half)
        full = "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in half)
        nid = mk.add(full, skip_dedup=True)
        for j in range(5):
            mk.add(f"干扰设备{i}-{j}的型号是Y{j}", skip_dedup=True)
        top = _top(mk, f"设备ABC{i:03d}的型号", 3) or []
        hits += nid in top
    out["nfkc_fullwidth_query_halfwidth"] = round(hits / 40, 4)
    # 4 去重顺序对称
    sym = 0
    pairs = []
    for i in range(30):
        f = facts[i]
        a = f"{f['e']}的{f['a']}是{f['v']}"
        b = [f"  {a}。", a.replace("是", "为"), f"{f['e']}的{f['a']}不是{f['v']}"][i % 3]
        pairs.append((a, b))
    for a, b in pairs:
        r = []
        for x, y in ((a, b), (b, a)):
            mm = A.open()
            i1 = mm.add(x)
            i2 = mm.add(y)
            r.append(i1 == i2)
        sym += r[0] == r[1]
    out["dedup_order_symmetric"] = round(sym / len(pairs), 4)
    # 5 因果插入顺序
    agree5 = []
    for g in range(6):
        gr = random.Random(seed * 1000 + g)
        nn = 25
        edges = set()
        while len(edges) < 45:
            a, b = sorted(gr.sample(range(nn), 2))
            edges.add((a, b))
        edges = sorted(edges)
        res = []
        for perm in (edges, list(reversed(edges))):
            mm = A.open()
            ids = [mm.add(f"因果节点{g}-{i}", skip_dedup=True) for i in range(nn)]
            for a, b in perm:
                mm.add_edge(ids[a], ids[b], "causal", 0.6)
            inv = {v: k for k, v in enumerate(ids)}
            try:
                chains = mm.reason(ids[0], ids[nn - 1], max_depth=8)
                res.append(sorted(tuple(inv.get(getattr(e, "source_id", None), -1) for e in c) for c in chains))
            except Exception:
                res.append(None)
        agree5.append(int(res[0] is not None and res[0] == res[1]))
    out["causal_insert_order_equal"] = round(sum(agree5) / len(agree5), 4)
    keys = [k for k in out]
    out["score_inputs"] = keys
    return out
