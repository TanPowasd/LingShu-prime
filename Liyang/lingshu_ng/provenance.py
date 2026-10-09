# -*- coding: utf-8 -*-
"""provenance · 记忆写入的「来源与验证」契约（ng 版，API 与旧版一致）

每条记忆必须能回答：谁说的(source) / 在哪观测 / 用什么工具 / 哪个会话 / 什么时候 /
验证过没有（状态 + 方式 + 可复现凭证）。四栏原样进 condition_space，其余落结构化 tag。

相对旧版修正的缺陷类别：
  * #146 ``to_tags`` 写出的验证方式与 ``vref:`` 凭证 ``from_legacy`` 读不回 ⇒ 本版
    :func:`from_legacy` 识别全部 :data:`VERIFY_METHODS` 标签与 ``vref:*``，往返无损；
  * #20 ``human_review`` 永远推不出 ⇒ 同上；
  * #83/PR11 显式来源被处理路径标签覆盖、``verified`` 漏推 ⇒ 来源声明优先、
    验证状态按强度取最强。

不变量：``from_legacy(p.to_tags(extra), condition_space=p.to_condition_space())`` 对
``source / session_id / 四栏 / verify_status / verify_methods / verify_ref`` 往返不变。
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["POSITIONS", "TOOLS", "SOURCES", "VERIFY_STATUS", "VERIFY_METHODS", "STRONG_METHODS",
           "CS_FIELDS", "DEFAULT_CS", "DEFAULT_WINDOW", "Provenance", "new_provenance",
           "from_legacy", "is_default_cs", "strip_source_tags"]

POSITIONS = {"电脑端·DSH", "灵枢·语音", "感知·摄像头", "感知·屏幕", "云端·知识入库", "测试台",
             "协议基底", "未知观测位"}
TOOLS = {"dsh", "lingshu_voice", "vision_pipeline", "screen_capture", "knowledge_ingest",
         "consolidation_engine", "bench_fixture", "protocol_core", "unknown"}
SOURCES = {"user", "assistant", "system", "tool", "external", "fixture", "unknown"}
VERIFY_STATUS = ("unverified", "partial", "verified", "anchored")
VERIFY_METHODS = {"none", "llm_verify", "cross_channel", "whitebox_code", "action_world", "human_review"}
STRONG_METHODS = {"whitebox_code", "action_world", "human_review"}
CS_FIELDS = ("observation_position", "observation_tool", "time_window", "existence_constraint")
DEFAULT_CS = {"observation_position": "感知系统", "observation_tool": "感官输入",
              "existence_constraint": "协议实例运行中"}
DEFAULT_WINDOW = 3600.0
#: 显式来源的优先序（同时出现多个来源标签时取首个）
_SOURCE_PRIORITY = ("user", "assistant", "external", "system", "tool", "fixture")


@dataclass
class Provenance:
    """一条记忆的来源与验证声明。"""
    source: str = "unknown"
    observation_position: str = "未知观测位"
    observation_tool: str = "unknown"
    session_id: Optional[str] = None
    time_window: Tuple[float, float] = (0.0, 0.0)
    existence_constraint: str = "（未声明）"
    verify_status: str = "unverified"
    verify_methods: List[str] = field(default_factory=lambda: ["none"])
    verify_ref: str = ""
    synthetic: List[str] = field(default_factory=list)

    def to_condition_space(self) -> Dict[str, Any]:
        """协议四栏（严格四键）。"""
        return {"observation_position": self.observation_position,
                "observation_tool": self.observation_tool,
                "time_window": list(self.time_window),
                "existence_constraint": self.existence_constraint}

    def to_tags(self, extra: Optional[List[str]] = None) -> List[str]:
        """来源/会话/验证 → 结构化 tag（未验证不写状态标签）。"""
        out: List[str] = []
        for t in list(extra or []) + (["session:" + str(self.session_id)] if self.session_id else []):
            if t and t not in out:
                out.append(t)
        if self.source and self.source != "unknown" and self.source not in out:
            out.append(self.source)
        if self.verify_status != "unverified":
            for t in [self.verify_status] + [m for m in self.verify_methods if m and m != "none"] \
                    + (["vref:" + self.verify_ref] if self.verify_ref else []):
                if t not in out:
                    out.append(t)
        return out

    def to_sql(self, extra_tags: Optional[List[str]] = None) -> Tuple[str, str]:
        """(condition_space_json, tags_json)。"""
        return (json.dumps(self.to_condition_space(), ensure_ascii=False),
                json.dumps(self.to_tags(extra_tags), ensure_ascii=False))

    def to_json(self) -> str:
        """全量 JSON。"""
        d = asdict(self)
        d["time_window"] = list(self.time_window)
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "Provenance":
        """从 JSON 还原（未知键忽略）。"""
        d = json.loads(s or "{}")
        tw = d.get("time_window") or [0.0, 0.0]
        d["time_window"] = (float(tw[0]), float(tw[1]))
        for k in ("verify_methods", "synthetic"):
            v = d.get(k)
            d[k] = list(v) if isinstance(v, (list, tuple)) else ([] if k == "synthetic" else ["none"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def strength(self) -> str:
        """验证强度：strong / weak / none。"""
        if self.verify_status == "unverified":
            return "none"
        return "strong" if any(m in STRONG_METHODS for m in self.verify_methods) else "weak"

    def is_traceable(self) -> bool:
        """能否回答「谁、哪个会话、什么时候」。"""
        if self.source == "unknown":
            return False
        if self.source in ("user", "assistant"):
            return bool(self.session_id) and self.observation_tool != "unknown" and self.time_window[0] > 0
        return True

    def extensions(self) -> List[str]:
        """取值域之外的扩展值（不是错误，回填时须原样保留）。"""
        out = []
        if self.observation_position not in POSITIONS:
            out.append("observation_position=" + str(self.observation_position))
        if self.observation_tool not in TOOLS:
            out.append("observation_tool=" + str(self.observation_tool))
        return out

    def validate(self) -> List[str]:
        """问题列表（空 = 合规）。"""
        p: List[str] = []
        if self.source not in SOURCES:
            p.append(f"source 取值非法: {self.source}")
        for k, dom in (("observation_position", POSITIONS), ("observation_tool", TOOLS)):
            v = getattr(self, k)
            if v not in dom:
                p.append(f"{k} 无信息量: {v!r}" if not v or v in DEFAULT_CS.values()
                         else f"{k} 取值域外（扩展值）: {v}")
        tw = self.time_window
        if not (isinstance(tw, (tuple, list)) and len(tw) == 2):
            p.append("time_window 必须是 [start, end]")
        elif tw[0] > tw[1]:
            p.append(f"time_window 起点晚于终点: {tw}")
        elif tw[0] <= 0:
            p.append("time_window 缺观测时刻（start <= 0）")
        if self.verify_status not in VERIFY_STATUS:
            p.append(f"verify_status 取值非法: {self.verify_status}")
        bad = [m for m in self.verify_methods if m not in VERIFY_METHODS]
        if bad:
            p.append(f"verify_methods 取值非法: {bad}")
        if self.source in ("user", "assistant") and not self.session_id:
            p.append("source 为 user/assistant 但缺 session_id —— 无法回溯到具体会话")
        if self.verify_status != "unverified":
            if self.verify_methods == ["none"] or not self.verify_methods:
                p.append("声称已验证但未声明 verify_methods")
            if not self.verify_ref:
                p.append("声称已验证但缺 verify_ref（不可复现的验证等于没验证）")
        if self.synthetic:
            p.append("含推断/回填字段: " + ",".join(self.synthetic) + "（非原始观测）")
        return p


def new_provenance(position: str, tool: str, source: str, session_id: Optional[str] = None,
                   existence_constraint: str = "协议实例运行中", verify_status: str = "unverified",
                   verify_methods: Optional[List[str]] = None, verify_ref: str = "",
                   observed_at: Optional[float] = None, window: float = DEFAULT_WINDOW) -> Provenance:
    """写入方构造合规 provenance。"""
    t0 = float(observed_at if observed_at is not None else time.time())
    return Provenance(source=source, observation_position=position, observation_tool=tool,
                      session_id=session_id, time_window=(t0, t0 + window),
                      existence_constraint=existence_constraint, verify_status=verify_status,
                      verify_methods=list(verify_methods or ["none"]), verify_ref=verify_ref)


def _tags(tags: Any) -> List[str]:
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except ValueError:
            return []
    return [str(t).strip() for t in (tags or [])]


def strip_source_tags(tags: Any) -> List[str]:
    """剔除来源类保留标签（user/assistant/external/system/tool/fixture 与 session:/role: 前缀）。
    合并进既有节点时用：来源只能在创建时由写入路径声明，命中不得追加（上游 #217）。"""
    from .dedup import SOURCE_TAGS
    return [t for t in _tags(tags) if t.lower() not in SOURCE_TAGS
            and not t.lower().startswith(("session:", "role:"))]


