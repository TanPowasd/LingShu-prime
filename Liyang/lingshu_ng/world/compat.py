# -*- coding: utf-8 -*-
"""compat · 旧 ``lingshu.world`` 主要公开 API 的同名适配（底层全部走 ng）。

覆盖（以旧 tests/ 中 world 相关测试实际 import 的为准）：
- ``lingshu.world.world3d``   : VisualSpec / DEFAULT_VISUAL_SPECS / default_spec /
  Camera3D / Object3D / World3D
- ``lingshu.world.vprim``     : VPrim / spatial_relation / count_vprims / parse_anchor /
  bbox_from_xywh / vprims_to_scene_text
- ``lingshu.world.shapes``    : SHAPE_LIBRARY / get_shape / register_shape / has_shape
- ``lingshu.world.skeleton3d``: Joint / Skeleton3D / human_skeleton /
  fatfish_bone_skeleton / cat_skeleton
- ``lingshu.world.scene_simulator``: SceneEntity / SceneSimulator

有意的行为差异（旧行为是缺陷）：
- 渲染为 z-buffer（无画家排序）；无描边线；球/圆盘为椭球网格而非 2D 圆。
- add_vprim 不做天空物体「地平线钳制」（#221）。
- Skeleton3D.world_pos 父链按 A_parent·R_child 累积（PR #72）。
- SceneSimulator（实现在 scene_sim.py）接受 seed（PR #12）；seek/follow 步长按剩余距离截断
  （world-n5）；体素地面为 ng VoxelWorld。

多视角融合（multiview）、语义锚点图（anchor_graph）、多感知机验证（anchor_verify）为 ng 原生；
scene_model 由旧源码惰性派生，仅 apply_relations 走 ng 求解器（scene_relations）。

``install_legacy_aliases()`` 把上述模块名注册进 ``sys.modules``，供旧测试/旧调用方
在不改源码的前提下跑在 ng 之上。
"""
from __future__ import annotations

import functools
import math
import re
import sys
import time
import uuid
import types
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import camera as ngcam
from .catalog import (DEFAULT_VISUAL_SPECS, SHAPE_LIBRARY, Part, VisualSpec, default_spec,
                      get_shape, has_shape, register_shape)
from .anchor_graph import (RELATION_TYPES, RelationEdge, SemanticAnchor,  # noqa: F401
                           SemanticAnchorGraph, register_relation_type)
from .anchor_verify import (CONF_THRESHOLD, CONFLICT_THRESHOLD, KL_THRESHOLD,  # noqa: F401
                            STABLE_ROUNDS, STRONG_CHANNELS, WEAK_CHANNELS, AnchorVerification)
from .geometry import Mesh, boxes_mesh, merge_meshes, primitive_mesh
from .multiview import MultiViewFusion, ViewObs
from .raster import Frame, fill_frame_rgb, new_frame, rasterize
from .scene import bbox_overlap_ratio, bbox_relation
from .skeleton import Skeleton, euler_matrix, forward_kinematics

PILImage = "PIL.Image.Image"   # PIL 惰性导入，仅作标注
Vec3 = Tuple[float, float, float]
BBox = Tuple[float, float, float, float]


# ===========================================================================
# world3d
# ===========================================================================

@dataclass
class Camera3D:
    """旧参数化（光心 + yaw/pitch）的薄壳；所有数学委托 :mod:`camera`。"""
    fov_deg: float = 60.0
    cx: float = 0.0
    cy: float = 1.2
    cz: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0

    @classmethod
    def look_at(cls, eye: Vec3, target: Vec3, fov_deg: float = 60.0) -> "Camera3D":
        c = ngcam.Camera.look_at(eye, target, fov_deg=fov_deg)
        d = np.asarray(target, float) - np.asarray(eye, float)
        return cls(fov_deg=fov_deg, cx=float(eye[0]), cy=float(eye[1]), cz=float(eye[2]),
                   yaw=math.atan2(-d[0], d[2]), pitch=math.atan2(d[1], math.hypot(d[0], d[2])))

    def to_ng(self, screen_w: int = 800, screen_h: int = 600) -> ngcam.Camera:
        return _ng_camera(float(self.cx), float(self.cy), float(self.cz), float(self.yaw),
                          float(self.pitch), float(self.fov_deg), int(screen_w), int(screen_h))

    def focal(self, screen_w: int) -> float:
        return self.to_ng(screen_w).focal

    def to_camera(self, p3: Vec3) -> Vec3:
        return tuple(float(v) for v in ngcam.world_to_camera(self.to_ng(), p3))

    def view_depth(self, p3: Vec3) -> float:
        return float(ngcam.depth(self.to_ng(), p3))

    def project(self, p3: Vec3, screen_w: int, screen_h: int) -> Optional[Tuple[float, float]]:
        return ngcam.project_point(self.to_ng(screen_w, screen_h), p3)

    def camera_to_world(self, pc: Vec3) -> Vec3:
        return tuple(float(v) for v in ngcam.camera_to_world(self.to_ng(), pc))


