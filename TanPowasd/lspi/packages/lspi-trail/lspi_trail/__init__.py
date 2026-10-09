"""LSPI 插件 · trail_reason：演示插件间协作只经底座。

- 依赖按**能力名** voxel 声明，不 import lspi_voxel；
- 订阅 voxel.spawned 事件自动跟踪实体；
- 推理结果经写入闸写成 world.inference，并可从统一认知图读回 voxel 写入的轨迹。
"""
from __future__ import annotations

import math
import time

from lspi import PluginManifest


class TrailReasonPlugin:
    manifest = PluginManifest(
        name="trail_reason", version="0.1.0", lspi=">=1,<2",
        actions=("tracked", "displacement", "recall"),
        requires=("voxel",), reads=("knowledge",), writes=("world.inference",),
        summary="基于 voxel 轨迹的位移推理",
    )

    def activate(self, ctx):
        self.ctx = ctx
        self.tracked = []
        ctx.subscribe("voxel.spawned", lambda ev: self.tracked.append(ev["entity_id"]))

    def deactivate(self):
        self.tracked = []

    def call(self, action, p):
        if action == "tracked":
            return {"status": "ok", "tracked": list(self.tracked)}
        if action == "displacement":
            eid = str(p.get("entity_id", ""))
            voxel = self.ctx.capability("voxel")
            if voxel is None:
                return {"status": "voxel_not_ready"}
            tr = voxel.call("trail", {"entity_id": eid}).get("trail", [])
            if len(tr) < 2:
                return {"status": "error", "error": "轨迹不足两点"}
            a, b = tr[0]["pos"], tr[-1]["pos"]
            d = math.dist(a, b)
            now = time.time()
            nid = self.ctx.write("world.inference",
                                 f"推断：实体 {eid} 累计位移 {d:.3f}（由 voxel 轨迹首末点计算）",
                                 condition={"observation_position": "体素世界沙盒",
                                            "observation_tool": "lspi-trail 位移计算",
                                            "time_window": (now, now),
                                            "existence_constraint": "仅对该沙盒轨迹成立"},
                                 tags=["inference", eid])
            return {"status": "ok", "entity_id": eid, "displacement": round(d, 6), "node_id": nid}
        if action == "recall":
            hits = self.ctx.read.search_content(str(p.get("query", "")))
            return {"status": "ok", "hits": [
                {"id": n.id, "content": n.content,
                 "provenance": [t for t in n.tags if t.startswith("provenance:")]}
                for n, _ in hits[: int(p.get("limit", 5))]]}
        return {"status": "error", "error": "unreachable"}