def _infer_tool(p: Provenance, low: set, modality: str) -> None:
    rules = (("dsh", "dsh", "电脑端·DSH"), ("voice", "lingshu_voice", "灵枢·语音"),
             ("knowledge_ingest", "knowledge_ingest", "云端·知识入库"),
             ("consolidation", "consolidation_engine", "测试台"))
    if "dsh" in low or "voice" in low:
        tag = "dsh" if "dsh" in low else "voice"
        _, p.observation_tool, p.observation_position = next(r for r in rules if r[0] == tag)
    elif modality == "image":
        p.observation_tool, p.observation_position = "vision_pipeline", "感知·摄像头"
    elif "knowledge_ingest" in low or "consolidation" in low:
        tag = "knowledge_ingest" if "knowledge_ingest" in low else "consolidation"
        _, p.observation_tool, p.observation_position = next(r for r in rules if r[0] == tag)
    elif "novel_prefeed" in low or "gate" in low:
        p.observation_tool, p.observation_position = "bench_fixture", "测试台"


def _infer_source(p: Provenance, ts: List[str], low: set) -> None:
    for s in _SOURCE_PRIORITY:
        if s in low:
            p.source = s
            return
    if p.observation_tool == "bench_fixture":
        p.source = "fixture"
    elif "consolidation" in low:
        p.source = "system"
    elif "白箱校验" in ts or "llm_verify" in low:
        p.source = "assistant"


