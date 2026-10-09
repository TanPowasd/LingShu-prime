# -*- coding: utf-8 -*-
"""SpacetimeMemoryEngine 的世界模型外观（WorldFacadeMixin）· issue #178 拆分第一阶段

本文件为**纯搬移**：以下 13 个方法逐字取自 2bb8291 的 ``lingshu/core/core.py``
（``SpacetimeMemoryEngine.world3d`` … ``_load_vprims_from_memory``，原 L2864–L3694），
方法体零改动（tests/test_core_world_facade_split.py 以源码 sha256 守卫）。
``SpacetimeMemoryEngine`` 继承本 mixin，故 ``engine.world3d(...)`` 等调用路径、
签名、返回值与异常行为均不变。

目的：把 core.py 内对 ``..world`` 的全部 27 处方法内导入从记忆引擎本体中隔离出来，
为第二阶段（外观迁出 core 包、反转 core→world 依赖）做准备。见 _out/REFACTOR_PLAN.md。

方法体内所用的模块级名字只有 ``math`` / ``os``（AST 自由变量分析），在此导入；
``from ..world.x`` / ``from .game_web.x`` 相对导入的锚点包仍为 ``lingshu.core``，解析结果不变。
"""
import math  # noqa: F401  方法体内使用
import os  # noqa: F401  方法体内使用


