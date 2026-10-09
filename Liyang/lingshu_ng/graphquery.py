# -*- coding: utf-8 -*-
"""graphquery · 有界遍历 / 子图 / 时空邻域 / 时间线 / 结构重要性重算

不变量：
  P1 遍历是迭代 BFS，``max_depth`` 与 ``max_nodes`` 双上限，结果确定（同 importance 按深度再按 id）。
  P2 时空邻域：``time_radius=0`` 只取同刻节点且不做除零(#89)；候选为全量时间窗查询，
     不预截 importance 前 200 条。
  P3 结构重要性是**重算**：以「当前值 − 上次记录的结构提升」为地板，重复调用不叠加，
     单节点结构提升 ≤ boost_cap（core-py-11）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .store import Store
from .types import EdgeType, MemoryLayer, Node, _json_field

__all__ = ["traverse", "subgraph", "spatiotemporal", "timeline", "recalc_structural_importance"]


def traverse(store: Store, start_id: str, relation_types: Optional[Sequence[str]] = None,
             direction: str = "out", max_depth: int = 5, min_importance: float = 0.0,
             max_nodes: int = 500) -> List[Dict]:
    """P1：返回 [{node_id, depth, edge_id, direction, importance}]。"""
    types = [EdgeType.coerce(t).value for t in relation_types] if relation_types else None
    topo = store.edges.topology(types)
    out_adj: Dict[str, List[Tuple[str, str]]] = {}
    in_adj: Dict[str, List[Tuple[str, str]]] = {}
    for eid, s, t, _, _ in topo:
        out_adj.setdefault(s, []).append((t, eid))
        in_adj.setdefault(t, []).append((s, eid))
    frontier, visited, res = [start_id], {start_id}, []
    for depth in range(1, max_depth + 1):
        if not frontier or len(visited) > max_nodes:
            break
        nxt = []
        for nid in frontier:
            for d, adj in (("out", out_adj), ("in", in_adj)):
                if direction not in (d, "both"):
                    continue
                for other, eid in adj.get(nid, ()):
                    if other not in visited:
                        visited.add(other)
                        nxt.append(other)
                        res.append({"node_id": other, "depth": depth, "edge_id": eid, "direction": d})
        frontier = nxt
    nodes = store.nodes.get_many([r["node_id"] for r in res])
    keep = []
    for r in res:
        imp = (nodes[r["node_id"]].importance or 0.0) if r["node_id"] in nodes else 0.0
        if imp >= min_importance:
            r["importance"] = imp
            keep.append(r)
    keep.sort(key=lambda x: (-x["importance"], x["depth"], x["node_id"]))
    return keep[:max_nodes]


def subgraph(store: Store, root_id: str, max_depth: int = 3,
             relation_types: Optional[Sequence[str]] = None, direction: str = "out") -> Dict:
    """根 + 遍历到的节点 + 两端都在子图内的边。"""
    found = traverse(store, root_id, relation_types or ["hierarchical", "causal", "similar"],
                     direction=direction, max_depth=max_depth)
    ids = [root_id] + [r["node_id"] for r in found]
    edges = [{"source": a, "target": b, "relation_type": r} for a, b, r in store.edges.between(ids)]
    names = {}
    for nid, n in store.nodes.get_many(ids).items():
        nm = (n.state_attributes or {}).get("name") if isinstance(n.state_attributes, dict) else None
        names[nid] = {"name": nm or nid[:24], "importance": n.importance}
    return {"root": root_id, "node_count": len(ids), "edge_count": len(edges), "nodes": names,
            "edges": edges}


def spatiotemporal(store: Store, center_id: str, time_radius: float = 300.0,
                   space_metric: Optional[str] = None, space_radius: float = 0.5,
                   max_results: int = 20) -> List[Tuple[Node, float]]:
    """P2：时间邻近 + （可选）空间轴邻近，按综合距离升序。"""
    c = store.nodes.get(center_id)
    if c is None:
        return []
    def when(n: Node) -> float:
        """时间坐标；仅 NULL 回落 created_at（显式 0.0 保留，上游 PR #91）。"""
        return n.temporal_coordinate if n.temporal_coordinate is not None else (n.created_at or 0.0)

    tc = when(c)
    r = max(0.0, float(time_radius))
    out = []
    cands = store.nodes.in_range(tc - r, tc + r, limit=None) + store.nodes.undated_in_range(tc - r, tc + r)
    for n in cands:
        if n.id == center_id:
            continue
        td = abs(when(n) - tc)
        sd = 0.0
        if space_metric and space_metric in c.spatial_coordinates:
            if space_metric not in n.spatial_coordinates:
                continue
            sd = abs(c.spatial_coordinates[space_metric] - n.spatial_coordinates[space_metric])
            if sd > space_radius:
                continue
        tn = td / r if r > 0 else 0.0
        out.append((n, 0.5 * tn + 0.5 * (sd / max(space_radius, 0.01))))
    out.sort(key=lambda x: (x[1], x[0].id))
    return out[:max_results]


