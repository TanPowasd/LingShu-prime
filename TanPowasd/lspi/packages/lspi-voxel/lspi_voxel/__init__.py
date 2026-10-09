"""LSPI 插件 · voxel：把引擎上的 voxel_world 方法搬成独立可选包。

动作语义与上游 SpacetimeMemoryEngine.voxel_world 逐项一致（verify 有等价性检查），
另加 commit：把实体轨迹经写入闸沉淀进统一认知图。
"""
from __future__ import annotations

import time

from lspi import PluginManifest


class VoxelPlugin:
    manifest = PluginManifest(
        name="voxel", version="0.1.0", lspi=">=1,<2",
        actions=("build", "spawn", "simulate", "trail", "state", "commit"),
        reads=("knowledge",), writes=("world.trail",), extras=(),
        summary="4D 时空占用沙盒（里程碑 2.1）",
    )

    def activate(self, ctx):
        from lingshu.world.voxel_world import VoxelWorld  # 只在插件内依赖 world
        self._VW = VoxelWorld
        self.ctx = ctx
        self._voxel = None

    def deactivate(self):
        self._voxel = None

    def call(self, action, p):
        if self._voxel is None:
            self._voxel = self._VW(size=int(p.get("size", 16)),
                                   ground_level=int(p.get("ground_level", 1)))
        v = self._voxel
        if action == "build":
            blocks = v.build_flatland(trees=int(p.get("trees", 2)), water=bool(p.get("water", True)))
            return {"status": "ok", "blocks": blocks, "world": v.world_state()}
        if action == "spawn":
            pos = tuple(float(x) for x in p.get("pos", [0, 1, 0]))
            vel = tuple(float(x) for x in p.get("velocity", [0, 0, 0]))
            eid = v.spawn_entity(str(p.get("category", "entity")), pos, velocity=vel)
            self.ctx.emit("voxel.spawned", {"entity_id": eid})
            return {"status": "ok", "entity_id": eid}
        if action == "simulate":
            moved = v.simulate(steps=int(p.get("steps", 1)))
            return {"status": "ok", "entities_moved": moved, "step": v._step}
        if action == "trail":
            eid = str(p.get("entity_id", ""))
            return {"status": "ok", "entity_id": eid, "trail": v.trail(eid)}
        if action == "state":
            return {"status": "ok", "world": v.world_state()}
        if action == "commit":
            eid = str(p.get("entity_id", ""))
            trail = v.trail(eid)
            if not trail:
                return {"status": "error", "error": f"实体 {eid} 无轨迹"}
            a, b = trail[0], trail[-1]
            text = f"体素世界实体 {eid} 自步 {a.get('t')} 位置 {a.get('pos')} 移动到步 {b.get('t')} 位置 {b.get('pos')}"
            now = time.time()
            nid = self.ctx.write("world.trail", text, condition={
                "observation_position": "体素世界沙盒",
                "observation_tool": "lspi-voxel 轨迹记录",
                "time_window": (now, now),
                "existence_constraint": f"沙盒步 {a.get('t')}–{b.get('t')} 内成立",
            }, importance=0.6, tags=["voxel", eid])
            return {"status": "ok", "node_id": nid, "content": text}
        return {"status": "error", "error": "unreachable"}