@functools.lru_cache(maxsize=256)
def _ng_camera(cx: float, cy: float, cz: float, yaw: float, pitch: float, fov: float,
               w: int, h: int) -> ngcam.Camera:
    """旧参数 → 不可变 ng 相机（按值缓存：构造含旋转正交校验，渲染热路径上每帧都调）。"""
    return ngcam.Camera.from_yaw_pitch((cx, cy, cz), yaw, pitch, fov_deg=fov, width=w, height=h)


@dataclass
class Object3D:
    category: str
    center: Vec3
    size: Vec3
    color: Tuple[int, int, int]
    shape: str = "box"
    confidence: float = 0.5
    ts: float = field(default_factory=time.time)
    source: str = "world3d"

    def to_dict(self) -> Dict:
        return asdict(self)

    def corners(self) -> List[Vec3]:
        x, y, z = self.center
        hw, hh, hd = (s / 2 for s in self.size)
        return [(x - hw, y - hh, z - hd), (x + hw, y - hh, z - hd),
                (x + hw, y + hh, z - hd), (x - hw, y + hh, z - hd),
                (x - hw, y - hh, z + hd), (x + hw, y - hh, z + hd),
                (x + hw, y + hh, z + hd), (x - hw, y + hh, z + hd)]

    def depth(self, camera: Optional[Camera3D] = None) -> float:
        """相机深度；无相机时用默认相机（原点朝 +z 时等于世界 z）。"""
        return (camera or Camera3D()).view_depth(self.center)


def _object_items(obj: Object3D, obj_id: int) -> List[Tuple[str, np.ndarray, Vec3, Tuple, int]]:
    """物体 → 图元清单 (kind, center, size, color, id)：有部件形状则逐部件，否则单一图元。"""
    parts = get_shape(obj.category)
    if not parts:
        return [(obj.shape, np.asarray(obj.center, float), obj.size, obj.color, obj_id)]
    c = np.asarray(obj.center, float)
    return [(p.get("kind", "box"), c + np.asarray(p["pos"], float), p["size"],
             tuple(p.get("color", obj.color)), obj_id) for p in parts]


def _items_mesh(items: List[Tuple]) -> Mesh:
    """图元清单 → 网格；连续的盒类图元批量构造（面序与逐个构造后合并相同）。"""
    out: List[Mesh] = []
    run: List[Tuple] = []
    for it in items + [("<end>", None, None, None, None)]:
        if it[0] not in ("sphere", "disk", "pyramid", "<end>"):
            run.append(it)
            continue
        if run:
            out.append(boxes_mesh(np.array([r[1] for r in run], float), np.array([r[2] for r in run], float),
                                  np.array([r[3] for r in run]), np.array([r[4] for r in run])))
            run = []
        if it[0] != "<end>":
            out.append(primitive_mesh(*it))
    return out[0] if len(out) == 1 else merge_meshes(out)


def object_mesh(obj: Object3D, obj_id: int) -> Mesh:
    """物体 → 网格：有部件形状则部件组合，否则单一图元。"""
    return _items_mesh(_object_items(obj, obj_id))


def scene_mesh(objects: List[Object3D]) -> Mesh:
    """全部物体 → 一个网格（物体 i 的 id = i），所有盒类部件一次性批量构造。"""
    return _items_mesh([it for i, o in enumerate(objects) for it in _object_items(o, i)])


