"""H-CAU2（hard-rules-v2 新增子项，v1 的 d_causal.py 不动）：

  johnson  3000 点规模的 find_cycles 完整枚举，对 Johnson（1975）基本环算法预言机：
           3000 点局部 DAG（每点 3 条前向边，跨度 ≤ 6）+ 60 个 50 点窗口各 2 条回边（跨度 12–18），约 2 万个基本环，
           环集合按边集合（有向边 (src,dst) 的 frozenset）比较 → P/R/F1；另记 find_cycles 耗时与判环正确性。
           max_depth 传 3000（旧声明「完整枚举（不设预算）」core.py:1141-1145；环长上限=max_depth+1 条边），
           预言机给出的最长环远小于此，故比较的是完整环集。
  chains   reason_causal(start) 不给 end 的链枚举及 truncated / cyclic 标记，对按旧声明语义写的预言机
           （integrated core.py:323-341 CausalChain、core.py:2977-3018）：无出边 → 普通链；深度预算用尽仍有出边 → truncated；
           出边指向路径内已访问节点 → 该边收尾的 cyclic 链。比较 (节点序列, truncated, cyclic) 多重集 → F1。
  huge     20 万条因果边判环耗时：5 万点、20 万条前向边（DAG），has_causal_cycle 应为 False；
           再加一条从 BFS 可达的远端节点指回起点的回边，应为 True。两次各取 3 次中位数；正确性不过 → 耗时项记 0。
"""
import json
import os
import random
import statistics
import time
from collections import Counter, defaultdict

from dims.metrics import prf

RAW = False


# ---------------- Johnson 基本环（1975）——带阻塞表的经典算法（迭代实现） ----------------
def _sccs(nodes, adj):
    idx, low, on, st, res, cnt = {}, {}, set(), [], [], [0]
    for root in nodes:
        if root in idx:
            continue
        work = [(root, iter(adj.get(root, ())))]
        idx[root] = low[root] = cnt[0]; cnt[0] += 1; st.append(root); on.add(root)
        while work:
            v, it = work[-1]
            adv = False
            for w in it:
                if w not in idx:
                    idx[w] = low[w] = cnt[0]; cnt[0] += 1; st.append(w); on.add(w)
                    work.append((w, iter(adj.get(w, ()))))
                    adv = True
                    break
                elif w in on:
                    low[v] = min(low[v], idx[w])
            if adv:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == idx[v]:
                comp = []
                while True:
                    w = st.pop(); on.discard(w); comp.append(w)
                    if w == v:
                        break
                res.append(comp)
    return res


def johnson_cycles(n, edges):
    """返回全部基本环（节点序列列表）。节点 0..n-1；edges 为 (a,b) 集合（无重边）。"""
    adj = defaultdict(list)
    for a, b in sorted(edges):
        adj[a].append(b)
    out = []
    for a, b in edges:
        if a == b:
            out.append([a])
    s = 0
    while s < n:
        sub = {v: [w for w in adj[v] if w >= s and w != v] for v in range(s, n)}
        comps = [c for c in _sccs(range(s, n), sub) if len(c) > 1]
        if not comps:
            break
        least = min(min(c) for c in comps)
        comp = set(next(c for c in comps if least in c))
        s = least
        cadj = {v: [w for w in sub[v] if w in comp] for v in comp}
        blocked, B, stack = set(), defaultdict(set), [s]

        def unblock(u):
            todo = [u]
            while todo:
                x = todo.pop()
                if x in blocked:
                    blocked.discard(x)
                    todo.extend(B[x])
                    B[x].clear()

        blocked.add(s)
        work = [(s, iter(cadj[s]), [False])]
        while work:
            v, it, found = work[-1]
            adv = False
            for w in it:
                if w == s:
                    out.append(list(stack))
                    found[0] = True
                elif w not in blocked:
                    blocked.add(w); stack.append(w)
                    work.append((w, iter(cadj[w]), [False]))
                    adv = True
                    break
            if adv:
                continue
            work.pop()
            if found[0]:
                unblock(v)
            else:
                for w in cadj[v]:
                    B[w].add(v)
            stack.pop()
            if work:
                work[-1][2][0] = work[-1][2][0] or found[0]
        s += 1
    return out


def _cyc_key(seq):
    return frozenset((seq[i], seq[(i + 1) % len(seq)]) for i in range(len(seq)))