def timeline(store: Store, node_id: str, direction: str = "forward", max_depth: int = 20) -> List[Node]:
    """沿 SEQUENTIAL/CAUSAL 边按置信度最高者展开时间线（遇环即停）。"""
    chain, cur, seen = [], node_id, set()
    kinds = ["sequential", "causal"]
    for _ in range(max_depth):
        if cur is None or cur in seen:
            break
        seen.add(cur)
        n = store.nodes.get(cur)
        if n is None:
            break
        chain.append(n)
        edges = store.edges.outgoing(cur, kinds) if direction == "forward" else store.edges.incoming(cur, kinds)
        edges.sort(key=lambda e: (-e.confidence, e.id))
        cur = (edges[0].target_id if direction == "forward" else edges[0].source_id) if edges else None
    return chain


def _influence(adj: Dict[str, List[Tuple[str, float]]], imp: Dict[str, float], max_depth: int) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for src in adj:
        total, seen, frontier = 0.0, {src}, [(src, 1.0, 0)]
        while frontier:
            node, pc, d = frontier.pop(0)
            for t, cf in adj.get(node, ()):
                if t in seen or d + 1 > max_depth:
                    continue
                seen.add(t)
                nc = pc * cf
                total += nc * imp.get(t, 0.5) / (d + 1)
                frontier.append((t, nc, d + 1))
        if total > 0:
            out[src] = round(total, 4)
    return out


_NO_PROTECT_TAGS = frozenset({"archived", "refuted", "deprecated"})
_STRUCT_REASON = "结构保护:"


def _struct_graph(store: Store):
    """P4（上游 #269/#274）：只计两端节点都在库的边（悬空边不计分）；度数/因果出度用全部这类边（有上限的扇出
    提升），因果上游度传播（会导致永久保护）只走 verified=1 的因果边。"""
    rows = store.db.all("SELECT e.source_id, e.target_id, e.relation_type, e.confidence, e.verified FROM edges e "
                        "JOIN nodes ns ON ns.id = e.source_id JOIN nodes nt ON nt.id = e.target_id")
    deg: Dict[str, int] = {}
    cout: Dict[str, int] = {}
    adj: Dict[str, List[Tuple[str, float]]] = {}
    for s, t, rel, cf, ver in rows:
        deg[s], deg[t] = deg.get(s, 0) + 1, deg.get(t, 0) + 1
        if rel == "causal":
            cout[s] = cout.get(s, 0) + 1
            if ver:
                adj.setdefault(s, []).append((t, cf if cf is not None else 0.5))
    return len(rows), deg, cout, adj


def _protect_upstream(store: Store, nid: str, infl: float, cur: float, floor: float) -> None:
    """结构保护 + importance 保底；把本机制施加的部分记进 state_attributes.structural_protect 以便精确撤销。"""
    rec = store.nodes.state_attr(nid, "structural_protect")
    if not isinstance(rec, dict):
        n = store.nodes.get(nid)
        if n is None:
            return
        had = store.db.scalar("SELECT 1 FROM protections WHERE node_id=?", (nid,)) is not None
        rec = {"added_protection": not had, "added_no_forget": "no_forget" not in n.tags, "lift": 0.0}
        if had:                                       # 已有（他处授予的）保护：不覆盖其登记理由
            store.nodes.set_state_attr(nid, "structural_protect", rec)
        else:
            store.registry.protect(nid, f"{_STRUCT_REASON}概念影响度 {infl}")
    if cur < floor:
        store.nodes.update(nid, importance=floor)
        rec = dict(rec, lift=round(float(rec.get("lift", 0.0)) + floor - cur, 4))
    store.nodes.set_state_attr(nid, "structural_protect", rec)


