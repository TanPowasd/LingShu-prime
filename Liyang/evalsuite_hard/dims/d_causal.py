"""H-CAU 因果图：路径枚举对暴力预言机的精确率/召回、判环与环节点集合对 Tarjan 预言机、规模耗时。"""
import random
import sys
import time

from dims.metrics import logscore, mean, prf


def _paths(adj, s, t, D):
    out, stack = [], [(s, [s])]
    while stack:
        u, p = stack.pop()
        if len(p) - 1 >= D:
            continue
        for v in adj.get(u, ()):
            if v in p:
                continue
            if v == t:
                out.append(tuple(p + [v]))
            else:
                stack.append((v, p + [v]))
    return set(out)


def _scc_nodes(n, edges):
    sys.setrecursionlimit(100000)
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
    idx, low, on, st, cnt, res = {}, {}, set(), [], [0], set()

    def dfs(v):
        idx[v] = low[v] = cnt[0]; cnt[0] += 1; st.append(v); on.add(v)
        for w in adj.get(v, ()):
            if w not in idx:
                dfs(w); low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = st.pop(); on.discard(w); comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or (v in adj and v in adj[v]):
                res.update(comp)
    for v in range(n):
        if v not in idx:
            dfs(v)
    return res


def _chain_nodes(chain, inv):
    seq = []
    for e in chain:
        a, b = inv.get(getattr(e, "source_id", None)), inv.get(getattr(e, "target_id", None))
        if not seq:
            seq.append(a)
        seq.append(b)
    return tuple(seq)


def run(A, seed, n_pairs=25, part="small"):
    rnd = random.Random(seed * 101 + 7)
    out = {}
    if part == "big":
        return _big(A, rnd)
    # 1 路径枚举
    tp = fp = fn = 0
    errs = 0
    for g in range(n_pairs):
        n = rnd.randint(20, 40)
        edges = set()
        while len(edges) < n * 3:
            a, b = sorted(rnd.sample(range(n), 2))
            edges.add((a, b))
        adj = {}
        for a, b in edges:
            adj.setdefault(a, []).append(b)
        D = rnd.randint(3, 6)
        s = 0
        reach = [t for t in range(1, n) if _paths(adj, s, t, D)]
        if not reach:
            continue
        t = rnd.choice(reach)
        truth = _paths(adj, s, t, D)
        m = A.open()
        ids = [m.add(f"因果{g}-{i}", skip_dedup=True) for i in range(n)]
        inv = {v: k for k, v in enumerate(ids)}
        for a, b in sorted(edges):
            m.add_edge(ids[a], ids[b], "causal", 0.6)
        try:
            got = {_chain_nodes(c, inv) for c in m.reason(ids[s], ids[t], max_depth=D)}
        except Exception:
            got, errs = set(), errs + 1
        tp += len(truth & got); fp += len(got - truth); fn += len(truth - got)
    p, r, f = prf(tp, fp, fn)
    out["paths"] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp, "fp": fp, "fn": fn, "errors": errs}
    # 2 判环与环节点集合
    cyc_ok, jac = [], []
    for g in range(12):
        n = 150
        edges = set()
        while len(edges) < 300:
            a, b = sorted(rnd.sample(range(n), 2))
            edges.add((a, b))
        planted = g % 3 != 0
        if planted:
            for _ in range(rnd.randint(1, 3)):
                L = rnd.randint(2, 14)
                cyc = rnd.sample(range(n), L)
                for i in range(L):
                    edges.add((cyc[i], cyc[(i + 1) % L]))
        truth = _scc_nodes(n, edges)
        m = A.open()
        ids = [m.add(f"环{g}-{i}", skip_dedup=True) for i in range(n)]
        inv = {v: k for k, v in enumerate(ids)}
        for a, b in sorted(edges):
            m.add_edge(ids[a], ids[b], "causal", 0.6)
        try:
            hc = m.has_cycle()
            cyc_ok.append(int(hc == bool(truth)))
        except Exception:
            cyc_ok.append(0)
        try:
            got = set()
            for c in m.cycles(max_depth=20):
                for a, b in c:
                    got.add(inv.get(a)); got.add(inv.get(b))
            jac.append(len(got & truth) / len(got | truth) if (got | truth) else 1.0)
        except Exception:
            jac.append(0.0)
    out["has_cycle_acc"] = round(mean(cyc_ok), 4)
    out["cycle_nodes_jaccard"] = round(mean(jac), 4)
    return out


def _big(A, rnd):
    out = {}
    # 3 规模：3000 节点 / 9000 边 DAG，从源出发链枚举与判环耗时
    m = A.open(A.tmpdb("causal_big"))
    n = 3000
    ids = [m.add(f"大图{i}", skip_dedup=True) for i in range(n)]
    edges = set()
    while len(edges) < 3 * n:
        a, b = sorted(rnd.sample(range(n), 2))
        if b - a < 30:
            edges.add((a, b))
    for a, b in sorted(edges):
        m.add_edge(ids[a], ids[b], "causal", 0.6)
    import json, os
    part = os.environ.get("HARD_PARTIAL")
    t0 = time.perf_counter()
    try:
        m.has_cycle()
        out["big_has_cycle_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    except Exception:
        out["big_has_cycle_ms"] = None
    if part:
        json.dump(out, open(part, "w"))
    t0 = time.perf_counter()
    try:
        m.reason(ids[0], ids[200], max_depth=12)
        out["big_reason_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    except Exception:
        out["big_reason_ms"] = None
    return out