class World3D:
    """3D 语义时空图：物体集合 + 相机 + 反投影 + z-buffer 渲染。"""

    def __init__(self, camera: Optional[Camera3D] = None):
        self.camera = camera or Camera3D()
        self.objects: List[Object3D] = []
        self.visual: Dict[str, VisualSpec] = dict(DEFAULT_VISUAL_SPECS)

    def add_vprim(self, vprim, screen_w: int, screen_h: int,
                  horizon_ratio: float = 0.45) -> Optional[Object3D]:
        """2D 框 → 3D 物体（经 camera.bbox_to_world，计入完整位姿）。"""
        spec = self.visual.get(vprim.category, default_spec(vprim.category))
        x1, y1, x2, y2 = vprim.bbox
        x2 = max(x2, x1 + 1.0)          # 旧语义：像素宽至少 1
        cam = self.camera.to_ng(screen_w, screen_h)
        X, Y, Z = ngcam.bbox_to_world(cam, (x1, y1, x2, y2), spec.size[0])
        if spec.ground:
            Y = spec.size[1] / 2.0
        obj = Object3D(vprim.category, (round(float(X), 2), round(float(Y), 2), round(float(Z), 2)),
                       spec.size, spec.color, spec.shape, vprim.confidence, source=vprim.source)
        for i, old in enumerate(self.objects):
            if old.category == obj.category and math.hypot(
                    old.center[0] - obj.center[0], old.center[2] - obj.center[2]) < max(old.size[0], old.size[2]):
                self.objects[i] = obj
                return obj
        self.objects.append(obj)
        return obj

    def render_frame(self, screen_w: int = 800, screen_h: int = 600,
                     camera: Optional[Camera3D] = None,
                     background: Tuple[int, int, int] = (20, 24, 40),
                     ground_color: Tuple[int, int, int] = (30, 34, 50),
                     frame: Optional[Frame] = None) -> Frame:
        """z-buffer 渲染。``frame`` 给定（同画幅）时就地复用其缓冲，省去整帧分配。"""
        cam = (camera or self.camera).to_ng(screen_w, screen_h)
        if frame is None or frame.depth.shape != (screen_h, screen_w):
            frame = new_frame(cam, background)
        else:
            frame.reset(background)
        fill_frame_rgb(frame, ground_color, int(screen_h * 0.45))
        return rasterize(scene_mesh(self.objects), cam, frame=frame)

    def render(self, screen_w: int = 800, screen_h: int = 600,
               camera: Optional[Camera3D] = None,
               background: Tuple[int, int, int] = (20, 24, 40),
               ground_color: Tuple[int, int, int] = (30, 34, 50)) -> "PILImage":
        """→ PIL 图。帧缓冲按画幅缓存复用（``Image.fromarray`` 对 RGB 拷贝，返回图不共享缓冲）；
        沙箱里每帧重新分配 ~1.4 MB 缓冲的缺页开销与整帧光栅同量级。"""
        from PIL import Image
        fr = self.render_frame(screen_w, screen_h, camera, background, ground_color,
                               frame=getattr(self, "_scratch", None))
        self._scratch = fr
        if fr.rgbx is not None and fr.rgbx.flags.c_contiguous:     # RGBX → RGB 由 PIL 的 C 解码器拷出
            return Image.frombuffer("RGBX", (screen_w, screen_h), fr.rgbx, "raw", "RGBX", 0, 1).convert("RGB")
        return Image.fromarray(np.ascontiguousarray(fr.color), "RGB")

    def to_dict(self) -> Dict:
        return {"camera": asdict(self.camera), "objects": [o.to_dict() for o in self.objects],
                "count": len(self.objects)}

    def scene_text(self) -> str:
        parts = []
        for o in sorted(self.objects, key=lambda x: -x.depth(self.camera)):
            x, y, z = [round(v, 1) for v in o.center]
            parts.append(f"{o.category}@3D({x},{y},{z})")
        return "；".join(parts) if parts else "（空场景）"

    # ---- 多视角融合 / 语义锚点图 / 多感知机验证（ng 原生：multiview / anchor_graph）----

    def add_view(self, category: str, bbox2d, screen_w: int, screen_h: int,
                 camera: Optional[Camera3D] = None, confidence: float = 0.5) -> Dict:
        """多视角观测 → 轨迹三角化；同一轨迹再次收敛时**就地更新**其物体（旧版每个视角追加
        一个重复物体），``object_added`` 只在轨迹首次三角化时为真。"""
        cam = camera or self.camera
        obs = ViewObs(cam, ((bbox2d[0] + bbox2d[2]) / 2, (bbox2d[1] + bbox2d[3]) / 2),
                      screen_w, screen_h)
        if getattr(self, "_mv", None) is None:
            self._mv, self._mv_objects = MultiViewFusion(), {}
        spec = self.visual.get(category, default_spec(category))
        res = self._mv.add_observation(category, obs, size=spec.size, color=spec.color,
                                       shape=spec.shape, confidence=confidence)
        obj = self._mv_objects.get(res["track_id"])
        res["object_added"] = res["object_updated"] = False
        if res["center_3d"] is not None and obj is None:
            obj = Object3D(category, tuple(res["center_3d"]), spec.size, spec.color, spec.shape,
                           confidence, source="multiview")
            self.objects.append(obj)
            self._mv_objects[res["track_id"]] = obj
            res["object_added"] = True
        elif res["center_3d"] is not None:
            obj.center, obj.confidence = tuple(res["center_3d"]), confidence
            res["object_updated"] = True
        return res

    def build_anchor_graph(self, infer: bool = True) -> Dict:
        """重建锚点图。上游 #262：锚点 id 跟物体身份走（首次建图时给物体挂一个稳定 id，之后重建沿用），
        多通道验证记录（证据 / 冲突 / 轮次）跨重建保留——重建不得清空证据、把冲突「洗白」。"""
        g = SemanticAnchorGraph()
        for o in self.objects:
            aid = getattr(o, "_anchor_id", None)
            if not aid:
                aid = "anchor_" + uuid.uuid4().hex[:10]
                object.__setattr__(o, "_anchor_id", aid)   # 非 dataclass 字段：不进 to_dict()/asdict
            g.add_anchor(SemanticAnchor(category=o.category, center=o.center, size=o.size,
                                        confidence=o.confidence, provenance=o.source, id=aid))
        if infer:
            g.infer_relations()
        old = getattr(self, "_anchor_graph", None)
        if old is not None and getattr(old, "_verifier", None) is not None:
            g._verifier = old._verifier
            g._verifier.graph = g
        self._anchor_graph = g
        return g.to_dict()

    def has_anchor(self, anchor_id: str) -> bool:
        """上游 #262：verify / verify_conflict 只接受当前锚点图里存在的 id（无图时先建图）。"""
        g = getattr(self, "_anchor_graph", None)
        ids = [getattr(o, "_anchor_id", None) for o in self.objects]
        if g is None or None in ids or set(ids) != set(g.anchors):   # graph 之后 add 的物体：补建（沿用既有 id）
            self.build_anchor_graph()
        return anchor_id in self._anchor_graph.anchors

    def verify_anchor(self, anchor_id: str, channel: str = "visual",
                      evidence: float = 0.5, strong: Optional[bool] = None) -> Dict:
        if not self.has_anchor(anchor_id):
            raise KeyError(f"未知锚点 id：{anchor_id!r}（先 graph 建图，且只能验证图中存在的锚点）")
        return self._anchor_graph.verify(anchor_id, channel, evidence, strong)

    def verify_conflict(self, anchor_id: str, channel: str, expected: str, actual: str) -> Dict:
        if not self.has_anchor(anchor_id):
            raise KeyError(f"未知锚点 id：{anchor_id!r}（先 graph 建图，且只能验证图中存在的锚点）")
        return self._anchor_graph.verify_conflict(anchor_id, channel, expected, actual)