def _unprotect_upstream(store: Store, nid: str) -> None:
    """不再达标：只撤本机制授予的保护登记 / no_forget / importance 抬升（上游 #269）。"""
    rec = store.nodes.state_attr(nid, "structural_protect")
    if not isinstance(rec, dict):
        return
    reason = store.db.scalar("SELECT reason FROM protections WHERE node_id=?", (nid,))
    with store.db.tx():
        n = store.nodes.get(nid)
        if n is None:
            return
        fields: Dict = {}
        if rec.get("added_protection") and str(reason or "").startswith(_STRUCT_REASON):
            store.db.run("DELETE FROM protections WHERE node_id=?", (nid,))
            if rec.get("added_no_forget"):
                fields["tags"] = [t for t in n.tags if t != "no_forget"]
        lift = float(rec.get("lift") or 0.0)
        if lift:
            fields["importance"] = max(0.0, (n.importance or 0.0) - lift)
        sa = dict(n.state_attributes or {})
        sa.pop("structural_protect", None)
        fields["state_attributes"] = sa
        store.nodes.update(nid, **fields)


def recalc_structural_importance(store: Store, dry_run: bool = True, boost_cap: float = 0.15,
                                 beta: float = 0.30, gamma: float = 0.40, c: float = 6.0,
                                 min_degree: int = 5, min_causal: int = 3, min_delta: float = 0.02,
                                 max_depth: int = 5, protect_threshold: float = 1.0,
                                 floor_importance: float = 0.9) -> Dict:
    """P3：度数/因果出度驱动的结构提升（重算语义）+ 因果上游影响度保护（P4：只走已验证因果边；
    归档/驳回/废弃与情境层节点不保护；不再达标即撤销本机制授予的保护）。"""
    n_edges, deg, cout, adj = _struct_graph(store)
    max_deg = max(deg.values()) if deg else 1
    rows = store.db.all("SELECT id, importance, layer, tags FROM nodes ORDER BY id")
    imp = {r[0]: (r[1] if r[1] is not None else 0.5) for r in rows}
    infl = _influence(adj, imp, max_depth)
    movers, protected, revoked, applied = [], [], [], 0
    for nid, cur, layer, tags in rows:
        cur = 0.5 if cur is None else cur
        if infl.get(nid, 0) > 0 and not dry_run:
            store.nodes.set_state_attr(nid, "concept_influence", infl[nid])
        blocked = layer == MemoryLayer.CONTEXT.value or bool(_NO_PROTECT_TAGS & set(_json_field(tags, [])))
        if infl.get(nid, 0) >= protect_threshold and not blocked:
            protected.append(nid)
            if not dry_run:
                _protect_upstream(store, nid, infl[nid], cur, floor_importance)
            continue
        if store.nodes.state_attr(nid, "structural_protect") is not None:
            revoked.append(nid)
            if not dry_run:
                _unprotect_upstream(store, nid)
            continue
        d, co = deg.get(nid, 0), cout.get(nid, 0)
        if cur >= 0.95 or (d < min_degree and co < min_causal) or MemoryLayer(layer) == MemoryLayer.SELF:
            continue
        boost = min(beta * min(co, c) / c + gamma * d / max_deg, boost_cap)
        base = cur - float(store.nodes.state_attr(nid, "structural_boost", 0.0) or 0.0)
        new = min(1.0, base + boost)
        delta = round(new - cur, 4)
        if delta >= min_delta:
            movers.append({"node_id": nid, "importance_old": round(cur, 4), "importance_new": round(new, 4),
                           "degree": d, "causal_out": co, "boost": delta, "concept_influence": infl.get(nid, 0)})
            if not dry_run:
                store.nodes.update(nid, importance=new)
                store.nodes.set_state_attr(nid, "structural_boost", round(new - base, 4))
                applied += 1
    return _struct_report(locals(), n_edges, max_deg, movers, infl, protected, revoked, applied)


def _struct_report(p: Dict, n_edges: int, max_deg: int, movers: List[Dict], infl: Dict[str, float],
                   protected: List[str], revoked: List[str], applied: int) -> Dict:
    movers.sort(key=lambda x: -x["boost"])
    top = sorted(infl.items(), key=lambda x: -x[1])[:10]
    keys = ("beta", "gamma", "c", "boost_cap", "min_degree", "min_causal", "min_delta", "max_depth",
            "protect_threshold", "floor_importance")
    return {"mode": "dry_run" if p["dry_run"] else "applied", "params": {k: p[k] for k in keys},
            "edges_total": n_edges, "max_deg": max_deg, "candidates": len(movers), "applied": applied,
            "influence_nodes": len(infl), "protected": len(protected), "revoked": len(revoked),
            "top_influence": [{"node_id": n, "concept_influence": v} for n, v in top], "movers": movers[:50]}
