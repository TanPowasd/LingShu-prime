"""LSPI 插件 · credibility：world-verify 包的试点（B1）。

包装 lingshu.world.channel_credibility + anchored_verification（均为纯标准库）。
只依赖 lspi 协议，不碰任何宿主 API —— 同一个包可挂身体库引擎，也可挂大脑库认知图。

首个独立小迭代：入口处拒绝非有限的 conf（NaN/inf）。上游 #402 记录了 NaN 经钳位
变成满分支持的问题；插件在边界上先挡住，上游模块不改。
"""
from __future__ import annotations

import math
import time

from lspi import PluginManifest


def _conf(p) -> float:
    c = float(p.get("conf", 1.0))
    if not math.isfinite(c) or not (0.0 <= c <= 1.0):
        raise ValueError(f"conf 须为 [0,1] 内的有限数，得 {p.get('conf')!r}")
    return c


class CredibilityPlugin:
    manifest = PluginManifest(
        name="credibility", version="0.1.0", lspi=">=1,<2",
        actions=("state", "hit", "miss", "verify", "registry", "commit"),
        default_action="state",
        reads=("knowledge",), writes=("world.credibility",),
        hosts=("body", "brain"),
        summary="通道可信度 Beta 后验 + 锚定分级验证（world-verify 试点）",
    )

    def activate(self, ctx):
        from lingshu.world.channel_credibility import ChannelCredibilityRegistry
        from lingshu.world.anchored_verification import AnchoredVerification
        self.ctx = ctx
        self.reg = ChannelCredibilityRegistry()        # 不落盘：状态归宿主认知图（commit）
        self.av = AnchoredVerification(self.reg)

    def deactivate(self):
        self.reg = self.av = None

    def call(self, action, p):
        ch = str(p.get("channel", "visual"))
        try:
            if action == "state":
                return {"status": "ok", **self.reg.channel_state(ch)}
            if action == "hit":
                return {"status": "ok", **self.reg.record_hit(ch, _conf(p), strong=bool(p.get("strong", False)))}
            if action == "miss":
                return {"status": "ok", **self.reg.record_miss(ch, _conf(p), strong=bool(p.get("strong", False)))}
            if action == "verify":
                r = self.av.verify(ch, str(p.get("source", "")), _conf(p), hit=bool(p.get("hit", True)))
                return {"status": "ok", **r}
        except ValueError as e:
            return {"status": "error", "error": str(e)}
        if action == "registry":
            return {"status": "ok", "channels": self.reg.registry()}
        if action == "commit":
            st = self.reg.channel_state(ch)
            text = (f"通道 {ch} 的可信度为 {st['credibility']}（Beta 后验 a={st['a']}, b={st['b']}；"
                    f"命中 {st['hits']} 次、未命中 {st['misses']} 次；状态 {st['status']}）。")
            now = time.time()
            nid = self.ctx.write("world.credibility", text, condition={
                "observation_position": f"channel:{ch}",
                "observation_tool": "channel_credibility",
                "time_window": (now, now),
                "existence_constraint": f"通道 {ch} 在线",
            }, importance=0.5, tags=[f"channel:{ch}"])
            self.ctx.emit("credibility.committed", {"channel": ch, "node_id": nid})
            return {"status": "ok", "node_id": nid, "host": self.ctx.host_kind, **st}
        return {"status": "error", "error": f"未处理动作 {action}"}