# ===========================================================================
# vprim
# ===========================================================================

@dataclass
class VPrim:
    category: str
    bbox: BBox
    confidence: float = 0.5
    ts: float = field(default_factory=time.time)
    source: str = "detect"

    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def size(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return (x2 - x1, y2 - y1)

    def area(self) -> float:
        w, h = self.size()
        return w * h

    def to_dict(self) -> Dict:
        return asdict(self)

    def anchor_text(self) -> str:
        x1, y1, x2, y2 = [int(v) for v in self.bbox]
        return f"{self.category}@({x1},{y1},{x2},{y2})"

    def describe(self) -> str:
        x1, y1, x2, y2 = [int(v) for v in self.bbox]
        return f"{self.category}@({x1},{y1},{x2},{y2}) {x2 - x1}x{y2 - y1} conf={self.confidence:.2f}"

    def __repr__(self) -> str:
        return f"<VPrim {self.describe()}>"


def spatial_relation(a: BBox, b: BBox) -> Dict:
    """旧返回结构不变；关系与重叠率由 :mod:`scene` 的集中定义给出。"""
    acx, acy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bcx, bcy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return {"relation": bbox_relation(a, b),
            "distance": round(math.hypot(acx - bcx, acy - bcy), 1),
            "dx": round(acx - bcx, 1), "dy": round(acy - bcy, 1),
            "a_center": (round(acx, 1), round(acy, 1)),
            "b_center": (round(bcx, 1), round(bcy, 1)),
            "overlap_ratio": round(bbox_overlap_ratio(a, b), 3)}


def count_vprims(vprims: List[VPrim], category: Optional[str] = None) -> Dict:
    items = vprims if category is None else [v for v in vprims if v.category == category]
    by: Dict[str, int] = {}
    for v in items:
        by[v.category] = by.get(v.category, 0) + 1
    return {"total": len(items), "by_category": by, "filter": category,
            "anchors": [v.anchor_text() for v in items]}


def parse_anchor(text: str) -> Optional[VPrim]:
    m = re.search(r"([\w\-]+)@\((\d+),(\d+),(\d+),(\d+)\)", text)
    if not m:
        return None
    x1, y1, x2, y2 = (int(g) for g in m.groups()[1:])
    return VPrim(category=m.group(1), bbox=(x1, y1, x2, y2), source="anchor")


def bbox_from_xywh(x: float, y: float, w: float, h: float) -> BBox:
    return (x, y, x + w, y + h)


def vprims_to_scene_text(vprims: List[VPrim], scene: str = "") -> str:
    scene_part = f" {scene}" if scene else ""
    return f"[视觉原语{scene_part}] " + "；".join(v.describe() for v in vprims)


# ===========================================================================
# skeleton3d
# ===========================================================================

@dataclass
class Joint:
    name: str
    pos: Vec3
    parent: Optional[str] = None
    rot: Vec3 = (0.0, 0.0, 0.0)
    radius: float = 0.02

    def _rot_matrix(self) -> List[List[float]]:
        return euler_matrix(*self.rot).tolist()

    def apply_rot(self, p: Vec3) -> Vec3:
        return tuple(float(v) for v in euler_matrix(*self.rot) @ np.asarray(p, float))


class Skeleton3D:
    """关节树（dict 视图，兼容旧代码直接改 ``joints[n].rot``）；解算走 ng FK。"""

    def __init__(self, center: Vec3 = (0.0, 0.0, 5.0)):
        self.center = center
        self.joints: Dict[str, Joint] = {}
        self._bone_color = (220, 220, 230)
        self._joint_color = (255, 180, 120)

    def add_joint(self, name: str, pos: Vec3, parent: Optional[str] = None,
                  rot: Vec3 = (0, 0, 0), radius: float = 0.02) -> "Skeleton3D":
        if parent is not None and parent not in self.joints:
            raise ValueError(f"parent joint {parent!r} not found")
        self.joints[name] = Joint(name=name, pos=pos, parent=parent, rot=rot, radius=radius)
        return self

    def to_ng(self) -> Skeleton:
        sk = Skeleton(center=np.asarray(self.center, float))
        for n, j in self.joints.items():
            sk.add(n, j.pos, j.parent, j.rot)
        return sk

    def world_positions(self) -> Dict[str, Vec3]:
        sk = self.to_ng()
        pos, _ = forward_kinematics(sk)
        return {n: tuple(float(v) for v in pos[i]) for i, n in enumerate(sk.names)}

    def world_pos(self, name: str, memo: Optional[Dict[str, Tuple]] = None) -> Vec3:
        if memo is not None and name in memo:
            return memo[name]
        allp = self.world_positions()
        if memo is not None:
            memo.update(allp)
        return allp[name]

    def bones(self) -> List[Tuple[str, str]]:
        return [(j.parent, n) for n, j in self.joints.items() if j.parent is not None]

    def render(self, screen_w: int = 400, screen_h: int = 400,
               camera: Optional[Camera3D] = None,
               background: Tuple[int, int, int] = (24, 28, 46)) -> "PILImage":
        """线条渲染：骨段按相机深度远→近（线条无面，深度序即正确遮挡近似）。"""
        from PIL import Image, ImageDraw
        cam = (camera or Camera3D()).to_ng(screen_w, screen_h)
        img = Image.new("RGB", (screen_w, screen_h), background)
        draw = ImageDraw.Draw(img)
        world = self.world_positions()
        names = list(world)
        pts = np.array([world[n] for n in names]).reshape(-1, 3)
        uv, z = ngcam.project(cam, pts) if len(names) else (np.zeros((0, 2)), np.zeros(0))
        scr = {n: (float(uv[i, 0]), float(uv[i, 1])) for i, n in enumerate(names) if z[i] > cam.near}
        zz = {n: float(z[i]) for i, n in enumerate(names)}
        for p, c in sorted(self.bones(), key=lambda b: -(zz[b[0]] + zz[b[1]]) / 2):
            if p in scr and c in scr:
                draw.line([scr[p], scr[c]], fill=self._bone_color, width=2)
        for n, sp in scr.items():
            r = max(1, int(self.joints[n].radius * cam.focal / max(zz[n], 0.1)))
            draw.ellipse([sp[0] - r, sp[1] - r, sp[0] + r, sp[1] + r], fill=self._joint_color)
        return img

    def _bone_depth(self, world: Dict[str, Tuple], bone: Tuple[str, str],
                    camera: Optional[Camera3D] = None) -> float:
        cam = camera or Camera3D()
        return (cam.view_depth(world[bone[0]]) + cam.view_depth(world[bone[1]])) / 2


# ---- 骨架模板（关节表与旧模块逐项相同）----

def human_skeleton(center: Tuple[float, float, float] = (0, 0, 5),
                   height: float = 1.7) -> Skeleton3D:
    """标准人形骨架（肥鱼/角色通用）。h 缩放各段。"""
    h = height
    s = Skeleton3D(center=center)
    hip_y = h * 0.48
    torso_h = h * 0.22
    leg_h = h * 0.30
    arm_h = h * 0.24
    # 躯干
    s.add_joint("hip", (0, hip_y, 0))
    s.add_joint("torso", (0, torso_h, 0), parent="hip")
    s.add_joint("chest", (0, h * 0.10, 0), parent="torso")
    s.add_joint("neck", (0, h * 0.08, 0), parent="chest")
    s.add_joint("head", (0, h * 0.10, 0), parent="neck")
    # 腿
    s.add_joint("thigh_l", (-h * 0.05, -leg_h, 0), parent="hip")
    s.add_joint("shin_l", (0, -leg_h, 0), parent="thigh_l")
    s.add_joint("foot_l", (0, -h * 0.04, h * 0.04), parent="shin_l")
    s.add_joint("thigh_r", (h * 0.05, -leg_h, 0), parent="hip")
    s.add_joint("shin_r", (0, -leg_h, 0), parent="thigh_r")
    s.add_joint("foot_r", (0, -h * 0.04, h * 0.04), parent="shin_r")
    # 手臂
    s.add_joint("shoulder_l", (-h * 0.06, h * 0.02, 0), parent="chest")
    s.add_joint("elbow_l", (0, -arm_h, 0), parent="shoulder_l")
    s.add_joint("hand_l", (0, -arm_h * 0.8, 0), parent="elbow_l")
    s.add_joint("shoulder_r", (h * 0.06, h * 0.02, 0), parent="chest")
    s.add_joint("elbow_r", (0, -arm_h, 0), parent="shoulder_r")
    s.add_joint("hand_r", (0, -arm_h * 0.8, 0), parent="elbow_r")
    return s

def _fatfish_limbs(s: "Skeleton3D", h: float) -> None:
    """肥鱼骨架的四肢（手臂含 3 指、腿含趾），关节表与旧模块逐项相同。"""
    # ---- 手臂（锁骨→肩→肘→腕→指）----
    arm_h = h * 0.23
    for side, sgn in (("l", -1), ("r", 1)):
        s.add_joint(f"shoulder_{side}", (sgn * h * 0.07, 0, 0), parent="clavicle")
        s.add_joint(f"elbow_{side}", (0, -arm_h, 0), parent=f"shoulder_{side}")
        s.add_joint(f"wrist_{side}", (0, -arm_h * 0.62, 0), parent=f"elbow_{side}")
        s.add_joint(f"hand_{side}", (0, -arm_h * 0.22, 0), parent=f"wrist_{side}")
        # 3 指（thumb 在侧面，index/middle 前伸）
        s.add_joint(f"thumb_{side}", (sgn * h * 0.02, 0, h * 0.015), parent=f"hand_{side}")
        s.add_joint(f"thumb_tip_{side}", (sgn * h * 0.02, -h * 0.015, h * 0.03), parent=f"thumb_{side}")
        s.add_joint(f"index_{side}", (sgn * h * 0.008, 0, h * 0.02), parent=f"hand_{side}")
        s.add_joint(f"index_tip_{side}", (sgn * h * 0.008, -h * 0.02, h * 0.035), parent=f"index_{side}")
        s.add_joint(f"middle_{side}", (0, 0, h * 0.025), parent=f"hand_{side}")
        s.add_joint(f"middle_tip_{side}", (0, -h * 0.022, h * 0.04), parent=f"middle_{side}")
    # ---- 腿（髋→膝→踝→趾）----
    leg_h = h * 0.36                  # 动漫长腿比例（腿占身高 36%）
    for side, sgn in (("l", -1), ("r", 1)):
        s.add_joint(f"thigh_{side}", (sgn * h * 0.05, -leg_h, 0), parent="hip")
        s.add_joint(f"knee_{side}", (0, -leg_h * 0.62, 0), parent=f"thigh_{side}")
        s.add_joint(f"ankle_{side}", (0, -leg_h * 0.38, 0), parent=f"knee_{side}")
        s.add_joint(f"foot_{side}", (0, -h * 0.03, h * 0.05), parent=f"ankle_{side}")
        s.add_joint(f"toe_{side}", (0, -h * 0.01, h * 0.035), parent=f"foot_{side}")


def fatfish_bone_skeleton(center: Tuple[float, float, float] = (0, 0.85, 5),
                          height: float = 1.55) -> Skeleton3D:
    """肥鱼精细骨架（猫娘少女，40+ 关节）。

    细化（对照 human_skeleton 17 关节）：
    - 脊柱分节：腰/胸/锁骨/颈（真实脊柱层次）
    - 手指：每手 3 指关节（thumb/index/middle → tip）
    - 脚趾：每脚 2 趾
    - 猫耳：每耳 2 关节（可立/垂/抖）
    - 尾巴：5 节（摆动细腻）
    """
    h = height
    s = Skeleton3D(center=center)
    hip_y = h * 0.47
    # ---- 脊柱（分节）----
    s.add_joint("hip", (0, hip_y, 0))
    s.add_joint("waist", (0, h * 0.07, 0), parent="hip")
    s.add_joint("torso", (0, h * 0.08, 0), parent="waist")
    s.add_joint("chest", (0, h * 0.07, 0), parent="torso")
    s.add_joint("clavicle", (0, h * 0.04, 0), parent="chest")
    s.add_joint("neck", (0, h * 0.06, 0), parent="clavicle")
    s.add_joint("head", (0, h * 0.09, 0), parent="neck")
    s.add_joint("head_top", (0, h * 0.05, 0), parent="head")   # 头顶（猫耳挂点）
    # ---- 猫耳（每耳 2 关节）----
    # 视觉验收修复（2026-08-29）：base 原悬在 head_top 上方 0.06h，加上头椭圆
    # 半径后耳朵整体飘在头轮廓外（L3 特写呈悬空锥）——base 下移+内收嵌入
    # 头椭圆（rx≈0.052h 内），tip 微外倾成自然猫耳
    s.add_joint("ear_l_base", (-h * 0.04, -h * 0.01, 0), parent="head_top")
    s.add_joint("ear_l_tip", (-h * 0.05, h * 0.04, 0), parent="ear_l_base")
    s.add_joint("ear_r_base", (h * 0.04, -h * 0.01, 0), parent="head_top")
    s.add_joint("ear_r_tip", (h * 0.05, h * 0.04, 0), parent="ear_r_base")
    _fatfish_limbs(s, h)
    # ---- 尾巴（5 节）----
    tb = (-h * 0.14, 0, h * 0.02)          # 尾根（身后）
    s.add_joint("tail0", tb, parent="hip")
    prev = "tail0"
    for i in range(1, 5):
        s.add_joint(f"tail{i}", (0, h * 0.015 * i, h * 0.05), parent=prev)
        prev = f"tail{i}"
    return s


def cat_skeleton(center: Tuple[float, float, float] = (0, 0, 5),
                 body_len: float = 0.6) -> Skeleton3D:
    """四足/猫科骨架（动物通用）。"""
    s = Skeleton3D(center=center)
    b = body_len
    s.add_joint("root", (0, b * 0.35, 0))
    # 脊柱
    s.add_joint("back", (0, b * 0.08, -b * 0.15), parent="root")
    s.add_joint("neck", (0, b * 0.10, -b * 0.15), parent="back")
    s.add_joint("head", (0, b * 0.05, -b * 0.10), parent="neck")
    s.add_joint("tail_root", (0, 0, b * 0.18), parent="root")
    s.add_joint("tail_tip", (0, b * 0.05, b * 0.22), parent="tail_root")
    # 四腿
    leg = b * 0.4
    s.add_joint("fl", (-b * 0.18, -leg, 0), parent="root")
    s.add_joint("fl_paw", (0, -b * 0.12, 0), parent="fl")
    s.add_joint("fr", (b * 0.18, -leg, 0), parent="root")
    s.add_joint("fr_paw", (0, -b * 0.12, 0), parent="fr")
    s.add_joint("bl", (-b * 0.18, -leg, b * 0.10), parent="back")
    s.add_joint("bl_paw", (0, -b * 0.12, 0), parent="bl")
    s.add_joint("br", (b * 0.18, -leg, b * 0.10), parent="back")
    s.add_joint("br_paw", (0, -b * 0.12, 0), parent="br")
    return s



# ===========================================================================
# scene_simulator：实现在 scene_sim.py（确定性分支唯一公式来源，世界与影子共用）
# ===========================================================================

from .scene_sim import SceneEntity, SceneSimulator  # noqa: E402,F401
from .spacetime import SpacetimeConsistency  # noqa: E402,F401
from .world_model import UnifiedWorldModel, WMEdge, WMNode  # noqa: E402,F401
from .prediction import PredictionEngine  # noqa: E402,F401
from .world_learner import LNNode, WorldLearner  # noqa: E402,F401
from .curiosity import CuriosityExplorer  # noqa: E402,F401
from .seven_layer_loop import SevenLayerLoop  # noqa: E402,F401


# ===========================================================================
# 旧模块名注册
# ===========================================================================

_EXPORTS: Dict[str, List[str]] = {
    "world3d": ["VisualSpec", "DEFAULT_VISUAL_SPECS", "default_spec", "Camera3D",
                "Object3D", "World3D"],
    "vprim": ["BBox", "VPrim", "spatial_relation", "count_vprims", "parse_anchor",
              "bbox_from_xywh", "vprims_to_scene_text"],
    "shapes": ["Part", "SHAPE_LIBRARY", "get_shape", "register_shape", "has_shape"],
    "skeleton3d": ["Camera3D", "Joint", "Skeleton3D", "human_skeleton",
                   "fatfish_bone_skeleton", "cat_skeleton"],
    "scene_simulator": ["SceneEntity", "SceneSimulator"],
    "spacetime_consistency": ["SpacetimeConsistency", "SceneSimulator"],
    "world_model": ["UnifiedWorldModel", "WMNode", "WMEdge", "SceneSimulator"],
    "prediction": ["PredictionEngine"],
    "multiview": ["ViewObs", "MultiViewFusion"],
    "semantic_anchor_graph": ["RELATION_TYPES", "register_relation_type", "SemanticAnchor",
                              "RelationEdge", "SemanticAnchorGraph"],
    "anchor_verify": ["STRONG_CHANNELS", "WEAK_CHANNELS", "CONF_THRESHOLD", "KL_THRESHOLD",
                      "STABLE_ROUNDS", "CONFLICT_THRESHOLD", "AnchorVerification"],
    "world_learner": ["WorldLearner", "LNNode", "SceneSimulator", "SpacetimeConsistency"],
    "curiosity_explorer": ["CuriosityExplorer", "WorldLearner", "LNNode"],
    "seven_layer_loop": ["SevenLayerLoop", "SceneSimulator", "CuriosityExplorer"],
}


# 由旧模块派生、只替换缺陷部分的惰性模块（首次取属性时才加载旧源码；旧源码里的相对导入
# 解析到已安装的 ng 别名）。
_DERIVED: Dict[str, str] = {"scene_model": "_derive_scene_model"}


def _load_legacy_source(short: str) -> types.ModuleType:
    """按文件加载旧 ``lingshu/world/<short>.py``（私有模块名，不占用被别名的正式名）。"""
    import importlib
    import importlib.util
    import pathlib
    pkg = importlib.import_module("lingshu.world")
    path = pathlib.Path(pkg.__file__).with_name(short + ".py")
    spec = importlib.util.spec_from_file_location(f"lingshu.world._legacy_{short}", path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "lingshu.world"
    sys.modules[spec.name] = mod          # dataclass 等在执行期按 __module__ 回查 sys.modules
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return mod


def _derive_scene_model(legacy: types.ModuleType) -> Dict[str, object]:
    """scene_model：WorldModel.apply_relations 改走 ng 求解器（left_of/right_of 违反条件修正）。"""
    from .scene_relations import solve_relations

    class WorldModel(legacy.WorldModel):
        __doc__ = legacy.WorldModel.__doc__

        def apply_relations(self) -> None:
            solve_relations(self.entities)

    WorldModel.__module__ = "lingshu.world.scene_model"

    def load_world_from_memory(agent_or_store, tag: str = "spatial") -> WorldModel:
        """上游 #282：重建世界须按写入时间旧→新遍历（同名实体 add_entity 覆盖，最后写入者 = 最新一帧）；
        旧版按 get_nodes_by_tag 的 importance 序且截 200 条，重建停在最旧帧/丢新帧。解析规则与旧版一致，
        返回本模块的 WorldModel（apply_relations 走 ng 求解器）。"""
        store = getattr(agent_or_store, "store", agent_or_store)
        if not hasattr(store, "get_nodes_by_tag"):
            engine = getattr(agent_or_store, "engine", None)
            if engine is not None:
                store = getattr(engine, "store", store)
        try:
            nodes = store.get_nodes_by_tag(tag, limit=None)
        except TypeError:                               # 旧 store 的 limit 只收 int
            nodes = store.get_nodes_by_tag(tag, limit=1_000_000)
        nodes = sorted(nodes, key=lambda n: (getattr(n, "created_at", 0.0) or 0.0,
                                             getattr(n, "temporal_coordinate", 0.0) or 0.0))
        wm = WorldModel()
        for n in nodes:
            sp = n.spatial_coordinates or {}
            if not isinstance(sp, dict) or not sp:
                continue
            pos = (sp.get("x", 0.0), sp.get("y", 0.5), sp.get("z", 5.0))
            cat, name = "object", (n.content.split(" ")[0] if n.content else "?")
            for t in (n.tags or []):
                if t.startswith("cat:"):
                    cat = t[4:]
                if t.startswith("ent:"):
                    name = t[4:]
            sa = n.state_attributes or {}
            state = sa["state"] if isinstance(sa, dict) and sa.get("state") else "neutral"
            wm.add_entity(name, category=cat, pos=pos, state=state)
        wm.build()
        return wm

    load_world_from_memory.__module__ = "lingshu.world.scene_model"
    return {"WorldModel": WorldModel, "load_world_from_memory": load_world_from_memory}


def _derived_module(short: str) -> types.ModuleType:
    mod = types.ModuleType(f"lingshu.world.{short}", f"ng-derived compat for lingshu.world.{short}")
    mod.__ng_compat__ = True
    state: Dict[str, object] = {}

    def __getattr__(name: str) -> object:
        if not state:
            legacy = _load_legacy_source(short)
            state.update({k: v for k, v in vars(legacy).items() if not k.startswith("__")})
            state.update(globals()[_DERIVED[short]](legacy))
            mod.__dict__.update(state)
        if name in state:
            return state[name]
        raise AttributeError(name)

    mod.__getattr__ = __getattr__
    return mod


def legacy_modules() -> Dict[str, types.ModuleType]:
    """{旧短模块名: 由本模块对象组成的 ModuleType}（含惰性派生模块）。"""
    me = sys.modules[__name__]
    out = {}
    for short, names in _EXPORTS.items():
        mod = types.ModuleType(f"lingshu.world.{short}", f"ng compat for lingshu.world.{short}")
        for n in names:
            setattr(mod, n, getattr(me, n))
        mod.__ng_compat__ = True
        out[short] = mod
    for short in _DERIVED:
        out[short] = _derived_module(short)
    return out


def install_legacy_aliases(only: Optional[List[str]] = None) -> List[str]:
    """把 ``lingshu.world.<旧模块>`` 指向 ng 适配；须在旧模块首次 import 之前调用。"""
    import importlib
    pkg = importlib.import_module("lingshu.world")
    done = []
    for short, mod in legacy_modules().items():
        if only is not None and short not in only:
            continue
        sys.modules[f"lingshu.world.{short}"] = mod
        setattr(pkg, short, mod)
        done.append(short)
    return done
