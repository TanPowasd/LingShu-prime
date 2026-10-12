# v6 dev 分析：在每题已标注段落内，哪些特征能区分证据（2/3）与误用（1）——逐题内 AUC 平均（只读 T2R dev）
import collections, math, re, statistics as st
import t2r_eval as E, t2r_proto as P
HR = E.HR
def feats(c, i, I, rk):
    t = E.T()["S"][c["store"]]["docs"][i]["text"]; n = HR.norm(t)
    qb = set(P.bg(c["question"])); tot = sum(I.idf.get(b, 0) for b in qb) or 1
    cov = sum(I.idf.get(b, 0) for b in qb if b in I.tf[i]) / tot
    return {"cov": cov, "rank": -rk.get(i, 999), "len": len(n), "digits": len(re.findall(r"\d", t)) / max(1, len(n)),
            "steps": len(re.findall(r"(?:^|\n)\s*(?:\d+[、.．]|第[一二三四五六七八九十]步|首先|然后|其次|最后)", t)),
            "qmark": t.count("?") + t.count("？")}
def auc(pos, neg):
    if not pos or not neg: return None
    s = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg); return s / (len(pos) * len(neg))
# 第二轮特征：最长公共子串、题面三元组覆盖、按问句类型的答案线索
def lcs(a, b):
    best = 0; prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b):
            if x == y: cur[j + 1] = prev[j] + 1; best = max(best, cur[j + 1])
        prev = cur
    return best
QT = [(r"怎么|如何|怎样|方法|步骤", r"(?:^|\n)\s*(?:\d+[、.．]|第[一二三四五六七八九十]步)|首先|点击|然后|打开"),
      (r"多少|几|多大|多长|多久|多高|价格|钱", r"\d"), (r"为什么|为何|原因", r"因为|原因|由于|所以|导致"),
      (r"是什么|什么是|什么意思|指什么", r"是指|指的是|是一种|意思是|即"), (r"哪|什么时候|何时", r"\d|在")]
def atype(q, t):
    s = 0
    for qp, ap in QT:
        if re.search(qp, q): s += len(re.findall(ap, t)) > 0
    return s


if __name__ == "__main__":
    base = E.get("v4", "dev"); A = collections.defaultdict(list)
    for c in E.cards("dev"):
        I = P.idx(c["store"]); rk = {d: r for r, d in enumerate(base[c["qid"]])}
        F = {i: feats(c, i, I, rk) for i in c["ev"] + c["mis"]}
        for k in F[c["ev"][0]]:
            a = auc([F[i][k] for i in c["ev"]], [F[i][k] for i in c["mis"]])
            if a is not None: A[k].append(a)
    for k, v in A.items(): print(k, round(st.mean(v), 3), len(v))
    B = collections.defaultdict(list)
    for c in E.cards("dev"):
        I = P.idx(c["store"]); D = E.T()["S"][c["store"]]["docs"]; qn = HR.norm(c["question"])
        tri = {qn[i:i+3] for i in range(len(qn) - 2)}
        F = {}
        for i in c["ev"] + c["mis"]:
            n = HR.norm(D[i]["text"])
            F[i] = {"lcs": lcs(qn, n[:400]), "tri": sum(t in n for t in tri) / max(1, len(tri)), "atype": atype(c["question"], D[i]["text"])}
        for k in F[c["ev"][0]]:
            a = auc([F[i][k] for i in c["ev"]], [F[i][k] for i in c["mis"]])
            if a is not None: B[k].append(a)
    for k, v in B.items(): print(k, round(st.mean(v), 3), len(v))