def _infer_window(p: Provenance, cs: Any, created_at: Optional[float]) -> None:
    if isinstance(cs, str):
        try:
            cs = json.loads(cs or "{}")
        except ValueError:
            cs = {}
    cs = cs or {}
    tw = cs.get("time_window")
    if isinstance(tw, (list, tuple)) and len(tw) == 2 and tw[0] is not None and float(tw[0]) > 0:
        p.time_window = (float(tw[0]), float(tw[1]) if tw[1] is not None else float("inf"))
    elif created_at:
        p.time_window = (float(created_at), float(created_at) + DEFAULT_WINDOW)
        p.synthetic.append("time_window")
    for k, v in DEFAULT_CS.items():
        cur = cs.get(k)
        if cur and cur != v:
            setattr(p, k, cur)
        else:
            p.synthetic.append(k)
    if not cs.get("existence_constraint"):
        p.existence_constraint = "（未声明）"


def from_legacy(tags: Any, created_at: Optional[float] = None, condition_space: Any = None,
                modality: str = "text") -> Provenance:
    """从既有行反推 provenance；只做有证据的推断，推不出的记入 synthetic。"""
    ts = _tags(tags)
    low = {t.lower() for t in ts}
    p = Provenance()
    p.session_id = next((t.split(":", 1)[1] for t in ts if t.startswith("session:")), None)
    if not p.session_id:
        role = next((t.split(":", 1)[1] for t in ts if t.startswith("role:")), None)
        if role:
            p.session_id = "role-session-" + role
            p.synthetic.append("session_id")
    _infer_tool(p, low, modality)
    _infer_source(p, ts, low)
    _infer_window(p, condition_space, created_at)
    p.verify_status = next((s for s in reversed(VERIFY_STATUS) if s in low), "unverified")
    methods = [m for m in sorted(VERIFY_METHODS - {"none"}) if m in low]
    if "白箱校验" in ts and "whitebox_code" not in methods:
        methods.insert(0, "whitebox_code")
    p.verify_methods = methods or ["none"]
    p.verify_ref = next((t.split(":", 1)[1] for t in ts if t.startswith("vref:")), "")
    if not p.session_id and p.source in ("user", "assistant"):
        p.synthetic.append("session_id")
    return p


def is_default_cs(cs: Any) -> bool:
    """condition_space 是否为引擎默认值（缺键也算无信息量）。"""
    if isinstance(cs, str):
        try:
            cs = json.loads(cs or "{}")
        except ValueError:
            return True
    cs = cs or {}
    return all(cs.get(k, v) == v for k, v in DEFAULT_CS.items())
