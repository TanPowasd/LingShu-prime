# -*- coding: utf-8 -*-
"""compat_body · 旧 API 中不依赖仓外器官的四个方法（stab-r3：由占位转为真实实现）

上游 ``SpacetimeMemoryEngine`` 里这四个方法在公开仓形态下**不需要**任何器官模块就能真实运行，ng 以前却把它们
做成「未装配」占位。现按上游同样的语义实现：

* ``get_body_capabilities()``：身体能力声明。上游形状逐键保留（modalities / vision / memory / devices /
  devices_available / tools / note）；视觉是否可用取自 ``set_vision_provider`` 注入的提供者（duck-typed
  ``available()`` / ``name``），未注入时 ``provider="lazy"``、``available=False``。ng 没有设备注册表 ⇒ 设备清单为空。
  有意不同：``memory.engine`` 写 ``"lingshu_ng"``（上游写自己的版本号 ``"v1.13"``）；``tools`` 只列 ng 门面真实可调的工具。
* ``sync_body_state()``：把能力摘要写进自我模型的 ``state_description``（经 :meth:`SelfStore.update` 白名单落库，
  会在自我模型 history 里留一条记录——上游是绕过 update 的直接赋值 + 落库）。返回 ``{"status": "ok", ...}``。
* ``export_trajectory(cycle_id=None, output_path=None)`` / ``export_structured_trajectories(limit=10, output_path=None)``：
  读带 ``cycle:<id>`` / ``cycle_record_full`` 标签的节点导出轨迹，排序、截断与上游 #57 修订相同。ng 本身不产生认知闭环
  记录（那是上游仓外器官写的），所以在只用 ng 的库上通常导出空的 ``{"cycles": [], "meta": …}``——这是真实结果，不是占位。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

__all__ = ["BodyMixin", "BODY_REAL"]

_log = logging.getLogger(__name__)

#: 本模块真实实现、因而从 compat_stubs.NOT_READY 移出的方法名
BODY_REAL = ("get_body_capabilities", "sync_body_state", "export_trajectory", "export_structured_trajectories")

_TOOLS = ["search", "recall", "capabilities"]


class BodyMixin:
    """见模块说明。依赖宿主提供 ``store``（compat_store）、``ng``（MemoryEngine）与 ``_vision_provider``。"""

    def get_body_capabilities(self) -> Dict[str, Any]:
        """身体能力声明（上游 v1.13 形状）。"""
        vp = getattr(self, "_vision_provider", None)
        if vp is None:
            ok, name, note = False, "lazy", "未注入视觉提供者（ng 不自动装配；用 set_vision_provider 注入）"
        else:
            try:
                ok = bool(vp.available())
                note = None
            except Exception as e:  # 调用方提供者的 available() 抛什么都不可预知：如实记为不可用
                _log.debug("视觉提供者 available() 失败，记为不可用", exc_info=True)
                ok, note = False, f"{type(e).__name__}: {e}"
            name = getattr(vp, "name", type(vp).__name__)
        return {
            "modalities": {"text": True, "image": ok, "audio": False, "video": False},
            "vision": {"provider": name, "available": ok, "error": note},
            "memory": {"engine": "lingshu_ng", "persistent": True},
            "devices": [],
            "devices_available": [],
            "tools": list(_TOOLS),
            "note": "ng 门面：文本感知 + 记忆；视觉需注入提供者；无设备注册表",
        }

    def sync_body_state(self) -> Dict[str, Any]:
        """身体状态摘要写入自我模型 ``state_description`` 并落库。"""
        body = self.get_body_capabilities()
        mods = [m for m, ok in body["modalities"].items() if ok]
        desc = (f"运行中 · 感知[{','.join(mods)}] · 视觉({body['vision']['provider']}) · "
                f"设备[{','.join(body['devices_available']) or 'none'}] · 记忆({body['memory']['engine']})")
        self.ng.self_store.update({"state_description": desc}, reason="sync_body_state")
        return {"status": "ok", "state_description": desc, "body": body}

    def export_trajectory(self, cycle_id: Optional[str] = None, output_path: Optional[str] = None,
                          _limit: Optional[int] = None) -> Dict[str, Any]:
        """导出认知闭环轨迹（上游 A-5 / #57 语义）。"""
        if cycle_id:
            nodes = self.store.get_nodes_by_tag(f"cycle:{cycle_id}", limit=20)
            full = [n for n in nodes if "cycle_record_full" in (n.tags or [])]
            traj: Optional[Dict[str, Any]] = None
            if full:
                traj = _loads(full[0].content)
            if traj is None:
                traj = {"cycle_id": cycle_id, "nodes": [n.content[:100] for n in nodes]}
        else:
            if _limit is None:
                records = self.store.get_nodes_by_tag("cycle_record_full", limit=10)
            else:
                records = self.store.get_nodes_by_tag("cycle_record_full", limit=None)
                records.sort(key=lambda n: (n.temporal_coordinate or 0.0, n.id), reverse=True)
                if _limit >= 0:
                    records = records[:_limit]
            cycles: List[Any] = []
            for n in records:
                d = _loads(n.content)
                if d is not None:
                    cycles.append(d)
            traj = {"cycles": cycles}
        traj.setdefault("meta", {"exported_at": time.time(), "engine_version": "lingshu_ng",
                                 "condition_space": "轨迹导出 · 训练资产格式（有损投影）"})
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(traj, f, ensure_ascii=False, indent=2)
        return traj

    def export_structured_trajectories(self, limit: int = 10, output_path: Optional[str] = None) -> Dict[str, Any]:
        """批量导出最近 ``limit`` 条轨迹（按时间降序，上游 #57）。"""
        return self.export_trajectory(None, output_path, _limit=limit)


def _loads(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None
