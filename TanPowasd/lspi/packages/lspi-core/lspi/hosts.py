"""宿主适配：同一套插件协议挂到不同宿主上。

插件只认 CognitionContext；宿主差异（写到哪、怎么授权、读什么）全在这里。
  · BodyHost  —— 身体库 lingshu 的 SpacetimeMemoryEngine（本包内置，鸭子类型）
  · BrainHost —— 大脑库 dsh-memory 的认知图（在 lspi-brain-host 包里，本包不 import）
宿主协议（鸭子类型）：
  kind: str                        "body" / "brain"
  read_view() -> 只读对象
  write(manifest, kind, content, condition, importance, tags) -> node_id   失败抛 GateRejected
  notify(event_type, payload) -> None
  authorize(manifest) -> None      越权抛 PermissionError
  reserved: frozenset              宿主自有 op 名，插件不得占用
"""
from __future__ import annotations

from typing import Any, Dict

from .gate import WriteGate

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


class BodyHost:
    kind = "body"
    reserved = frozenset()

    def __init__(self, engine: Any):
        self.engine = engine
        self.gate = WriteGate(engine)

    def read_view(self):
        return _ReadView(self.engine)

    def write(self, manifest, kind, content, condition, importance=0.5, tags=None) -> str:
        return self.gate.write(manifest, kind, content, condition, importance, tags)

    def notify(self, event_type: str, payload: Dict) -> None:
        if hasattr(self.engine, "notify_event"):
            self.engine.notify_event(event_type, payload)

    def authorize(self, manifest) -> None:
        # 身体宿主：插件写入一律经写入闸落知识层，不触及 IMMUTABLE_LAYERS，无额外角色要求。
        return None


def as_host(target: Any):
    """已是宿主则原样返回；否则当作身体引擎包一层（兼容 P0 的 Registry(engine) 用法）。"""
    if all(hasattr(target, a) for a in ("read_view", "write", "authorize")):
        return target
    return BodyHost(target)
