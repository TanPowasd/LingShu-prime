# -*- coding: utf-8 -*-
"""因果图性质测试 / 激活引擎 / 后台调度 / 结构重要性"""
import itertools
import random
import sys
import threading
import time

import pytest

from lingshu_ng import causal
from lingshu_ng.activation import ActivationEngine
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.graphquery import recalc_structural_importance, spatiotemporal
from lingshu_ng.scheduler import AutoDecay
from lingshu_ng.types import EdgeType


# ---------------------------------------------------------------- 因果：与暴力枚举一致（性质测试）
def _brute_cycles(arcs, nodes, max_len=None):
    """暴力：枚举所有节点排列，验证闭合简单环；返回边集合的集合。"""
    by_pair = {}
    for eid, s, t in arcs:
        by_pair.setdefault((s, t), []).append(eid)
    found = set()
    for k in range(1, len(nodes) + 1):
        if max_len is not None and k > max_len:
            break
        for perm in itertools.permutations(nodes, k):
            if perm[0] != min(perm):
                continue
            pairs = list(zip(perm, perm[1:] + perm[:1]))
            if all(p in by_pair for p in pairs):
                for combo in itertools.product(*[by_pair[p] for p in pairs]):
                    found.add(frozenset(combo))
    return found


@pytest.mark.parametrize("seed", range(40))
def test_cycle_enumeration_matches_bruteforce(seed):
    rng = random.Random(seed)
    nodes = [f"v{i}" for i in range(rng.randint(1, 6))]
    arcs = [(f"e{j}", rng.choice(nodes), rng.choice(nodes)) for j in range(rng.randint(0, 9))]
    adj, order = causal.build_adjacency(arcs)
    used = sorted({a[1] for a in arcs} | {a[2] for a in arcs})
    want = _brute_cycles(arcs, used)
    got = causal.enumerate_cycles(adj, order, None, None)
    assert {frozenset(c) for c in got.cycles} == want
    assert len(got.cycles) == len(want)                       # 每环恰一次
    assert causal.has_cycle(adj, order) == bool(want)          # 判环与枚举同一结论（#215）
    for L in (1, 2, 3):
        lim = causal.enumerate_cycles(adj, order, L, None)
        assert {frozenset(c) for c in lim.cycles} == {c for c in want if len(c) <= L}


def test_dense_cycles_are_budgeted_not_exploding():
    nodes = [f"n{i}" for i in range(11)]
    arcs = [(f"{a}>{b}", a, b) for a in nodes for b in nodes if a != b]
    adj, order = causal.build_adjacency(arcs)
    t0 = time.time()
    scan = causal.enumerate_cycles(adj, order, None, 256)
    assert scan.truncated and len(scan.cycles) == 256 and time.time() - t0 < 1.0     # #252
    assert causal.has_cycle(adj, order)


def test_long_cycle_detected_regardless_of_depth():
    e = MemoryEngine()
    ids = [e.perceive(f"环上节点{i}号独立内容{i * 13}", skip_dedup=True).node_id for i in range(12)]
    for a, b in zip(ids, ids[1:] + ids[:1]):
        e.link(a, b, EdgeType.CAUSAL)
    r = e.self_check()
    assert r["has_cycle"] and r["cycles_found"] == 1 and r["cyclic_components"] == 1   # 环长 12 > 8


def test_chain_flags():
    arcs = [("a", "A", "B"), ("b", "B", "C"), ("c", "C", "B"), ("d", "C", "D"), ("e", "D", "E")]
    adj, _ = causal.build_adjacency(arcs)
    ch = causal.chains(adj, "A", 3)
    kinds = sorted(k for _, k in ch)
    assert kinds == ["cyclic", "truncated"]
    assert causal.chains(adj, "E", 3) == []


# ---------------------------------------------------------------- 激活
def _graph():
    e = MemoryEngine()
    a = e.perceive("灵枢认知图上下文").node_id
    b = e.perceive("完全无关的天气记录").node_id
    c = e.perceive("另一条毫不相干的流水账").node_id
    e.link(a, b, EdgeType.CAUSAL)
    e.link(b, c, EdgeType.CAUSAL)
    return e, a, b, c


def test_activation_empty_query_and_empty_graph(tmp_path):
    e, *_ = _graph()
    act = ActivationEngine(audit_path=str(tmp_path / "a.jsonl"), store=e.store)
    for q in ("", "   ", "\n"):
        r = act.activate(q, workset="w")
        assert r["status"] == "ok" and r["size"] == 0 and r["seeds"] == 0          # #199/#161
    empty = ActivationEngine(audit_path=str(tmp_path / "b.jsonl"), store=MemoryEngine().store)
    assert empty.activate("任何查询")["size"] == 0                                # #95


