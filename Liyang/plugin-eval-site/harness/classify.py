"""四结论分类器：✅真有用 / ❌帮倒忙 / 😐看不出差别 / 🚧没法测。

输入：底子臂与插件臂的逐题逐种子加权分（同卷、同种子集合）。
统计：
- 每题先在种子上取均值 → 配对差 d_c = plug_c − base_c；
- 净提升 D = mean(d_c)，折算成「多对几道题」= D × 题数（只报整数）；
- 配对 bootstrap（按题重抽，B=10000，固定 rng 种子 7）得 95% 区间；
- 符号检验（d_c≠0 的题，双侧精确二项）作并列证据；
- 逐种子净提升 D_s，看方向是否一致。
阈值（写进 SPEC §6）：见 THRESH。

题目非独立（UPSTREAM U3：89 卡中 11 组共用同一答案键）：
- `answer_key_clusters(cards)` 按 (file, answer.human.line) 给每卡一个簇号；
- `cluster_bootstrap_ci` 按簇整组重抽（B=10000，rng 种子 7），统计量仍为"所抽卡的配对差均值"；
- `effective_n` 给出簇稳健方差下的设计效应 deff 与有效样本量 n_eff = n / deff（解析式，确定性）；
- `classify(..., clusters=..., ci_method="cluster")` 用簇区间判结论；缺省 ci_method="item"＝旧方法（SPEC v0.1 原口径），
  传了 clusters 时两种区间都写进输出以作对照。
"""
from __future__ import annotations
import math, random

THRESH = {
    "min_seeds": 3,
    "min_coverage": 0.90,       # 有效作答（非系统故障）题占比
    "min_effect_items": 3.0,    # |净提升| 至少折合 3 道题（89 卡≈0.034/题；> 判官一档跳动 0.0056×数条）
    "alpha": 0.05,
    "bootstrap_B": 10000,
}


def sign_test_p(pos: int, neg: int) -> float:
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def bootstrap_ci(diffs: list[float], B: int, seed: int = 7) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(diffs)
    ms = []
    for _ in range(B):
        ms.append(sum(diffs[rng.randrange(n)] for _ in range(n)) / n)
    ms.sort()
    return ms[int(0.025 * B)], ms[int(0.975 * B) - 1]


def answer_key_clusters(cards: list[dict]) -> dict:
    """cards: 上游题卡列表 → {qid: 簇号字符串 "<file>#L<answer.human.line>"}。不改题，只分组。"""
    return {c["id"]: f"{c['file']}#L{c['answer']['human']['line']}" for c in cards}


def _groups(qids: list, clusters: dict) -> list[list[int]]:
    """按簇把题下标分组；没有簇号的题自成一簇。组顺序按首次出现，确定性。"""
    order, g = [], {}
    for i, q in enumerate(qids):
        key = clusters.get(q, ("__solo__", q)) if clusters else ("__solo__", q)
        if key not in g:
            g[key] = []; order.append(key)
        g[key].append(i)
    return [g[k] for k in order]


def cluster_bootstrap_ci(diffs: list[float], groups: list[list[int]], B: int, seed: int = 7) -> tuple[float, float]:
    """按簇整组重抽：每次抽 G 个簇（有放回），统计量＝所抽全部卡的配对差均值（卡加权）。"""
    rng = random.Random(seed)
    G = len(groups)
    sums = [sum(diffs[i] for i in grp) for grp in groups]
    sizes = [len(grp) for grp in groups]
    ms = []
    for _ in range(B):
        S = N = 0.0
        for _ in range(G):
            k = rng.randrange(G)
            S += sums[k]; N += sizes[k]
        ms.append(S / N)
    ms.sort()
    return ms[int(0.025 * B)], ms[int(0.975 * B) - 1]


def effective_n(diffs: list[float], groups: list[list[int]]) -> dict:
    """簇稳健（CR1）方差 vs 独立方差 → 设计效应 deff 与有效样本量 n_eff=n/deff。
    V_iid = s²/n；V_cl = G/(G−1) · Σ_g (S_g − m_g·D)² / n²。deff<1 时如实报告（组内负相关），n_eff 不截断。"""
    n = len(diffs); G = len(groups)
    if n < 2 or G < 2:
        return {"n": n, "n_clusters": G, "deff": float("nan"), "n_eff": float("nan")}
    D = sum(diffs) / n
    s2 = sum((d - D) ** 2 for d in diffs) / (n - 1)
    v_iid = s2 / n
    v_cl = G / (G - 1) * sum((sum(diffs[i] for i in g) - len(g) * D) ** 2 for g in groups) / n ** 2
    deff = v_cl / v_iid if v_iid > 0 else float("nan")
    # 组内相关（单因素 ANOVA 估计，簇大小不等时用 m0）
    m0 = (n - sum(len(g) ** 2 for g in groups) / n) / (G - 1)
    msb = sum(len(g) * (sum(diffs[i] for i in g) / len(g) - D) ** 2 for g in groups) / (G - 1)
    ssw = sum((diffs[i] - sum(diffs[j] for j in g) / len(g)) ** 2 for g in groups for i in g)
    msw = ssw / (n - G) if n > G else 0.0
    icc = (msb - msw) / (msb + (m0 - 1) * msw) if (msb + (m0 - 1) * msw) > 0 else float("nan")
    return {"n": n, "n_clusters": G, "se_iid": v_iid ** 0.5, "se_cluster": v_cl ** 0.5,
            "deff": deff, "n_eff": n / deff if deff and deff == deff and deff > 0 else float("nan"), "icc": icc}