class WorldFacadeMixin:
    """世界模型/视觉原语外观方法（字符串 action 分发）。由 SpacetimeMemoryEngine 继承；
    方法依赖宿主的 ``self.store`` / ``self.add_perception`` / ``self._note_action`` 等。"""

    def world3d(self, action: str, params: dict = None) -> dict:
        """WORLD3D-REV1 时空重建：语义 → 3D 空间与颜色（灵枢自己的文生图）。

        - build: 从记忆中的视觉原语（vprim 标签）重建 3D 世界
          （params: limit 记忆节点数, screen_w/h 参考视角）
        - render: 渲染 3D 世界为图像（params: path 输出路径, yaw/pitch/cx
          相机参数——任意视角透视投影；2D 是 3D 透视下的情况）
        - status: 当前 3D 世界状态（物体/相机）
        - add: 手动添加物体（params: category, bbox 或 center/size/color）"""
        p = params or {}
        try:
            from ..world.world3d import World3D, Camera3D
        except ImportError:
            try:
                from ..world.world3d import World3D, Camera3D
            except Exception as e:
                return {"status": "world3d_not_ready", "error": str(e)}
        # 世界状态（跨调用保持于引擎）
        if not hasattr(self, "_world3d"):
            self._world3d = World3D()

        if action == "build":
            try:
                from ..world.vprim import VPrim, parse_anchor  # noqa: F401
            except ImportError:
                from ..world.vprim import parse_anchor  # noqa: F401
            world = World3D()
            nodes = self.store.get_nodes_by_tag("vprim", limit=int(p.get("limit", 20)))
            sw = int(p.get("screen_w", 800))
            sh = int(p.get("screen_h", 600))
            multiview = bool(p.get("multiview", False))  # 多视角融合（阶段1 里程碑1.1）
            added = 0
            if multiview:
                # 多视角模式：按类别分组，同类别多帧用不同虚拟视角 → 三角化
                # 视角派生：按时间戳/索引产生 yaw 偏移（模拟环绕观测，借鉴 DUSt3R）
                import itertools
                try:
                    from ..world.world3d import Camera3D as _C3D
                except ImportError:
                    from ..world.world3d import Camera3D as _C3D
                per_cat: dict = {}
                for n in nodes:
                    text = n.content or ""
                    for token in text.split("；"):
                        vp = parse_anchor(token)
                        if vp is not None:
                            per_cat.setdefault(vp.category, []).append(vp)
                for cat, vps in per_cat.items():
                    for idx, vp in enumerate(vps):
                        # 虚拟视角：同一物体多帧 = 环绕观测（yaw 随索引旋转）
                        yaw_i = math.radians(idx * 30 - 30) if len(vps) > 1 else 0.0
                        cam_v = _C3D(yaw=yaw_i, pitch=0.1, cx=-1.5 if idx % 2 == 0 else 1.5, cy=1.2)
                        res = world.add_view(vp.category, vp.bbox, sw, sh,
                                            camera=cam_v, confidence=vp.confidence)
                        if res.get("triangulated"):
                            added += 1
            else:
                for n in nodes:
                    text = n.content or ""
                    for token in text.split("；"):
                        vp = parse_anchor(token)
                        if vp is not None:
                            world.add_vprim(vp, sw, sh)
                            added += 1
            self._world3d = world
            return {"status": "ok", "objects": added,
                    "mode": "multiview" if multiview else "single_view",
                    "scene": world.scene_text(),
                    "detail": world.to_dict()}
        if action == "render":
            cam = Camera3D(yaw=float(p.get("yaw", 0)), pitch=float(p.get("pitch", 0)),
                           cx=float(p.get("cx", 0)), cy=float(p.get("cy", 1.2)))
            sw = int(p.get("screen_w", 800))
            sh = int(p.get("screen_h", 600))
            path = str(p.get("path", ""))
            img = self._world3d.render(sw, sh, camera=cam)
            if path:
                img.save(path)
                return {"status": "ok", "path": os.path.abspath(path),
                        "scene": self._world3d.scene_text()}
            import io as _io
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            return {"status": "ok", "in_memory": True,
                    "bytes": len(buf.getvalue()),
                    "scene": self._world3d.scene_text()}
        if action == "graph":
            """3D 语义锚点图（里程碑1.2）：世界物体 → 图结构（节点=锚点，边=关系）。
            核心哲学：事物是其关系的总和。infer=False 跳过关系推理。"""
            infer = bool(p.get("infer", True))
            g = self._world3d.build_anchor_graph(infer=infer)
            return {"status": "ok", "graph": g}
        if action == "verify":
            """多感知机锚点验证（里程碑1.4）：记录某通道对锚点的验证证据 → 确认度判定。
            params: anchor_id, channel(visual/tactile/audio/action/prediction), evidence[0,1]。
            核心：一个事物不能只有视觉一层信息——多通道协同确认（打破视觉自证陷阱）。"""
            aid = str(p.get("anchor_id", ""))
            channel = str(p.get("channel", "visual"))
            evidence = float(p.get("evidence", 0.5))
            strong = p.get("strong")
            if not aid:
                return {"status": "error", "error": "anchor_id 必填"}
            r = self._world3d.verify_anchor(aid, channel, evidence,
                                            strong=strong if strong is not None else None)
            return {"status": "ok", "verification": r}
        if action == "verify_conflict":
            """多通道矛盾检测（里程碑1.4）：通道观测与锚点声明冲突 → 降级。
            params: anchor_id, channel, expected, actual。"""
            aid = str(p.get("anchor_id", ""))
            ch = str(p.get("channel", ""))
            exp = str(p.get("expected", ""))
            act = str(p.get("actual", ""))
            if not aid or not ch or not exp or not act:
                return {"status": "error", "error": "anchor_id/channel/expected/actual 必填"}
            r = self._world3d.verify_conflict(aid, ch, exp, act)
            return {"status": "ok", "verification": r}
        if action == "status":
            return {"status": "ok", **self._world3d.to_dict()}
        if action == "add":
            try:
                from ..world.vprim import VPrim, bbox_from_xywh  # noqa: F401
            except ImportError:
                from ..world.vprim import VPrim  # noqa: F401
            category = str(p.get("category", ""))
            bbox = p.get("bbox")
            if not category or not bbox or len(bbox) != 4:
                return {"status": "error", "error": "category 与 bbox=[x1,y1,x2,y2] 必填"}
            vp = VPrim(category, tuple(float(v) for v in bbox),
                       float(p.get("confidence", 0.5)), source="manual")
            self._world3d.add_vprim(vp, int(p.get("screen_w", 800)),
                                    int(p.get("screen_h", 600)))
            return {"status": "ok", "scene": self._world3d.scene_text()}
        if action == "add_view":
            """多视角融合（阶段1 · 里程碑1.1）：category + bbox + 视角相机 → 三角化。
            首次观测记录；≥2 视角触发射线交汇收敛（借鉴 DUSt3R 多视图对齐）。"""
            category = str(p.get("category", ""))
            bbox = p.get("bbox")
            if not category or not bbox or len(bbox) != 4:
                return {"status": "error", "error": "category 与 bbox=[x1,y1,x2,y2] 必填"}
            sw = int(p.get("screen_w", 800))
            sh = int(p.get("screen_h", 600))
            # 视角相机（可选：缺省当前相机）
            cam = None
            if p.get("camera"):
                cp = p["camera"]
                cam = Camera3D(yaw=float(cp.get("yaw", 0)), pitch=float(cp.get("pitch", 0)),
                               cx=float(cp.get("cx", 0)), cy=float(cp.get("cy", 1.2)))
            result = self._world3d.add_view(category, [float(v) for v in bbox],
                                            sw, sh, camera=cam,
                                            confidence=float(p.get("confidence", 0.5)))
            result["scene"] = self._world3d.scene_text()
            return {"status": "ok", **result}
        return {"status": "error", "error": f"未知动作 {action}（可用: build/render/status/add/add_view/graph/verify/verify_conflict）"}

    def voxel_world(self, action: str, params: dict = None) -> dict:
        """小型我的世界（里程碑2.1 · 4D 时空占用沙盒）：
        - build: 生成平地世界（params: size, trees, water）
        - spawn: 生成动态实体（params: category, pos, velocity）
        - simulate: 时空演化推进（params: steps——实体按速度移动）
        - trail: 实体时空轨迹（params: entity_id——A→B 完整记录）
        - state: 世界状态（方块/实体/时间步）"""
        p = params or {}
        try:
            from ..world.voxel_world import VoxelWorld
        except ImportError:
            try:
                from ..world.voxel_world import VoxelWorld
            except Exception as e:
                return {"status": "voxel_not_ready", "error": str(e)}
        if not hasattr(self, '_voxel'):
            self._voxel = VoxelWorld(size=int(p.get('size', 16)),
                                    ground_level=int(p.get('ground_level', 1)))
        if action == "build":
            blocks = self._voxel.build_flatland(trees=int(p.get("trees", 2)),
                                               water=bool(p.get("water", True)))
            return {"status": "ok", "blocks": blocks, "world": self._voxel.world_state()}
        if action == "spawn":
            category = str(p.get("category", "entity"))
            pos = tuple(float(v) for v in p.get("pos", [0, 1, 0]))
            vel = tuple(float(v) for v in p.get("velocity", [0, 0, 0]))
            eid = self._voxel.spawn_entity(category, pos, velocity=vel)
            return {"status": "ok", "entity_id": eid}
        if action == "simulate":
            steps = int(p.get("steps", 1))
            moved = self._voxel.simulate(steps=steps)
            return {"status": "ok", "entities_moved": moved, "step": self._voxel._step}
        if action == "trail":
            eid = str(p.get("entity_id", ""))
            trail = self._voxel.trail(eid)
            return {"status": "ok", "entity_id": eid, "trail": trail}
        if action == "state":
            return {"status": "ok", "world": self._voxel.world_state()}
        return {"status": "error", "error": f"未知动作 {action}（可用: build/spawn/simulate/trail/state）"}

    def wm_simloop(self, action: str, params: dict = None) -> dict:
        """世界模型推演循环（里程碑 M5.1 · WM-SIMLOOP-REV1）：
        - setup: 构建推演循环（size/seed/entities/mask/wal_path）
        - run: 推进 n tick（可选 script=drift_sinusoid 内置确定性外部演化）
        - step: 推进 n tick（无汇总）
        - load: 认知图现在时节点 → 世界图先验（mdcg_root）
        - flush: WAL → 认知图 contextual 载荷（可选 out_path）
        - wal / growth: 审计轨迹 / 拓扑生长事件
        - report / state: 报告与状态"""
        p = params or {}
        try:
            from ..world.wm_simloop import SimulationLoop
        except ImportError:
            try:
                from ..world.wm_simloop import SimulationLoop
            except Exception as e:
                return {"status": "simloop_not_ready", "error": str(e)}
        if action == "setup":
            wal = p.get("wal_path") or os.path.join("data", "wm_simloop_wal.jsonl")
            sl_ = SimulationLoop(size=int(p.get("size", 40)),
                                 seed=int(p.get("seed", 42)), wal_path=wal)
            sl_.scene.create_scene(trees=int(p.get("trees", 0)), water=False)
            eids = []
            for e in p.get("entities", []):
                eids.append(sl_.scene.add_entity(
                    str(e.get("category", "entity")),
                    behavior=str(e.get("behavior", "wander")),
                    pos=tuple(float(v) for v in e.get("pos", [2, 1.5, 2])),
                    speed=float(e.get("speed", 0.3)),
                    goal=str(e.get("goal", ""))))
            sl_._mask = set(str(x) for x in p.get("mask", []))
            sl_.wm.perceive(observations=sl_._observe())
            self._simloop = sl_
            return {"status": "ok", "entity_ids": eids,
                    "masked": sorted(sl_._mask), "wal_path": wal,
                    "state": sl_.state()}
        if not hasattr(self, '_simloop'):
            return {"status": "error", "error": "推演循环未初始化（先 setup）"}
        sl = self._simloop
        if action == "run":
            n = int(p.get("n", 10))
            script = str(p.get("script", ""))
            target = str(p.get("target", ""))
            if script == "drift_sinusoid" and target in sl.scene.entities:
                amp = float(p.get("amplitude", 2.5))
                drift = float(p.get("drift", 0.55))
                freq = float(p.get("freq", 0.45))
                z = sl.scene.entities[target].pos[2]

                def ext(scene, tick):
                    scene.entities[target].pos = (
                        3.0 + drift * tick + amp * math.sin(freq * tick), 1.5, z)
                sl.step(n=1)
                sl.step(n=max(0, n - 1), external=ext)
            else:
                sl.run(n=n)
            return {"status": "ok", "report": sl.report()}
        if action == "step":
            return {"status": "ok", "state": sl.step(n=int(p.get("n", 1)))}
        if action == "load":
            return {"status": "ok",
                    "load": sl.load_priors(str(p.get("mdcg_root", "")))}
        if action == "flush":
            out = p.get("out_path")
            r = sl.flush_payloads(out_path=str(out) if out else None)
            return {"status": "ok",
                    "flush": {k: r[k] for k in ("payload", "written", "note")}}
        if action == "wal":
            lim = int(p.get("limit", 20))
            return {"status": "ok", "wal": sl.wal[-lim:]}
        if action == "growth":
            return {"status": "ok",
                    "growth": sl.growth_events(limit=int(p.get("limit", 20)))}
        if action == "report":
            return {"status": "ok", "report": sl.report()}
        if action == "state":
            return {"status": "ok", "state": sl.state()}
        return {"status": "error", "error": f"未知动作 {action}（可用: setup/run/step/load/flush/wal/growth/report/state）"}

    def scene_simulator(self, action: str, params: dict = None) -> dict:
        """场景级世界模拟器（里程碑2.3 · 自主行为玩家）：
        - create: 创建场景（size/trees/water）
        - entity: 添加自主实体（category/behavior/pos/speed/goal——wander/seek/avoid/flee/follow）
        - path: 定义巡逻路径（path_id/points）
        - step: 推进 n tick（所有自主实体决策→行动→场景演化）
        - state: 场景状态（实体+行为+演化历史）
        - log: 自主行为决策记录（可审计）"""
        p = params or {}
        try:
            from ..world.scene_simulator import SceneSimulator
        except ImportError:
            try:
                from ..world.scene_simulator import SceneSimulator
            except Exception as e:
                return {"status": "scene_not_ready", "error": str(e)}
        if not hasattr(self, '_scene'):
            self._scene = SceneSimulator(size=int(p.get('size', 24)),
                                       ground_level=int(p.get('ground_level', 1)))
        if action == "create":
            r = self._scene.create_scene(trees=int(p.get("trees", 4)),
                                        water=bool(p.get("water", True)))
            return {"status": "ok", "scene": r}
        if action == "entity":
            eid = self._scene.add_entity(
                str(p.get("category", "entity")),
                behavior=str(p.get("behavior", "wander")),
                pos=tuple(float(v) for v in p.get("pos", [2, 1.5, 2])),
                speed=float(p.get("speed", 0.3)),
                goal=str(p.get("goal", "")))
            return {"status": "ok", "entity_id": eid}
        if action == "path":
            self._scene.add_path(str(p.get("path_id", "")), p.get("points", []))
            return {"status": "ok", "path_id": str(p.get("path_id", ""))}
        if action == "step":
            r = self._scene.step(n=int(p.get("n", 1)))
            return {"status": "ok", "step": r}
        if action == "state":
            return {"status": "ok", "scene": self._scene.scene_state()}
        if action == "log":
            return {"status": "ok", "log": self._scene.behavior_log(limit=int(p.get("limit", 30)))}
        return {"status": "error", "error": f"未知动作 {action}（可用: create/entity/path/step/state/log）"}

    def spacetime_consistency(self, action: str, params: dict = None) -> dict:
        """时空一致性验证（里程碑2.4 · 阶段2收官）——世界模型自洽判定：
        - init: 初始化一致性验证器（size/window/hit_threshold/drift_rate/drift_ticks/consistent_rate/min_consistent_ticks）
        - create: 创建场景（透传 SceneSimulator）
        - entity: 添加自主实体（wander/seek/avoid/flee/follow）
        - path: 定义巡逻路径
        - run: 持续运行 n tick（每 tick 预测下一状态 vs 实际 → 滚动命中率）
        - step: 验证一步（预测 vs 实际 + 不变量校验 + 漂移检测）
        - teleport: 排队外部事件瞬移（模型无法解释 → 演示漂移检测）
        - report: 自洽度报告（总体/滚动/分行为命中率 + 漂移事件 + 判定）
        - self_consistent: 世界模型自洽判定（持续运行中预测与实际保持一致性）
        - drift: 漂移事件列表
        - history: 预测验证历史（可审计）"""
        p = params or {}
        try:
            from ..world.spacetime_consistency import SpacetimeConsistency
        except ImportError:
            try:
                from ..world.spacetime_consistency import SpacetimeConsistency
            except Exception as e:
                return {"status": "stc_not_ready", "error": str(e)}
        if not hasattr(self, '_stc'):
            self._stc = SpacetimeConsistency(
                size=int(p.get('size', 24)),
                ground_level=int(p.get('ground_level', 1)),
                window=int(p.get('window', 20)),
                hit_threshold=float(p.get('hit_threshold', 0.5)),
                drift_rate=float(p.get('drift_rate', 0.7)),
                drift_ticks=int(p.get('drift_ticks', 5)),
                consistent_rate=float(p.get('consistent_rate', 0.85)),
                min_consistent_ticks=int(p.get('min_consistent_ticks', 50)))
        if action == "create":
            r = self._stc.create_scene(trees=int(p.get("trees", 4)),
                                       water=bool(p.get("water", True)))
            return {"status": "ok", "scene": r}
        if action == "entity":
            eid = self._stc.add_entity(
                str(p.get("category", "entity")),
                behavior=str(p.get("behavior", "wander")),
                pos=tuple(float(v) for v in p.get("pos", [2, 1.5, 2])),
                speed=float(p.get("speed", 0.3)),
                goal=str(p.get("goal", "")))
            return {"status": "ok", "entity_id": eid}
        if action == "path":
            self._stc.add_path(str(p.get("path_id", "")), p.get("points", []))
            return {"status": "ok", "path_id": str(p.get("path_id", ""))}
        if action == "run":
            r = self._stc.run(n=int(p.get("n", 10)))
            return {"status": "ok", "run": r}
        if action == "step":
            r = self._stc.step_verified()
            return {"status": "ok", "step": r}
        if action == "teleport":
            ok = self._stc.teleport(str(p.get("entity_id", "")),
                                    tuple(float(v) for v in p.get("pos", [0, 0, 0])))
            return {"status": "ok" if ok else "error",
                    "queued": ok}
        if action == "report":
            return {"status": "ok", "report": self._stc.consistency_report()}
        if action == "self_consistent":
            rep = self._stc.consistency_report()
            return {"status": "ok", "self_consistent": rep["self_consistent"],
                    "verdict": rep["verdict"],
                    "overall_hit_rate": rep["overall_hit_rate"],
                    "rolling_hit_rate": rep["rolling_hit_rate"]}
        if action == "drift":
            return {"status": "ok", "drift_events": self._stc.drift_events(),
                    "drift_active": self._stc.drift_active()}
        if action == "history":
            return {"status": "ok",
                    "history": self._stc.prediction_history(limit=int(p.get("limit", 10)))}
        return {"status": "error", "error": f"未知动作 {action}（可用: init/create/entity/path/run/step/teleport/report/self_consistent/drift/history）"}

    def world_model(self, action: str, params: dict = None) -> dict:
        """统一世界模型（里程碑3.1 · HERMES 式统一架构）：世界状态表征作为
        理解/生成/验证共享的同一骨干——
        - init: 初始化（size/ground_level/seed）
        - create: 物理世界创建场景（trees/water）
        - entity: 物理世界添加自主实体（行为已知=世界真相，模型只能观测）
        - path: 定义巡逻路径
        - perceive: 理解端口（观测→世界图；生成先验注入理解=预测-观测一致性异常检测）
        - generate: 生成端口（世界图→候选未来，顺序语义外推+不确定边界）
        - verify: 验证端口（外部观察者对比→命中率）
        - run: 持续运行 n tick（generate→物理演化→perceive→verify）
        - patterns: 观测-only 行为模式推断（关系/速度/方向一致性）
        - anomalies: 预测-观测异常事件（模型缺口/外部事件）
        - graph: 世界图导出（节点+边+观测溯源条件空间）
        - history: 4D 演化历史
        - state: 模型状态"""
        p = params or {}
        try:
            from ..world.world_model import UnifiedWorldModel
        except ImportError:
            try:
                from ..world.world_model import UnifiedWorldModel
            except Exception as e:
                return {"status": "wm_not_ready", "error": str(e)}
        if not hasattr(self, '_wmodel'):
            self._wmodel = UnifiedWorldModel(
                size=int(p.get('size', 24)),
                ground_level=int(p.get('ground_level', 1)),
                seed=int(p.get('seed', 42)))
        if action == "create":
            r = self._wmodel.world.create_scene(trees=int(p.get("trees", 2)),
                                                water=bool(p.get("water", False)))
            return {"status": "ok", "scene": r}
        if action == "entity":
            eid = self._wmodel.world.add_entity(
                str(p.get("category", "entity")),
                behavior=str(p.get("behavior", "wander")),
                pos=tuple(float(v) for v in p.get("pos", [2, 1.5, 2])),
                speed=float(p.get("speed", 0.3)),
                goal=str(p.get("goal", "")))
            return {"status": "ok", "entity_id": eid}
        if action == "path":
            self._wmodel.world.add_path(str(p.get("path_id", "")), p.get("points", []))
            return {"status": "ok", "path_id": str(p.get("path_id", ""))}
        if action == "perceive":
            r = self._wmodel.perceive(tool=str(p.get("tool", "observer")))
            return {"status": "ok", "perceive": r}
        if action == "generate":
            r = self._wmodel.generate(horizon=int(p.get("horizon", 1)))
            return {"status": "ok", "generate": r}
        if action == "verify":
            r = self._wmodel.verify()
            return {"status": "ok", "verify": r}
        if action == "run":
            r = self._wmodel.verify_run(n=int(p.get("n", 10)))
            return {"status": "ok", "run": r}
        if action == "patterns":
            return {"status": "ok", "patterns": self._wmodel.patterns()}
        if action == "anomalies":
            return {"status": "ok",
                    "anomalies": self._wmodel.anomalies(limit=int(p.get("limit", 20)))}
        if action == "graph":
            return {"status": "ok", "graph": self._wmodel.graph()}
        if action == "history":
            return {"status": "ok",
                    "history": self._wmodel.history_view(limit=int(p.get("limit", 10)))}
        if action == "state":
            return {"status": "ok", "model": self._wmodel.state()}
        return {"status": "error", "error": f"未知动作 {action}（可用: init/create/entity/path/perceive/generate/verify/run/patterns/anomalies/graph/history/state）"}

    def world_learner(self, action: str, params: dict = None) -> dict:
        """自监督世界学习（里程碑3.2 · V-JEPA 式）：从观测序列无标注学转移函数——
        - init: 初始化（size/seed/window）
        - create: 物理世界创建场景
        - entity: 物理世界添加自主实体
        - path: 定义巡逻路径
        - run: 物理世界演化 n tick + 观测（数据采集，观测面只暴露位置/类别）
        - learn: 自监督学习（从观测序列估计学得模型参数）
        - predict: 用学得模型预测下一状态（带不确定边界）
        - evaluate: 评估协议（train/eval：学得 vs naive 基线 vs 真模型上界 → 认知缺口）
        - curve: 增量学习曲线（观测增加 → 命中率提升 = 认知缺口收紧）
        - masked: 遮挡重建损失（V-JEPA 自监督信号）
        - model: 学得模型参数导出（白箱可审计）
        - history: 观测序列
        - state: 学习者状态"""
        p = params or {}
        try:
            from ..world.world_learner import WorldLearner
        except ImportError:
            try:
                from ..world.world_learner import WorldLearner
            except Exception as e:
                return {"status": "wl_not_ready", "error": str(e)}
        if not hasattr(self, '_wlearner'):
            self._wlearner = WorldLearner(
                size=int(p.get('size', 24)),
                ground_level=int(p.get('ground_level', 1)),
                seed=int(p.get('seed', 42)),
                window=int(p.get('window', 6)))
        if action == "create":
            r = self._wlearner.world.create_scene(trees=int(p.get("trees", 2)),
                                                  water=bool(p.get("water", False)))
            return {"status": "ok", "scene": r}
        if action == "entity":
            eid = self._wlearner.world.add_entity(
                str(p.get("category", "entity")),
                behavior=str(p.get("behavior", "wander")),
                pos=tuple(float(v) for v in p.get("pos", [2, 1.5, 2])),
                speed=float(p.get("speed", 0.3)),
                goal=str(p.get("goal", "")))
            return {"status": "ok", "entity_id": eid}
        if action == "path":
            self._wlearner.world.add_path(str(p.get("path_id", "")), p.get("points", []))
            return {"status": "ok", "path_id": str(p.get("path_id", ""))}
        if action == "run":
            r = self._wlearner.run(n=int(p.get("n", 10)))
            return {"status": "ok", "run": r}
        if action == "learn":
            m = self._wlearner.learn()
            return {"status": "ok", "learned": m}
        if action == "predict":
            r = self._wlearner.predict(horizon=int(p.get("horizon", 1)))
            return {"status": "ok", "predict": r}
        if action == "evaluate":
            r = self._wlearner.evaluate(train_ticks=int(p.get("train_ticks", 30)),
                                        eval_ticks=int(p.get("eval_ticks", 15)))
            return {"status": "ok", "evaluate": r}
        if action == "curve":
            r = self._wlearner.learning_curve(
                epochs=int(p.get("epochs", 4)),
                per_epoch_ticks=int(p.get("per_epoch_ticks", 10)),
                eval_ticks=int(p.get("eval_ticks", 8)))
            return {"status": "ok", "curve": r}
        if action == "masked":
            r = self._wlearner.masked_loss()
            return {"status": "ok", "masked": r}
        if action == "model":
            return {"status": "ok", "model": self._wlearner.model_params()}
        if action == "history":
            return {"status": "ok",
                    "history": self._wlearner.history_view(limit=int(p.get("limit", 10)))}
        if action == "state":
            return {"status": "ok", "learner": self._wlearner.state()}
        return {"status": "error", "error": f"未知动作 {action}（可用: init/create/entity/path/run/learn/predict/evaluate/curve/masked/model/history/state）"}

    def curiosity_explorer(self, action: str, params: dict = None) -> dict:
        """好奇驱动探索（里程碑3.3）：主动选择观测最大化信息增益——
        - init: 初始化（size/seed/window/budget）
        - create: 物理世界创建场景（追逐链测试世界）
        - entity: 添加实体
        - path: 定义巡逻路径
        - explore: 探索 n tick（budget/policy：curiosity/random/round_robin）
        - step: 探索一步（决策日志：chosen + IG 分解）
        - probe: 全带宽探针评估（学得模型 held-out 命中率）
        - compare: 策略对比（同世界轨迹：好奇 vs 随机 vs 轮询）
        - curiosity: 好奇心摘要（观测分布/不确定度趋势/异常计数）
        - uncertainty: 不确定度轨迹
        - model: 学得模型参数
        - history: 观测序列
        - state: 探索器状态"""
        p = params or {}
        try:
            from ..world.curiosity_explorer import CuriosityExplorer
        except ImportError:
            try:
                from ..world.curiosity_explorer import CuriosityExplorer
            except Exception as e:
                return {"status": "cx_not_ready", "error": str(e)}
        if not hasattr(self, '_curious'):
            self._curious = CuriosityExplorer(
                size=int(p.get('size', 24)),
                ground_level=int(p.get('ground_level', 1)),
                seed=int(p.get('seed', 42)),
                window=int(p.get('window', 6)))
        if action == "create":
            r = self._curious.world.create_scene(trees=int(p.get("trees", 2)),
                                                 water=bool(p.get("water", False)))
            return {"status": "ok", "scene": r}
        if action == "entity":
            eid = self._curious.world.add_entity(
                str(p.get("category", "entity")),
                behavior=str(p.get("behavior", "wander")),
                pos=tuple(float(v) for v in p.get("pos", [2, 1.5, 2])),
                speed=float(p.get("speed", 0.3)),
                goal=str(p.get("goal", "")))
            return {"status": "ok", "entity_id": eid}
        if action == "path":
            self._curious.world.add_path(str(p.get("path_id", "")), p.get("points", []))
            return {"status": "ok", "path_id": str(p.get("path_id", ""))}
        if action == "explore":
            r = self._curious.explore(ticks=int(p.get("n", 30)),
                                      budget=int(p.get("budget", 2)),
                                      policy=str(p.get("policy", "curiosity")))
            return {"status": "ok", "explore": r}
        if action == "step":
            r = self._curious.explore_tick(budget=int(p.get("budget", 2)),
                                           policy=str(p.get("policy", "curiosity")))
            return {"status": "ok", "step": r}
        if action == "probe":
            r = self._curious.probe(ticks=int(p.get("n", 15)))
            return {"status": "ok", "probe": r}
        if action == "compare":
            r = self._curious.compare_policies(
                budget=int(p.get("budget", 2)),
                explore_ticks=int(p.get("explore_ticks", 40)),
                probe_ticks=int(p.get("probe_ticks", 15)))
            return {"status": "ok", "compare": r}
        if action == "curiosity":
            return {"status": "ok", "curiosity": self._curious.curiosity_summary()}
        if action == "uncertainty":
            return {"status": "ok", "curve": self._curious.uncertainty_curve,
                    "current": self._curious.uncertainty()}
        if action == "model":
            return {"status": "ok", "model": self._curious.model_params()}
        if action == "history":
            return {"status": "ok",
                    "history": self._curious.history_view(limit=int(p.get("limit", 10)))}
        if action == "state":
            return {"status": "ok", "explorer": self._curious.state()}
        return {"status": "error", "error": f"未知动作 {action}（可用: init/create/entity/path/explore/step/probe/compare/curiosity/uncertainty/model/history/state）"}

    def seven_layer_loop(self, action: str, params: dict = None) -> dict:
        """七层闭环（里程碑3.4 · 阶段3收官）：感知→记忆→理解→预测→验证→物理→决策
        完整自主循环——
        - init: 初始化（size/seed/window/budget/policy）
        - create: 物理世界创建场景
        - entity: 添加实体
        - path: 定义巡逻路径
        - run: 持续运行 n tick（每 tick 七层闭环）
        - step: 闭环一步（返回七层留痕：L1感知/L2记忆/L3认知/L4预测/L5验证/L6物理/L7决策）
        - report: 闭环报告（七层统计 + 自增强曲线：early vs late 命中率）
        - audit: 审计轨迹（最近 n tick 七层留痕）
        - verify: 验证状态（L5 命中率）
        - decision: 决策状态（L7 好奇观测分布）
        - memory: 时空记忆（L2）
        - graph: 认知图（L3）
        - state: 闭环状态"""
        p = params or {}
        try:
            from ..world.seven_layer_loop import SevenLayerLoop
        except ImportError:
            try:
                from ..world.seven_layer_loop import SevenLayerLoop
            except Exception as e:
                return {"status": "sll_not_ready", "error": str(e)}
        if not hasattr(self, '_sll'):
            self._sll = SevenLayerLoop(
                size=int(p.get('size', 24)),
                ground_level=int(p.get('ground_level', 1)),
                seed=int(p.get('seed', 42)),
                window=int(p.get('window', 6)),
                budget=int(p.get('budget', 2)),
                policy=str(p.get('policy', 'curiosity')))
        if action == "create":
            r = self._sll.create_scene(trees=int(p.get("trees", 2)),
                                       water=bool(p.get("water", False)))
            return {"status": "ok", "scene": r}
        if action == "entity":
            eid = self._sll.add_entity(
                str(p.get("category", "entity")),
                behavior=str(p.get("behavior", "wander")),
                pos=tuple(float(v) for v in p.get("pos", [2, 1.5, 2])),
                speed=float(p.get("speed", 0.3)),
                goal=str(p.get("goal", "")))
            return {"status": "ok", "entity_id": eid}
        if action == "path":
            self._sll.add_path(str(p.get("path_id", "")), p.get("points", []))
            return {"status": "ok", "path_id": str(p.get("path_id", ""))}
        if action == "run":
            r = self._sll.run(n=int(p.get("n", 30)))
            return {"status": "ok", "run": r}
        if action == "step":
            r = self._sll.step()
            return {"status": "ok", "step": r}
        if action == "report":
            return {"status": "ok", "report": self._sll.report()}
        if action == "audit":
            return {"status": "ok",
                    "audit": self._sll.audit_view(limit=int(p.get("limit", 10)))}
        if action == "verify":
            return {"status": "ok", "verify": self._sll.verify_state()}
        if action == "decision":
            return {"status": "ok", "decision": self._sll.decision_state()}
        if action == "memory":
            return {"status": "ok", "memory": self._sll.memory_state()}
        if action == "graph":
            return {"status": "ok", "graph": self._sll.graph_state()}
        if action == "state":
            return {"status": "ok", "loop": self._sll.state()}
        return {"status": "error", "error": f"未知动作 {action}（可用: init/create/entity/path/run/step/report/audit/verify/decision/memory/graph/state）"}

    def world_generator(self, action: str, params: dict = None) -> dict:
        """文字生图/文字生视频（里程碑4.3 · 世界模型生成器）：
        有世界模型的 AI 生成画面与时序——文字→场景解析→世界实例化→渲染。
        - scene: 场景解析（text → 地形 + 实体规格，白箱可审计）
        - image: 文字生图（text → PNG base64，3D 渲染，确定性）
        - video: 文字生视频（text → GIF 多帧=世界演化的一串帧 + L4 预测叠加）
        - save: 保存到文件（path + image/video）"""
        p = params or {}
        try:
            from game_web.generate import WorldGenerator
        except ImportError:
            try:
                from .game_web.generate import WorldGenerator
            except Exception as e:
                return {"status": "gen_not_ready", "error": str(e)}
        if not hasattr(self, '_wgen'):
            self._wgen = WorldGenerator(size=int(p.get('size', 24)),
                                        seed=int(p.get('seed', 42)))
        if action == "scene":
            r = self._wgen.scene_from_text(str(p.get("text", "")))
            return {"status": "ok", "scene": r}
        if action == "image":
            r = self._wgen.generate_image(
                str(p.get("text", "")),
                size=int(p.get("size", 480)),
                run_ticks=int(p.get("run_ticks", 0)))
            import base64
            return {"status": "ok", "image_b64": base64.b64encode(r["image"]).decode("ascii"),
                    "summary": r["summary"], "bytes": len(r["image"])}
        if action == "video":
            r = self._wgen.generate_video(
                str(p.get("text", "")),
                ticks=int(p.get("ticks", 16)),
                fps=int(p.get("fps", 5)),
                size=int(p.get("size", 360)))
            import base64
            return {"status": "ok", "gif_b64": base64.b64encode(r["gif"]).decode("ascii"),
                    "summary": r["summary"], "frames": r["frames"],
                    "bytes": len(r["gif"]), "final_tick": r["final_tick"]}
        if action == "save":
            text = str(p.get("text", ""))
            path = str(p.get("path", "world_gen"))
            if str(p.get("kind", "image")) == "video":
                r = self._wgen.save_video(text, path + ".gif",
                                          ticks=int(p.get("ticks", 16)),
                                          fps=int(p.get("fps", 5)),
                                          size=int(p.get("size", 360)))
                return {"status": "ok", "path": r["path"], "summary": r["summary"],
                        "frames": r["frames"]}
            r = self._wgen.save_image(text, path + ".png",
                                      size=int(p.get("size", 480)))
            return {"status": "ok", "path": r["path"], "summary": r["summary"]}
        return {"status": "error", "error": f"未知动作 {action}（可用: scene/image/video/save）"}

    def world_semantics(self, action: str, params: dict = None) -> dict:
        """图像语义（环境自适应：AEIS 身体库有实现则真实执行，否则 BLINDSPOT）。

        细分能力（analyze/decompose/reconstruct/generate_roundtrip，依赖
        完整态身体件）已迁移至 AEIS 身体库。
        本体保留环境自适应接口：所在环境有 game_web 实现则真实执行
        （AEIS 私有库），没有则诚实声明 BLINDSPOT（公开仓库形态）。
        """
        try:
            try:
                from game_web.semantics import analyze_image
            except ImportError:
                from .game_web.semantics import analyze_image
        except ImportError:
            return {"status": "blindspot",
                    "reason": "细分语义能力已迁移至 AEIS 身体库（本环境无实现）",
                    "available": []}
        p = params or {}
        if action == "analyze":
            import base64
            png = base64.b64decode(str(p.get("image_b64", "")))
            g = analyze_image(png, levels=int(p.get("levels", 2)),
                              size=int(p.get("size", 240)))
            return {"status": "ok", "graph": g}
        if action == "decompose":
            from game_web.semantics import part_decompose
            import base64
            png = base64.b64decode(str(p.get("image_b64", "")))
            r = part_decompose(png, size=int(p.get("size", 300)))
            return {"status": "ok", "decomposition": r}
        if action == "generate_roundtrip":
            try:
                from game_web.generate import WorldGenerator
            except ImportError:
                from .game_web.generate import WorldGenerator
            gen = WorldGenerator(size=int(p.get('size', 24)),
                                 seed=int(p.get("seed", 42)))
            r = gen.generate_image(str(p.get("text", "森林里有狼追兔子")),
                                   size=int(p.get("img_size", 420)),
                                   run_ticks=int(p.get("run_ticks", 6)))
            g = analyze_image(r["image"], levels=int(p.get("levels", 2)),
                              size=int(p.get("ana_size", 320)))
            return {"status": "ok", "source_summary": r["summary"],
                    "extracted_graph": g}
        return {"status": "error", "error": f"未知动作 {action}（可用: analyze/decompose/generate_roundtrip）"}

    def vprim_query(self, action: str, params: dict = None) -> dict:
        """VPRIM-REV1 视觉原语查询（确定性·零 LLM）：
        - spatial: 两个 bbox 的空间关系（params: a=[x1,y1,x2,y2], b=[...]）
        - count: 最近视觉原语记忆计数（params: category 可选）
        - anchors: 最近视觉原语锚点列表（params: limit）"""
        p = params or {}
        try:
            from ..world.vprim import (  # noqa: F401  sys.modules 别名（__init__ 注册）
                VPrim, spatial_relation, count_vprims, parse_anchor)
        except ImportError:
            try:
                from ..world.vprim import (  # 相对导入兜底（包内调用）
                    VPrim, spatial_relation, count_vprims, parse_anchor)
            except Exception as e:
                return {"status": "vprim_not_ready", "error": str(e)}
        except Exception as e:
            return {"status": "vprim_not_ready", "error": str(e)}
        if action == "spatial":
            a = p.get("a")
            b = p.get("b")
            if not a or not b or len(a) != 4 or len(b) != 4:
                return {"status": "error", "error": "a/b 需为 [x1,y1,x2,y2]"}
            return {"status": "ok", "spatial": spatial_relation(
                tuple(float(v) for v in a), tuple(float(v) for v in b))}
        if action == "count":
            # 从最近 vprim 记忆节点解析锚点计数
            vprims = self._load_vprims_from_memory(limit=int(p.get("limit", 5)))
            result = count_vprims(vprims, category=p.get("category"))
            result["status"] = "ok"
            return result
        if action == "anchors":
            vprims = self._load_vprims_from_memory(limit=int(p.get("limit", 10)))
            return {"status": "ok", "anchors": [v.to_dict() for v in vprims]}
        return {"status": "error", "error": f"未知动作 {action}（可用: spatial/count/anchors）"}

    def _load_vprims_from_memory(self, limit: int = 5) -> list:
        """从记忆检索最近视觉原语（vprim 标签节点 → 解析坐标锚点）。"""
        vprims = []
        try:
            from ..world.vprim import VPrim, parse_anchor  # noqa: F401
            nodes = self.store.get_nodes_by_tag("vprim", limit=max(limit, 5))
            for n in reversed(nodes[-limit:]):
                text = n.content or ""
                for token in text.split("；"):
                    vp = parse_anchor(token)
                    if vp is not None:
                        vprims.append(vp)
        except Exception:
            pass
        return vprims