def _johnson_part(A, rnd):
    n = 3000
    edges = set()
    for a in range(n):
        for _ in range(3):
            b = a + rnd.randint(1, 6)
            if b < n:
                edges.add((a, b))
    for w in range(60):                      # 60 个 50 点窗口，每窗 2 条跨度 12–18 的回边（窗内环互锁、窗间独立）
        base = w * 50
        for _ in range(2):
            a = base + rnd.randrange(0, 25)
            edges.add((a + rnd.randint(12, 18), a))
    t0 = time.perf_counter()
    truth = {_cyc_key(c) for c in johnson_cycles(n, edges)}
    oracle_ms = (time.perf_counter() - t0) * 1000
    m = A.open(A.tmpdb("cau2_j"))
    ids = [m.add(f"约翰逊{i}", skip_dedup=True) for i in range(n)]
    inv = {v: k for k, v in enumerate(ids)}
    for a, b in sorted(edges):
        m.add_edge(ids[a], ids[b], "causal", 0.6)
    out = {"n_truth": len(truth), "max_len": max((len(k) for k in truth), default=0), "oracle_ms": round(oracle_ms, 1)}
    t0 = time.perf_counter()
    try:
        got = {frozenset((inv.get(a), inv.get(b)) for a, b in c) for c in m.cycles(max_depth=n)}
        out["find_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    except Exception as ex:
        got = set()
        out["error"] = f"{type(ex).__name__}:{str(ex)[:100]}"
    tp, fp, fn = len(truth & got), len(got - truth), len(truth - got)
    p, r, f = prf(tp, fp, fn)
    out.update({"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp, "fp": fp, "fn": fn,
                "n_got": len(got)})
    try:
        out["has_cycle_ok"] = m.has_cycle() is True
    except Exception:
        out["has_cycle_ok"] = False
    return out


# ---------------- 链枚举预言机（旧声明语义） ----------------
def oracle_chains(adj, s, D):
    res = []

    def go(u, path, on, depth):
        kept = adj.get(u, [])
        if not kept:
            if path:
                res.append((tuple(path), False, False))
            return
        if depth >= D:
            if path:
                res.append((tuple(path), True, False))
            return
        for v in kept:
            if v in on:
                res.append((tuple(path + [v]), False, True))
                continue
            on.add(v)
            go(v, path + [v], on, depth + 1)
            on.discard(v)
    go(s, [s], {s}, 0)
    # 路径以节点序列表示（含起点）；空路径（起点无出边）不产生链
    return Counter((p if len(p) > 1 else p, t, c) for p, t, c in res if len(p) > 1)


def _chain_seq(chain, inv):
    seq = []
    for e in chain:
        a, b = inv.get(getattr(e, "source_id", None)), inv.get(getattr(e, "target_id", None))
        if not seq:
            seq.append(a)
        seq.append(b)
    return tuple(seq)


def _chains_part(A, rnd, graphs=30):
    tp = fp = fn = 0
    exact = 0
    errs = 0
    flags = Counter()
    for g in range(graphs):
        n = rnd.randint(12, 24)
        edges = set()
        while len(edges) < int(n * 1.6):
            a, b = rnd.sample(range(n), 2)
            if a < b or rnd.random() < 0.18:          # 以前向为主，约 18% 回边（制造 cyclic 链）
                edges.add((a, b))
        if rnd.random() < 0.3:                        # 自环（旧声明「回边/自环 ⇒ cyclic」core.py:329,3016）
            v = rnd.randrange(n)
            edges.add((v, v))
        adj = defaultdict(list)
        for a, b in sorted(edges):
            adj[a].append(b)
        D = rnd.randint(2, 6)
        truth = oracle_chains(adj, 0, D)
        for (p, t, c), k in truth.items():
            flags["truncated" if t else "cyclic" if c else "end"] += k
        m = A.open()
        ids = [m.add(f"链{g}-{i}", skip_dedup=True) for i in range(n)]
        inv = {v: k for k, v in enumerate(ids)}
        for a, b in sorted(edges):
            m.add_edge(ids[a], ids[b], "causal", 0.6)
        try:
            got = Counter((_chain_seq(ch, inv), bool(getattr(ch, "truncated", False)), bool(getattr(ch, "cyclic", False)))
                          for ch in m.reason(ids[0], None, max_depth=D))
        except Exception:
            got, errs = Counter(), errs + 1
        tp += sum((truth & got).values()); fp += sum((got - truth).values()); fn += sum((truth - got).values())
        exact += int(truth == got)
    p, r, f = prf(tp, fp, fn)
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp, "fp": fp, "fn": fn,
            "graph_exact": round(exact / graphs, 4), "errors": errs, "truth_flags": dict(flags)}


# ---------------- 20 万边判环 ----------------
def _huge_part(A, rnd, n=50000, e=200000):
    part = os.environ.get("HARD_PARTIAL")
    out = {"n": n, "e": e}

    def save():
        if part:
            json.dump(out, open(part, "w"))
    m = A.open(A.tmpdb("cau2_huge"))
    t0 = time.perf_counter()
    ids = [m.add(f"巨图{i}", skip_dedup=True) for i in range(n)]
    edges = set()
    while len(edges) < e:
        a = rnd.randrange(n - 1)
        b = min(n - 1, a + rnd.randint(1, 200))
        edges.add((a, b))
    adj = defaultdict(list)
    for a, b in sorted(edges):
        m.add_edge(ids[a], ids[b], "causal", 0.6)
        adj[a].append(b)
    out["build_s"] = round(time.perf_counter() - t0, 1)
    save()

    def timed():
        ts, ans = [], None
        for _ in range(3):
            t1 = time.perf_counter()
            ans = m.has_cycle()
            ts.append((time.perf_counter() - t1) * 1000)
        return ans, round(statistics.median(ts), 2)
    try:
        ans, ms = timed()
        out["acyclic_ok"], out["acyclic_ms"] = ans is False, ms
    except Exception as ex:
        out["acyclic_ok"], out["acyclic_ms"] = False, None
        out["error"] = f"{type(ex).__name__}:{str(ex)[:100]}"
    save()
    # 回边：从 0 出发 BFS 取最远可达点 far，加 far→0
    seen, frontier = {0}, [0]
    while frontier:
        nxt = []
        for u in frontier:
            for v in adj.get(u, ()):
                if v not in seen:
                    seen.add(v); nxt.append(v)
        frontier = nxt
    far = max(seen)
    out["back_edge_span"] = far
    m.add_edge(ids[far], ids[0], "causal", 0.6)
    try:
        ans, ms = timed()
        out["cyclic_ok"], out["cyclic_ms"] = ans is True, ms
    except Exception as ex:
        out["cyclic_ok"], out["cyclic_ms"] = False, None
        out["error2"] = f"{type(ex).__name__}:{str(ex)[:100]}"
    return out


def run(A, seed, part="johnson"):
    rnd = random.Random(seed * 211 + {"johnson": 1, "chains": 2, "huge": 3}[part])
    if part == "johnson":
        return _johnson_part(A, rnd)
    if part == "chains":
        return _chains_part(A, rnd)
    return _huge_part(A, rnd)
