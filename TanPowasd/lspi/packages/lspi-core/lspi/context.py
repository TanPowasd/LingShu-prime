"""认知上下文：插件看到的「统一认知」——唯一入口，与宿主无关。"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from .hosts import READ_METHODS, _ReadView  # noqa: F401  （P0 兼容导出）


class CognitionContext:
    def __init__(self, manifest, host, registry):
        self.manifest = manifest
        self.host_kind = getattr(host, "kind", "?")
        self.read = host.read_view()
        self._host = host
        self._registry = registry

    def write(self, kind: str, content: str, condition: Dict, importance: float = 0.5, tags=None) -> str:
        return self._host.write(self.manifest, kind, content, condition, importance, tags)

    def emit(self, event_type: str, payload: Optional[Dict] = None) -> int:
        payload = dict(payload or {}, source=self.manifest.provenance)
        self._host.notify(event_type, payload)
        return self._registry._dispatch(event_type, payload)

    def subscribe(self, event_type: str, handler: Callable[[Dict], None]) -> None:
        self._registry._subscribe(event_type, handler, self.manifest.name)

    def capability(self, name: str):
        """拿别的能力；只能拿 manifest.requires 里声明过的，拿不到返回 None。"""
        if name not in self.manifest.requires:
            raise PermissionError(f"{self.manifest.name} 未在 requires 声明 {name!r}")
        return self._registry.capability(name)
