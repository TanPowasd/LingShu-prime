# -*- coding: utf-8 -*-
"""subgraph · 子图替换（可嵌套认知图：子部件级更新）

旧实现（#139）「先删后挂」：先逐个删除旧子树，再递归挂入新子树；新子树任何一处非法（缺 id、
importance 为 NaN、坐标非数值）都会在删除之后抛错——旧子树已丢、新子树只挂了一半。

不变量：
  G1 先完整校验新子树（每节点 str id、id 不重复、数值有限且 importance/confidence ∈[0,1]、
     深度 ≤ :data:`MAX_DEPTH`），父节点必须存在；任何一条不满足 ⇒ ValueError，库零改动。
  G2 删除旧子树（旧根 + 经 hierarchical 入边可达的全部后代）与挂入新子树在**同一事务**内；
     删除受 LayerPolicy 守卫（共享层子树不可被替换），任何异常整体回滚。旧根 = 父节点、父节点落在
     旧子树内、旧子树含受保护节点 ⇒ 拒绝（ValueError / PermissionError），库零改动。
  G3 新节点 = 知识层、modality 默认 visual、标签 [subgraph_replace, img:<id>]、实体 <id>；
     新根以 hierarchical 边（新→父）挂接，与旧版同形。
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Set

from . import graphquery
from .numeric import unit
from .types import EdgeType

__all__ = ["replace_subtree", "validate_subtree", "MAX_DEPTH"]

MAX_DEPTH = 64


def _coord(node: Dict) -> Dict[str, float]:
    raw = (node.get("spatial_coordinates") or {}).get("image2d", [0, 0]) or []
    xs = [float(v) for v in list(raw)[:2]] + [0.0, 0.0]
    if not all(math.isfinite(v) for v in xs[:2]):
        raise ValueError(f"节点 {node.get('id')} 坐标非有限值")
    return {"image2d_x": xs[0], "image2d_y": xs[1]}


def validate_subtree(node: Any, depth: int = 0, seen: Optional[Set[str]] = None) -> int:
    """G1：递归校验，返回节点总数。"""
    seen = set() if seen is None else seen
    if depth > MAX_DEPTH:
        raise ValueError(f"子树深度超过 {MAX_DEPTH}")
    if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
        raise ValueError("子树节点必须是含非空字符串 id 的映射")
    if node["id"] in seen:
        raise ValueError(f"子树节点 id 重复: {node['id']}")
    seen.add(node["id"])
    unit(float(node.get("importance", 0.5)), "importance")
    unit(float(node.get("confidence", 0.9)), "confidence")
    _coord(node)
    json.dumps(node.get("content", {}), ensure_ascii=False, allow_nan=False)
    subs = (node.get("subgraph") or {}).get("nodes", [])
    if not isinstance(subs, list):
        raise ValueError("subgraph.nodes 必须是列表")
    return 1 + sum(validate_subtree(s, depth + 1, seen) for s in subs)


def _attach(engine: Any, node: Dict, parent: Optional[str], counter: List[int]) -> str:
    r = engine.perceive(json.dumps(node.get("content", {}), ensure_ascii=False, allow_nan=False),
                        modality=node.get("modality", "visual"), spatial=_coord(node),
                        importance=float(node.get("importance", 0.5)),
                        tags=["subgraph_replace", "img:" + node["id"]], entities=[node["id"]], skip_dedup=True)
    counter[0] += 1
    if parent:
        engine.link(r.node_id, parent, EdgeType.HIERARCHICAL, confidence=float(node.get("confidence", 0.9)),
                    evidence="subgraph_replace")
    for sub in (node.get("subgraph") or {}).get("nodes", []):
        _attach(engine, sub, r.node_id, counter)
    return r.node_id


def replace_subtree(engine: Any, parent_id: str, old_root_id: str, new_subtree: Dict) -> Dict:
    """G1–G3：返回 {new_root_id, new_nodes, removed_nodes}。"""
    validate_subtree(new_subtree)
    nodes = engine.store.nodes
    if parent_id and nodes.get(parent_id) is None:
        raise ValueError(f"父节点不存在: {parent_id}")
    if old_root_id == parent_id:
        raise ValueError("old_sub_root_id 不能等于 parent_id（会删掉父节点自身）")
    desc = graphquery.traverse(engine.store, old_root_id, ["hierarchical"], "in", MAX_DEPTH, 0.0,
                               max_nodes=10 ** 9)
    removed = [old_root_id] + [d["node_id"] for d in desc]
    if parent_id in removed:
        raise ValueError("父节点位于旧子树内（层级环），拒绝替换")
    guarded = set(engine.store.registry.protected_ids()) & set(removed)
    if guarded:
        raise PermissionError(f"旧子树含受保护节点，拒绝替换: {sorted(guarded)[:5]}")
    for nid in removed:                        # #244：SUB 替换子树不得级联删触及共享层的边
        engine.store.policy.check_node_cascade(engine.store.edges, nodes, nid)
    counter = [0]
    with engine.store.db.tx():
        gone = sum(1 for nid in removed if nodes.delete(nid))
        root = _attach(engine, new_subtree, parent_id, counter)
    return {"new_root_id": root, "new_nodes": counter[0], "removed_nodes": gone}
