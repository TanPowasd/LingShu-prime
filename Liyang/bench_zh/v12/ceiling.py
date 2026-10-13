# 标注噪声下的 AUC 天花板（粗估）：真值完美可分的打分，在独立翻转率 e 的 1/2-3 标注下题内 E-M AUC 的期望
# e 由近重复段落一致率 a 反推：2e(1-e) = 1-a（修订 7a：a = .784；κ CI 下/上界对应 a ≈ .70 / .85 作敏感性）
import json, os, numpy as np
D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs", "t2r2", "v12"); P = json.load(open(os.path.join(D, "pairs.json")))
sz = [(sum(x["lab"] == "E" for x in v["items"]), sum(x["lab"] == "M" for x in v["items"])) for v in P.values()]
rng = np.random.RandomState(0); r = {}
for a in (.70, .784, .85):
    e = (1 - np.sqrt(1 - 2 * (1 - a))) / 2; aucs = []
    for _ in range(20):
        for nE, nM in sz:
            if not nE or not nM: continue
            # 观测 E 中真为 E 的以 1-e 概率；真 E 打分 1+u，真 M 打分 u
            tE = rng.rand(nE) > e; tM = rng.rand(nM) < e
            sE = tE + rng.rand(nE) * .5; sM = tM + rng.rand(nM) * .5
            aucs.append(np.mean([(x > y) + .5 * (x == y) for x in sE for y in sM]))
    r[str(a)] = {"e": round(float(e), 3), "ceiling_auc": round(float(np.mean(aucs)), 3)}
print(r); json.dump(r, open(os.path.join(D, "ceiling.json"), "w"))
