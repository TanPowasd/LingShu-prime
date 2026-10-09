# -*- coding: utf-8 -*-
"""compat_world · 旧世界模型外观方法（13 个，#178）在 ng 门面上的形态

记忆引擎本体零依赖（标准库）；世界线 ``lingshu_ng.world`` 依赖 numpy，故**只在调用外观方法时**惰性导入。
  * 有 ng 实现的：``world3d`` / ``vprim_query`` / ``_load_vprims_from_memory`` / ``scene_simulator``
    委托 ``lingshu_ng.world.compat``（World3D、VPrim、SceneSimulator，z-buffer 渲染、截断步长等修复随之生效）。
  * 模拟 / 世界模型 6 个（voxel_world / spacetime_consistency / world_model / world_learner /
    curiosity_explorer / seven_layer_loop）在 :mod:`lingshu_ng.compat_world_sim`；
  * ng 世界线尚无对应模块的 3 个（wm_simloop / world_generator / world_semantics）保持桩
    （compat_stubs.WORLD_MISSING，NotImplementedError），不伪造成功、不回落旧 ``lingshu.world``。
  * ng 世界线依赖 numpy/PIL；不可导入时返回旧版同名的 ``*_not_ready`` 状态字典。
不变量：这里的方法不写库；参数中的数值经 isfinite 校验，非法时返回 ``status=error``。
"""
from __future__ import annotations

import io
import math
import os
from typing import Any, Dict, List, Optional

__all__ = ["WorldFacade"]

def _world() -> Any:
    """惰性导入 ng 世界线适配层（numpy）；不可用时抛 ImportError。"""
    from .world import compat as wc
    return wc


def _num(p: Dict, key: str, default: float) -> float:
    v = float(p.get(key, default))
    if not math.isfinite(v):
        raise ValueError(f"参数 {key} 必须是有限值")
    return v


def _bbox(raw: Any) -> Optional[tuple]:
    if not raw or len(raw) != 4:
        return None
    b = tuple(float(v) for v in raw)
    return b if all(math.isfinite(v) for v in b) else None


def _vec3(raw: Any, default: tuple) -> tuple:
    v = tuple(float(x) for x in (raw if raw is not None else default))
    if len(v) != 3 or not all(math.isfinite(x) for x in v):
        raise ValueError("pos 必须是 3 个有限数值")
    return v


#: 上游 #277：render 输出只收图像扩展名
RENDER_EXTS = (".png", ".bmp", ".jpg", ".jpeg")


def _render_target(path: str) -> str:
    """上游 #277：render 的 path 限定在渲染根内（环境变量 LINGSHU_RENDER_ROOT，缺省 cwd）——相对路径按根拼接，
    realpath + commonpath 判包含（挡 ``../``、根外绝对路径、符号链接逃逸），扩展名白名单；越界抛 ValueError
    （world3d 门面转为 status=error，不写盘）。缺省根与变量名与 integrated-v3 bcb954f 同口径（needs-owner-decision）。"""
    root = os.path.realpath(os.environ.get("LINGSHU_RENDER_ROOT") or os.getcwd())
    full = os.path.realpath(os.path.join(root, path))
    ext = os.path.splitext(full)[1].lower()
    if ext not in RENDER_EXTS:
        raise ValueError(f"render 输出扩展名 {ext!r} 不在白名单 {RENDER_EXTS}")
    try:
        inside = os.path.commonpath([root, full]) == root
    except ValueError:                                  # 不同盘符等
        inside = False
    if not inside:
        raise ValueError("render 输出路径越出渲染根（LINGSHU_RENDER_ROOT，缺省 cwd）")
    return full