def classify(base: dict, plug: dict, *, install_ok: bool = True, coverage: float = 1.0,
             judge_valid: bool = True, clusters: dict | None = None, ci_method: str = "item") -> dict:
    """clusters: {qid: 簇号}（见 answer_key_clusters）；ci_method: "item"（旧，SPEC v0.1）| "cluster"（按答案键整簇重抽）。"""
    """base/plug: {qid: {seed: score}}。返回结论与证据（不含小数点百分比的展示字段另行生成）。"""
    seeds = sorted(set.intersection(*[set(v) for v in list(base.values()) + list(plug.values())])) if base and plug else []
    qids = sorted(set(base) & set(plug))
    out = {"n_items": len(qids), "seeds": seeds, "thresholds": THRESH}
    reasons = []
    if not install_ok:
        reasons.append("安装失败")
    if not judge_valid:
        reasons.append("判官批次作废未恢复")
    if coverage < THRESH["min_coverage"]:
        reasons.append(f"有效作答覆盖不足（{round(coverage*100)}% < {round(THRESH['min_coverage']*100)}%）")
    if len(seeds) < THRESH["min_seeds"]:
        reasons.append(f"种子数 {len(seeds)} < {THRESH['min_seeds']}")
    if reasons or not qids:
        out.update(verdict="🚧", label="没法测", reasons=reasons or ["无可比题"])
        return out
    bm = {q: sum(base[q][s] for s in seeds) / len(seeds) for q in qids}
    pm = {q: sum(plug[q][s] for s in seeds) / len(seeds) for q in qids}
    diffs = [pm[q] - bm[q] for q in qids]
    n = len(qids)
    D = sum(diffs) / n
    lo_i, hi_i = bootstrap_ci(diffs, THRESH["bootstrap_B"])
    if ci_method not in ("item", "cluster"):
        raise ValueError(f"ci_method={ci_method!r}")
    if ci_method == "cluster" and not clusters:
        raise ValueError("ci_method='cluster' 需要 clusters")
    if clusters:
        grp = _groups(qids, clusters)
        lo_c, hi_c = cluster_bootstrap_ci(diffs, grp, THRESH["bootstrap_B"])
        out.update(ci_item=(lo_i, hi_i), ci_cluster=(lo_c, hi_c), ci_items_item=(lo_i * n, hi_i * n),
                   ci_items_cluster=(lo_c * n, hi_c * n), eff_n=effective_n(diffs, grp))
    lo, hi = (lo_c, hi_c) if ci_method == "cluster" else (lo_i, hi_i)
    out["ci_method"] = ci_method
    pos = sum(d > 1e-9 for d in diffs); neg = sum(d < -1e-9 for d in diffs)
    p_sign = sign_test_p(pos, neg)
    per_seed = {s: sum(plug[q][s] - base[q][s] for q in qids) / n for s in seeds}
    base_seed = {s: sum(base[q][s] for q in qids) / n for s in seeds}
    plug_seed = {s: sum(plug[q][s] for q in qids) / n for s in seeds}
    eff_items = D * n
    out.update(D=D, ci=(lo, hi), items_gain=eff_items, ci_items=(lo * n, hi * n), sign=(pos, neg, p_sign),
               per_seed_D=per_seed, base_per_seed=base_seed, plug_per_seed=plug_seed,
               base_mean=sum(bm.values()) / n, plug_mean=sum(pm.values()) / n)
    all_pos = all(v > 0 for v in per_seed.values())
    all_neg = all(v < 0 for v in per_seed.values())
    big = abs(eff_items) >= THRESH["min_effect_items"]
    if lo > 0 and all_pos and big:
        out.update(verdict="✅", label="真有用")
    elif hi < 0 and all_neg and big:
        out.update(verdict="❌", label="帮倒忙")
    else:
        why = []
        if not (lo > 0 or hi < 0):
            why.append("95% 区间跨 0")
        if not (all_pos or all_neg):
            why.append("各种子方向不一致")
        if not big:
            why.append(f"效应不足 {THRESH['min_effect_items']:g} 道题")
        out.update(verdict="😐", label="看不出差别", reasons=why)
    return out


def fmt_items(x: float) -> str:
    r = int(round(x))
    return f"+{r}" if r > 0 else str(r)
