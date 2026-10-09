"""写入闸：插件写入认知图的唯一通道（统一认知的守门人）。

纪律：
  1. 只许写 manifest.writes 声明过的种类；
  2. 条件显式：ConditionSpace 四字段必须给全，不替插件补默认；
  3. 零 LLM：闸内只做确定性校验与落库，不调用任何模型；
  4. 溯源：每条写入打上 provenance=plugin://名@版本 与写入种类标签；
  5. 原文落库：content 必须是非空字符串，不做改写。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

COND_FIELDS = ("observation_position", "observation_tool", "time_window", "existence_constraint")


class GateRejected(PermissionError):
    pass


@dataclass
class WriteRecord:
    plugin: str
    kind: str
    node_id: Optional[str]
    accepted: bool
    reason: str
    ts: float = field(default_factory=time.time)


class WriteGate:
    def __init__(self, engine: Any):
        self._engine = engine
        self.log: List[WriteRecord] = []

    def _cond(self, condition: Dict) -> Any:
        if not isinstance(condition, dict):
            raise GateRejected("condition 必须是 dict（条件显式）")
        missing = [f for f in COND_FIELDS if f not in condition]
        if missing:
            raise GateRejected(f"条件不完整，缺 {missing}（闸不代补默认）")
        tw = condition["time_window"]
        if not (isinstance(tw, (list, tuple)) and len(tw) == 2):
            raise GateRejected("time_window 须为二元组")
        # 鸭子类型拿 ConditionSpace：与引擎同模块，避免本包硬依赖 lingshu
        mod = __import__(type(self._engine).__module__, fromlist=["ConditionSpace"])
        CS = getattr(mod, "ConditionSpace")
        return CS(observation_position=str(condition["observation_position"]),
                  observation_tool=str(condition["observation_tool"]),
                  time_window=(float(tw[0]), float(tw[1])),
                  existence_constraint=str(condition["existence_constraint"]))

    def write(self, manifest, kind: str, content: str, condition: Dict,
              importance: float = 0.5, tags=None) -> str:
        try:
            if kind not in manifest.writes:
                raise GateRejected(f"{manifest.name} 未声明写入种类 {kind!r}（已声明 {list(manifest.writes)}）")
            if not isinstance(content, str) or not content.strip():
                raise GateRejected("content 须为非空原文字符串")
            if not (0.0 <= float(importance) <= 1.0):
                raise GateRejected("importance 须在 [0,1]")
            cs = self._cond(condition)
        except GateRejected as e:
            self.log.append(WriteRecord(manifest.name, kind, None, False, str(e)))
            raise
        node = self._engine.add_perception(
            content, modality=f"plugin:{manifest.name}", condition_space=cs,
            importance=float(importance),
            tags=list(tags or []) + [f"kind:{kind}", f"provenance:{manifest.provenance}"],
            skip_dedup=True)
        self.log.append(WriteRecord(manifest.name, kind, node.id, True, "ok"))
        return node.id
