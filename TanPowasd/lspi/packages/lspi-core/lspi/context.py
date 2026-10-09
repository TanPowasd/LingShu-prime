"""认知上下文：插件看到的「统一认知」——唯一入口。"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# 插件可用的只读方法白名单（引擎上的写方法一律不暴露）
READ_METHODS = ("search_content", "recall", "spatiotemporal_query", "get_self_model", "get_stats")


class _ReadView:
    def __init__(self, engine: Any):
        object.__setattr__(self, "_e", engine)

    def __getattr__(self, name):
        if name not in READ_METHODS:
            raise AttributeError(f"只读视图不提供 {name!r}（写入请走 ctx.write）")
        return getattr(object.__getattribute__(self, "_e"), name)

    def __setattr__(self, k, v):
        raise AttributeError("只读视图")


class CognitionContext:
    def __init__(self, manifest, engine, gate, registry):
        self.manifest = manifest
        self.read = _ReadView(engine)
        self._gate = gate
        self._registry = registry
        self._engine = engine

    def write(self, kind: str, content: str, condition: Dict, importance: float = 0.5, tags=None) -> str:
        return self._gate.write(self.manifest, kind, content, condition, importance, tags)

    def emit(self, event_type: str, payload: Optional[Dict] = None) -> int:
        payload = dict(payload or {}, source=self.manifest.provenance)
        if hasattr(self._engine, "notify_event"):
            self._engine.notify_event(event_type, payload)
        return self._registry._dispatch(event_type, payload)

    def subscribe(self, event_type: str, handler: Callable[[Dict], None]) -> None:
        self._registry._subscribe(event_type, handler, self.manifest.name)

    def capability(self, name: str):
        """拿别的能力；只能拿 manifest.requires 里声明过的，拿不到返回 None。"""
        if name not in self.manifest.requires:
            raise PermissionError(f"{self.manifest.name} 未在 requires 声明 {name!r}")
        return self._registry.capability(name)
