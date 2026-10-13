# -*- coding: utf-8 -*-
"""promotion · 固化终裁的唯一实现（stab-r1b：引擎与 store 级兼容门面共用）

终裁规则（与 rel-v1.14 的 ``MemoryEngine.adjudicate_promotion`` 逐字相同，只是搬到这里供两处调用）：
  * 设计者密钥闸 fail-closed（:func:`lingshu_ng.governance.require_designer`，失败抛 PermissionError）；
  * 提案不存在 / 被提案节点已不存在 ⇒ 返回 None，不写库；
  * 仓储层 ``decide_proposal`` 只接受已复核的提案，并比对复核时绑定的内容（不一致 ⇒ None）；
  * 通过 ⇒ 节点进结构层（confidence 1.0）；否决 ⇒ 记 ``promotion`` 负记忆；两者都去掉 ``promotion_pending`` 标签。
"""
from __future__ import annotations

from typing import Optional

from .governance import require_designer
from .types import MemoryLayer

__all__ = ["adjudicate"]


def adjudicate(store, negative, proposal_id: str, by: str, approved: bool,
               designer_key: Optional[str] = None) -> Optional[str]:
    """终裁：返回节点 id（未裁决返回 None）。``store`` 为 ng :class:`~lingshu_ng.store.Store`，``negative`` 为其负记忆。"""
    require_designer(designer_key, "晋升终裁")
    p = store.registry.proposal(proposal_id)
    node = store.nodes.get(p["node_id"]) if p else None
    if node is None:
        return None
    with store.db.tx():
        d = store.registry.decide_proposal(proposal_id, by, approved, designer_key, node.content or "")
        if d is None:
            return None
        store.nodes.remove_tags(node.id, ["promotion_pending"])
        if approved:
            store.nodes.update(node.id, allow_transition=True, layer=MemoryLayer.STRUCTURE, confidence=1.0)
        else:
            negative.record("promotion", f"固化提案被拒：{(node.content or '')[:60]}",
                            f"维生系统终裁拒绝（{by}）", subject=node.content or "")
    return node.id