class WorldFacade:
    """混入 SpacetimeMemoryEngine 门面。依赖宿主的 ``self.store.get_nodes_by_tag``。"""

    # ------------------------------------------------------------ world3d
    def world3d(self, action: str, params: Optional[dict] = None) -> dict:
        """3D 语义时空重建（build/render/graph/verify/verify_conflict/status/add/add_view）。"""
        p = params or {}
        try:
            wc = _world()
        except ImportError as exc:
            return {"status": "world3d_not_ready", "error": str(exc)}
        if getattr(self, "_world3d", None) is None:
            self._world3d = wc.World3D()
        handler = {"build": self._w3_build, "render": self._w3_render, "graph": self._w3_graph,
                   "verify": self._w3_verify, "verify_conflict": self._w3_conflict,
                   "status": lambda wc_, p_: {"status": "ok", **self._world3d.to_dict()},
                   "add": self._w3_add, "add_view": self._w3_add_view}.get(action)
        if handler is None:
            return {"status": "error", "error": f"未知动作 {action}（可用: build/render/status/add/add_view/"
                                                f"graph/verify/verify_conflict）"}
        try:
            return handler(wc, p)
        except ValueError as exc:
            return {"status": "error", "error": str(exc)}

    def _w3_build(self, wc: Any, p: Dict) -> dict:
        """#211：多视角三角化只用节点自带的真实相机位姿（state_attributes["camera_pose"]）；
        无位姿时不编造「环绕」视角，回退单视角并给 reason="no_camera_pose"。
        objects = 世界物体数（不是调用次数），observations = 观测条数。"""
        world = wc.World3D()
        sw, sh = int(_num(p, "screen_w", 800)), int(_num(p, "screen_h", 600))
        multiview = bool(p.get("multiview", False))
        obs: List[Any] = []
        for n in self.store.get_nodes_by_tag("vprim", limit=int(_num(p, "limit", 20))):
            pose = (getattr(n, "state_attributes", None) or {}).get("camera_pose")
            cam = None
            if isinstance(pose, dict):
                try:
                    cam = wc.Camera3D(**{k: float(pose[k]) for k in
                                         ("fov_deg", "cx", "cy", "cz", "yaw", "pitch") if k in pose})
                except (TypeError, ValueError):
                    cam = None
            for token in (n.content or "").split("；"):
                vp = wc.parse_anchor(token)
                if vp is not None:
                    obs.append((vp, cam))
        n_posed = sum(1 for _vp, c in obs if c is not None)
        use_mv = multiview and n_posed > 0
        for vp, cam in obs:
            if use_mv and cam is not None:
                world.add_view(vp.category, vp.bbox, sw, sh, camera=cam, confidence=vp.confidence)
            else:
                world.add_vprim(vp, sw, sh)
        self._world3d = world
        out = {"status": "ok", "objects": len(world.objects), "observations": len(obs),
               "mode": "multiview" if use_mv else "single_view",
               "scene": world.scene_text(), "detail": world.to_dict()}
        if multiview and n_posed == 0:
            out["reason"] = "no_camera_pose"
        return out

    @staticmethod
    def _camera(wc: Any, cp: Dict) -> Any:
        return wc.Camera3D(yaw=_num(cp, "yaw", 0), pitch=_num(cp, "pitch", 0), cx=_num(cp, "cx", 0),
                           cy=_num(cp, "cy", 1.2))

    def _w3_render(self, wc: Any, p: Dict) -> dict:
        sw, sh = int(_num(p, "screen_w", 800)), int(_num(p, "screen_h", 600))
        img = self._world3d.render(sw, sh, camera=self._camera(wc, p))
        path = str(p.get("path", ""))
        if path:
            full = _render_target(path)
            img.save(full)
            return {"status": "ok", "path": full, "scene": self._world3d.scene_text()}
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return {"status": "ok", "in_memory": True, "bytes": len(buf.getvalue()),
                "scene": self._world3d.scene_text()}

    def _w3_graph(self, wc: Any, p: Dict) -> dict:
        return {"status": "ok", "graph": self._world3d.build_anchor_graph(infer=bool(p.get("infer", True)))}

    def _w3_verify(self, wc: Any, p: Dict) -> dict:
        aid = str(p.get("anchor_id", ""))
        if not aid:
            return {"status": "error", "error": "anchor_id 必填"}
        try:
            r = self._world3d.verify_anchor(aid, str(p.get("channel", "visual")), _num(p, "evidence", 0.5),
                                            strong=p.get("strong"))
        except KeyError as exc:                        # 上游 #262：不存在的锚点 id 不建档、不判 ACCEPT
            return {"status": "error", "error": str(exc)}
        return {"status": "ok", "verification": r}

    def _w3_conflict(self, wc: Any, p: Dict) -> dict:
        vals = [str(p.get(k, "")) for k in ("anchor_id", "channel", "expected", "actual")]
        if not all(vals):
            return {"status": "error", "error": "anchor_id/channel/expected/actual 必填"}
        try:
            return {"status": "ok", "verification": self._world3d.verify_conflict(*vals)}
        except KeyError as exc:                        # 上游 #262
            return {"status": "error", "error": str(exc)}

    def _w3_add(self, wc: Any, p: Dict) -> dict:
        category, bbox = str(p.get("category", "")), _bbox(p.get("bbox"))
        if not category or bbox is None:
            return {"status": "error", "error": "category 与 bbox=[x1,y1,x2,y2] 必填（有限数值）"}
        vp = wc.VPrim(category, bbox, _num(p, "confidence", 0.5), source="manual")
        self._world3d.add_vprim(vp, int(_num(p, "screen_w", 800)), int(_num(p, "screen_h", 600)))
        return {"status": "ok", "scene": self._world3d.scene_text()}

    def _w3_add_view(self, wc: Any, p: Dict) -> dict:
        category, bbox = str(p.get("category", "")), _bbox(p.get("bbox"))
        if not category or bbox is None:
            return {"status": "error", "error": "category 与 bbox=[x1,y1,x2,y2] 必填（有限数值）"}
        cam = self._camera(wc, p["camera"]) if p.get("camera") else None
        res = self._world3d.add_view(category, list(bbox), int(_num(p, "screen_w", 800)),
                                     int(_num(p, "screen_h", 600)), camera=cam,
                                     confidence=_num(p, "confidence", 0.5))
        res["scene"] = self._world3d.scene_text()
        return {"status": "ok", **res}

    # ------------------------------------------------------------ vprim
    def _vprims_in_memory(self, wc: Any, limit: int, legacy_load: bool = True) -> List[Any]:
        """``legacy_load``：旧 _load_vprims_from_memory 口径（取 max(limit,5) 条、末 limit 条倒序）；
        否则旧 world3d build 口径（取 limit 条、原序）。"""
        if legacy_load:
            nodes = self.store.get_nodes_by_tag("vprim", limit=max(limit, 5))
            picked = list(reversed(nodes[-limit:]))
        else:
            picked = self.store.get_nodes_by_tag("vprim", limit=limit)
        out = []
        for n in picked:
            for token in (n.content or "").split("；"):
                vp = wc.parse_anchor(token)
                if vp is not None:
                    out.append(vp)
        return out

    def _load_vprims_from_memory(self, limit: int = 5) -> list:
        """从记忆读最近视觉原语（vprim 标签节点 → 坐标锚点）；世界线不可用时为空列表。"""
        try:
            wc = _world()
        except ImportError:
            return []
        return self._vprims_in_memory(wc, int(limit))

    def vprim_query(self, action: str, params: Optional[dict] = None) -> dict:
        """视觉原语查询：spatial（两框空间关系）/ count（记忆中原语计数）/ anchors。"""
        p = params or {}
        try:
            wc = _world()
        except ImportError as exc:
            return {"status": "vprim_not_ready", "error": str(exc)}
        if action == "spatial":
            a, b = _bbox(p.get("a")), _bbox(p.get("b"))
            if a is None or b is None:
                return {"status": "error", "error": "a/b 需为 [x1,y1,x2,y2]（有限数值）"}
            return {"status": "ok", "spatial": wc.spatial_relation(a, b)}
        if action == "count":
            result = wc.count_vprims(self._load_vprims_from_memory(int(p.get("limit", 5))),
                                     category=p.get("category"))
            result["status"] = "ok"
            return result
        if action == "anchors":
            return {"status": "ok",
                    "anchors": [v.to_dict() for v in self._load_vprims_from_memory(int(p.get("limit", 10)))]}
        return {"status": "error", "error": f"未知动作 {action}（可用: spatial/count/anchors）"}

    # ------------------------------------------------------------ scene_simulator
    def scene_simulator(self, action: str, params: Optional[dict] = None) -> dict:
        """场景模拟器（create/entity/path/step/state/log），委托 ng SceneSimulator。"""
        p = params or {}
        try:
            wc = _world()
        except ImportError as exc:
            return {"status": "scene_not_ready", "error": str(exc)}
        if getattr(self, "_scene", None) is None:
            self._scene = wc.SceneSimulator(size=int(p.get("size", 24)), ground_level=int(p.get("ground_level", 1)))
        sc = self._scene
        try:
            if action == "create":
                return {"status": "ok", "scene": sc.create_scene(trees=int(p.get("trees", 4)),
                                                                 water=bool(p.get("water", True)))}
            if action == "entity":
                pos = _vec3(p.get("pos"), (2, 1.5, 2))
                return {"status": "ok", "entity_id": sc.add_entity(
                    str(p.get("category", "entity")), behavior=str(p.get("behavior", "wander")), pos=pos,
                    speed=_num(p, "speed", 0.3), goal=str(p.get("goal", "")))}
            if action == "path":
                sc.add_path(str(p.get("path_id", "")), p.get("points", []))
                return {"status": "ok", "path_id": str(p.get("path_id", ""))}
            if action == "step":
                return {"status": "ok", "step": sc.step(n=int(p.get("n", 1)))}
        except ValueError as exc:
            return {"status": "error", "error": str(exc)}
        if action == "state":
            return {"status": "ok", "scene": sc.scene_state()}
        if action == "log":
            return {"status": "ok", "log": sc.behavior_log(limit=int(p.get("limit", 30)))}
        return {"status": "error", "error": f"未知动作 {action}（可用: create/entity/path/step/state/log）"}
