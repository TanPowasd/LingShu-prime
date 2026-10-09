"""H-DUP M5 去重 + H1 前馈新奇门控：带标注的「应合并 / 不应合并」「新 / 旧」判别。

去重（add_perception 默认路径）：先写 M 条事实，再写探针；返回 id == 原节点 id 视为「合并」。
  应合并（同一命题的表面变体）：原样重复、首尾空白、全角数字、标点替换、去句号、远距离重复（写在最早 10% 的事实）。
  不应合并（命题已变）：否定、数值改动、换实体（一字之差）、换属性、值改一字。
  指标：合并判定的 precision / recall / F1，M ∈ {300, 3000}。
新奇门控（prefeed_input）：先写 K 条已知事实，再前馈探针；novel 字段为判定。
  不新：原样重复、表面变体；新：新实体事实、同实体属性新值（更正）、否定。指标：balanced accuracy，K ∈ {200, 2000}。
"""
import random
import time

from data import ATTRS, corpus, entities, value
from dims.metrics import prf

FW = str.maketrans("0123456789", "０１２３４５６７８９")


def _surface(rnd, f):
    t = rnd.randrange(5)
    s = f["text"]
    if t == 0:
        return "exact", s
    if t == 1:
        return "space", "  " + s + " \n"
    if t == 2:
        return "fullwidth", s.translate(FW)
    if t == 3:
        return "punct", s.replace("：", ":").replace("，", ",").replace("的", "的 ", 1)
    return "nostop", s.rstrip("。") + ("。" if not s.endswith("。") else "")


def _changed(rnd, f, ents):
    t = rnd.randrange(7)
    e, a, v = f["e"], f["a"], f["v"]
    if t == 5:
        return "negation2", rnd.choice([f"{e}的{a}并非{v}", f"{e}的{a}尚未确定是{v}", f"{e}没有{a}是{v}的记录"])
    if t == 6:
        return "decimal", f"{e}的{a}是{v[:-1]}.{v[-1]}"
    if t == 0:
        return "negation", f"{e}的{a}不是{v}"
    if t == 1:
        d = v[-1]
        return "number", f"{e}的{a}是{v[:-1]}{(int(d) + 1) % 10}"
    if t == 2:
        e2 = e[:-1] + ("强" if e[-1] != "强" else "军")
        return "entity", f"{e2}的{a}是{v}"
    if t == 3:
        a2 = rnd.choice([x for x in ATTRS if x != a])
        return "attr", f"{e}的{a2}是{v}"
    return "value", f"{e}的{a}是{'乙' if v[0] != '乙' else '丙'}{v[1:]}"


def _canon(f):
    return f"{f['e']}的{f['a']}是{f['v']}"


def dedup_eval(A, seed, M, nprobe=60):
    rnd = random.Random(seed * 31 + M)
    facts = [dict(f, text=_canon(f)) for f in corpus(seed + 100, M, upd_frac=0)]
    m = A.open(A.tmpdb(f"dup{M}"))
    ids = []
    t0 = time.perf_counter()
    for f in facts:
        ids.append(m.add(f["text"]))
    build = time.perf_counter() - t0
    n0 = m.count("knowledge")
    order = list(range(M))
    rnd.shuffle(order)
    pos_idx, neg_idx = order[:nprobe], order[nprobe:2 * nprobe]
    far = list(range(max(1, M // 10)))
    rnd.shuffle(far)
    tp = fp = fn = tn = 0
    kinds = {}
    ents = list({f["e"] for f in facts})
    for k, i in enumerate(pos_idx):
        if k % 4 == 3:          # 远距离重复：取最早 10% 的事实
            i = far[k % len(far)]
            kind, s = "far_" + _surface(rnd, facts[i])[0], _surface(rnd, facts[i])[1]
        else:
            kind, s = _surface(rnd, facts[i])
        try:
            got = m.add(s)
        except Exception:
            got = None
        hit = got == ids[i]
        kinds.setdefault(kind, [0, 0])
        kinds[kind][0] += int(hit)
        kinds[kind][1] += 1
        tp += hit
        fn += not hit
    for i in neg_idx:
        kind, s = _changed(rnd, facts[i], ents)
        try:
            got = m.add(s)
        except Exception:
            got = None
        merged = got == ids[i]
        kinds.setdefault(kind, [0, 0])
        kinds[kind][0] += int(not merged)
        kinds[kind][1] += 1
        fp += merged
        tn += not merged
    p, r, f1 = prf(tp, fp, fn)
    try:
        m.close()
    except Exception:
        pass
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, "n_before": n0,
            "by_kind_correct": {k: f"{a}/{b}" for k, (a, b) in sorted(kinds.items())},
            "build_s": round(build, 2), "add_ms": round(build / M * 1000, 3)}


def novelty_eval(A, seed, K, nprobe=40):
    rnd = random.Random(seed * 37 + K)
    allf = [dict(f, text=_canon(f)) for f in corpus(seed + 200, K + nprobe, upd_frac=0)]
    known, fresh = allf[:K], allf[K:]
    m = A.open(A.tmpdb(f"nov{K}"))
    for f in known:
        m.add(f["text"], skip_dedup=True)
    probes = []
    pick = rnd.sample(range(K), 4 * nprobe)
    for j in range(nprobe):
        probes.append(("known_exact", known[pick[j]]["text"], False))
        probes.append(("known_surface", _surface(rnd, known[pick[nprobe + j]])[1], False))
        probes.append(("new_entity", fresh[j]["text"], True))
        f = known[pick[2 * nprobe + j]]
        probes.append(("update", f"{f['e']}的{f['a']}是{value(rnd)}", True))
        f = known[pick[3 * nprobe + j]]
        probes.append(("negation", f"{f['e']}的{f['a']}不是{f['v']}", True))
    rnd.shuffle(probes)
    stat = {}
    tpos = tneg = cpos = cneg = 0
    for kind, s, label in probes:
        try:
            r = m.prefeed(s)
            pred = bool(r.get("novel"))
        except Exception:
            pred = not label   # 崩溃按判错计
        ok = pred == label
        stat.setdefault(kind, [0, 0])
        stat[kind][0] += int(ok)
        stat[kind][1] += 1
        if label:
            tpos += 1
            cpos += ok
        else:
            tneg += 1
            cneg += ok
    bacc = 0.5 * (cpos / tpos + cneg / tneg)
    try:
        m.close()
    except Exception:
        pass
    return {"balanced_acc": round(bacc, 4), "tpr": round(cpos / tpos, 4), "tnr": round(cneg / tneg, 4),
            "by_kind_correct": {k: f"{a}/{b}" for k, (a, b) in sorted(stat.items())}}


def run(A, seed, dedup_sizes=(300, 3000), novelty_sizes=(200, 2000)):
    out = {"dedup": {}, "novelty": {}}
    for M in dedup_sizes:
        out["dedup"][str(M)] = dedup_eval(A, seed, M)
    for K in novelty_sizes:
        out["novelty"][str(K)] = novelty_eval(A, seed, K)
    return out
