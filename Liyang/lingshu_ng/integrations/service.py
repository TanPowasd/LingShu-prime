# -*- coding: utf-8 -*-
"""集成面共用的操作层：把 :class:`lingshu_ng.engine.MemoryEngine` 的写入 / 召回 / 状态 / capabilities
包成「JSON 进、JSON 出」的四个函数。HTTP 服务与 MCP 适配器都只调这里，保证两条通道的返回形状一致。

线程：一个 :class:`Service` 持有一个引擎和一把锁，所有操作串行执行（SQLite 单连接；见 docs/API_ng.md §10）。
入参校验沿用引擎本身（:mod:`lingshu_ng.inputs`）：类型错抛 ``TypeError`` / ``ValueError``，由调用方转成 400 /
JSON-RPC 错误。本模块不吞异常。
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

#: 写入接受的可选字段（其余字段一律拒绝，避免拼写错误被静默忽略）
PERCEIVE_FIELDS = ("content", "tags", "entities", "importance", "confidence", "layer", "skip_dedup")
#: 召回接受的字段
RECALL_FIELDS = ("query", "limit")
#: 单条正文上限（字符）：集成面额外的防护，引擎本身不设上限
MAX_CONTENT_CHARS = 100_000


class BadRequest(ValueError):
    """请求字段不合法（未知字段 / 缺字段 / 类型错）。HTTP 映射为 400，JSON-RPC 映射为 -32602。"""


def _check_fields(body: Any, allowed, required) -> Dict[str, Any]:
    if not isinstance(body, dict):
        raise BadRequest("请求体必须是 JSON 对象")
    extra = sorted(set(body) - set(allowed))
    if extra:
        raise BadRequest(f"未知字段 {extra}；可用字段 {list(allowed)}")
    miss = [k for k in required if k not in body]
    if miss:
        raise BadRequest(f"缺少字段 {miss}")
    return body


def node_json(node, score: Optional[float] = None) -> Dict[str, Any]:
    """节点 → JSON 字典（只含对外稳定字段）。"""
    d = {"id": node.id, "content": node.content, "layer": getattr(node.layer, "value", node.layer),
         "tags": list(node.tags), "importance": node.importance, "confidence": node.confidence,
         "created_at": node.created_at}
    if score is not None:
        d["score"] = round(float(score), 6)
    return d


class Service:
    """持有一个引擎的操作层。``engine`` 缺省按 ``path`` 新建 :class:`MemoryEngine`。"""

    def __init__(self, path: str = ":memory:", engine=None):
        if engine is None:
            from ..engine import MemoryEngine
            engine = MemoryEngine(path)
        self.engine, self.path, self.lock = engine, path, threading.Lock()

    def perceive(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """写入一条：``{"content": str, 可选 tags/entities/importance/confidence/layer/skip_dedup}``。"""
        b = _check_fields(body, PERCEIVE_FIELDS, ("content",))
        if isinstance(b["content"], str) and len(b["content"]) > MAX_CONTENT_CHARS:
            raise BadRequest(f"content 超过 {MAX_CONTENT_CHARS} 字符")
        kw = {k: b[k] for k in PERCEIVE_FIELDS[1:] if k in b}
        if "layer" in kw:
            from ..types import MemoryLayer
            kw["layer"] = MemoryLayer.coerce(kw["layer"])
        with self.lock:
            w = self.engine.perceive(b["content"], **kw)
        return {"node_id": w.node_id, "action": w.action, "layer": w.layer, "reason": w.reason}

    def recall(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """召回：``{"query": str, "limit": int=10}`` → ``{"hits": [...], "negative": [...]}``。"""
        b = _check_fields(body, RECALL_FIELDS, ("query",))
        with self.lock:
            r = self.engine.recall(b["query"], b.get("limit", 10))
        neg = [x if isinstance(x, (str, int, float, dict, list, type(None))) else str(x) for x in r["negative"]]
        return {"hits": [node_json(n, s) for n, s in r["hits"]], "negative": neg}

    def status(self, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """库状态：版本、schema 版本、各层条数。"""
        _check_fields(body or {}, (), ())
        from .. import __version__
        from ..types import MemoryLayer
        with self.lock:
            nodes = self.engine.store.nodes
            counts = {m.value: nodes.count(m) for m in MemoryLayer}
            sv = self.engine.store.db.schema_version
        return {"version": __version__, "schema_version": sv, "db": self.path, "counts": counts,
                "total": sum(counts.values())}

    def capabilities(self, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """当前生效档位（:meth:`MemoryEngine.capabilities`）。"""
        _check_fields(body or {}, (), ())
        with self.lock:
            return self.engine.capabilities()

    def close(self) -> None:
        """关闭引擎（幂等）。"""
        with self.lock:
            self.engine.close()


#: 操作名 → 方法名（HTTP 路径与 MCP 工具名都由此派生）
OPERATIONS = {"perceive": "perceive", "recall": "recall", "status": "status", "capabilities": "capabilities"}