def test_activation_sources_hops_and_fresh_graph(tmp_path):
    e, a, b, c = _graph()
    act = ActivationEngine(audit_path=str(tmp_path / "a.jsonl"), store=e.store)
    act.activate("认知图", workset="w", hops=2)
    snap = {m["node_id"]: m for m in act.export_workset("w")["members"]}
    assert (snap[a]["source"], snap[a]["hop"]) == ("seed", 0)
    assert (snap[c]["source"], snap[c]["hop"]) == ("propagate", 2)
    d = e.perceive("认知图的新增节点").node_id                                     # #126：新节点立刻可见
    assert d in [m[0] for m in act.activate("认知图", workset="w2")["top"]]


def test_opposite_edges_inhibit(tmp_path):
    e = MemoryEngine()
    claim = e.perceive("旧结论：方案甲最优").node_id
    for i in range(3):
        ev = e.perceive(f"证据{i}：方案甲在场景{i}失败").node_id
        e.link(ev, claim, EdgeType.OPPOSITE)
    act = ActivationEngine(audit_path=str(tmp_path / "a.jsonl"), store=e.store)
    r = act.activate("方案甲失败的证据", workset="w", hops=1)
    assert claim not in [m[0] for m in r["top"]]                                    # #229
    assert claim in [m[0] for m in r["suppressed"]]
    pol = {m["node_id"]: m["polarity"] for m in act.export_workset("w")["members"]}
    assert pol[claim] == -1
    assert claim not in act.carry_vector("w")


def test_activation_is_stdlib_only():
    import ast
    import lingshu_ng.activation as m
    tree = ast.parse(open(m.__file__, encoding="utf-8").read())
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and not n.level}
    assert not mods & {"numpy", "scipy"}                                           # #7


# ---------------------------------------------------------------- 调度
def test_autodecay_restart_no_stacking_and_survives_errors():
    calls, boom = [], {"n": 0}

    def tick(el):
        calls.append(el)
        if boom["n"] < 2:
            boom["n"] += 1
            raise RuntimeError("transient")
    ad = AutoDecay(tick)
    before = set(threading.enumerate())
    for _ in range(4):
        ad.start(0.05)
        ad.stop()
    ad.start(0.05)
    time.sleep(0.6)
    alive = [t for t in threading.enumerate() if t not in before and t.is_alive()]
    ad.stop()
    assert len(alive) == 1 and len(ad.errors) == 2 and len(calls) > 2              # #184/core-py-06
    assert all(not t.is_alive() for t in alive)                                    # stop 已 join（#37）


def test_elapsed_factor_independent_of_call_rate():
    from lingshu_ng.decay import elapsed_factor
    one = 1 - elapsed_factor(0.02, 60.0)
    many = (1 - elapsed_factor(0.02, 1.0)) ** 60
    assert abs(one - many) < 1e-12                                                 # #176


# ---------------------------------------------------------------- 图查询
def test_structural_importance_is_idempotent():
    e = MemoryEngine()
    hub = e.perceive("中心", importance=0.3).node_id
    for i in range(6):
        o = e.perceive(f"外围{i}号节点内容{i}", importance=0.1, skip_dedup=True).node_id
        e.link(hub, o, EdgeType.SIMILAR)
    vals = []
    for _ in range(4):
        recalc_structural_importance(e.store, dry_run=False)
        vals.append(round(e.store.nodes.get(hub).importance, 4))
    assert vals == [0.45] * 4


def test_spatiotemporal_zero_radius():
    e = MemoryEngine()
    a = e.perceive("同刻甲").node_id
    assert spatiotemporal(e.store, a, time_radius=0) == [] or True                 # 不抛 ZeroDivisionError（#89）


def test_scan_arcs_equals_full_enumeration_and_scc():
    """整数化判环 + 只在 SCC 导出子图上枚举 ≡ 全图邻接表上的枚举与 SCC 判定（随机图）。"""
    import random
    for seed in range(60):
        rng = random.Random(seed)
        n = rng.randint(1, 9)
        arcs = [(f"e{k}", f"v{rng.randrange(n)}", f"v{rng.randrange(n)}") for k in range(rng.randint(0, 18))]
        adj, order = causal.build_adjacency(arcs)
        assert causal.cyclic_from_arcs(arcs) == causal.cyclic_nodes(adj, order)[0]
        for ml, mc in ((None, None), (3, None), (None, 5)):
            a = causal.scan_arcs(arcs, ml, mc)
            b = causal.enumerate_cycles(adj, order, ml, mc)
            assert (a.cycles, a.truncated, a.components) == (b.cycles, b.truncated, b.components)
