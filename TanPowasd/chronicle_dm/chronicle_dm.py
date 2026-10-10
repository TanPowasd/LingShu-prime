"""编年判别记忆（ChronicleDM）：编年 × 判别式记忆合体。

分工
- 编年（chronicle.ChronicleMemory）是底层版本时间线：唯一写入口，保存每次
  变更的操作、旧值→新值、生效/记录时间、缘由与原文引文，回答四态、历史、
  变更链、缘由。
- 判别式记忆（discriminative_memory.Memory）是外壳：同一批事件镜像写入，
  负责按需求求证（证书、最小证据集、预算内选证据）与 BM25 原文检索。

查询时两边同时出答案，``agree`` 标出二者对“该时点取值”是否一致；四态以编年
为准（Memory 不区分“已撤销”和“不存在”），证据同时附上编年事件（含缘由）和
Memory 选出的原文。两个原包一行不改。
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from chronicle import ChronicleMemory, Query as CQuery            # noqa: E402
from discriminative_memory import Memory, Need, Query as DQuery, Slot   # noqa: E402

OPS = ("set", "correct", "restore", "retire", "unresolved", "resolve")
MODES = ("current", "state", "at", "history", "chain", "reason")
_STATE_ZH = {"active": "有效", "retired": "已撤销", "unresolved": "未裁定", "absent": "不存在"}


def _norm(value: Any) -> Any:
    """Memory 以 JSON 存值；比较前统一成同一形态。"""
    return None if value is None else json.loads(json.dumps(value, ensure_ascii=False))


class ChronicleDM:
    """单一写入口，双核心查询。"""

    def __init__(self, path: str = ":memory:", *, scope: str = "default") -> None:
        self.timeline = ChronicleMemory()
        self.memory = Memory(path)
        self.scope = scope
        self._slots: dict[tuple[str, str], Slot] = {}

    # ---------- 写入 ----------
    def _slot(self, entity: str, facet: str) -> tuple[tuple[str, str], Slot]:
        key = (self.timeline._canonical("entity", entity), self.timeline._canonical("facet", facet))
        if key not in self._slots:
            self._slots[key] = Slot.of(*key)
        return key, self._slots[key]

    def add_alias(self, kind: str, alias: str, canonical: str) -> None:
        if any(k[0 if kind == "entity" else 1] == alias for k in self._slots):
            raise ValueError("alias must be declared before the alias name is written")
        self.timeline.add_alias(kind, alias, canonical)

    def record(self, event_id: str, entity: str, facet: str, operation: str, *,
               effective_at: float, recorded_at: float, value: Any = None,
               alternative: Any = None, reason: str | None = None, quote: str = "",
               source_id: str | None = None, metadata: Mapping[str, Any] | None = None):
        """写一条版本事件：先校验，再镜像进 Memory，最后落编年。"""
        if operation not in OPS:
            raise ValueError(f"unknown operation: {operation}")
        if event_id in self.timeline._events:
            raise ValueError(f"event id already exists: {event_id}")
        if operation in ("set", "correct", "restore", "resolve") and value is None:
            raise ValueError(f"{operation} needs a value")
        if operation == "unresolved" and (value is None or alternative is None):
            raise ValueError("unresolved needs value and alternative")
        (ent, fac), slot = self._slot(entity, facet)
        text = quote.strip() or f"{ent}·{fac} {operation} {value if value is not None else ''}".strip()
        if reason:
            text += f"（缘由：{reason}）"
        common = dict(effective_at=effective_at, recorded_at=recorded_at, scope=self.scope)
        if operation == "unresolved":
            self.memory.append(event_id + "#a", text, assertions={slot: _norm(value)}, **common)
            self.memory.append(event_id + "#b", text, assertions={slot: _norm(alternative)}, **common)
        else:
            mval = None if operation == "retire" else _norm(value)
            self.memory.append(event_id, text, assertions={slot: mval}, **common)
        return self.timeline.emit(
            event_id, source_id or event_id, ent, fac, operation,
            effective_at=effective_at, recorded_at=recorded_at, value=value,
            alternative=alternative, reason=reason, quote=quote, metadata=metadata)

    def append_raw(self, source_id: str, text: str, *, recorded_at: float) -> None:
        self.memory.append_raw(source_id, text, recorded_at=recorded_at, scope=self.scope)
        self.timeline.append_raw(source_id, text, recorded_at=recorded_at)

    # ---------- 查询 ----------
    def ask(self, entity: str, facet: str, mode: str = "current", *, at: float = math.inf,
            event_at: float | None = None, budget: int = 10 ** 9) -> dict[str, Any]:
        if mode not in MODES:
            raise ValueError(f"unknown query mode: {mode}")
        (ent, fac), slot = self._slot(entity, facet)
        c = self.timeline.query(CQuery(ent, fac, mode=mode, at=at, event_at=event_at))
        st = self.timeline.state_at(CQuery(ent, fac, mode="state", at=at))
        t = at if math.isfinite(at) else self._last_time(ent, fac)
        dm = None
        if t is not None:
            need = Need("h", slot, "history") if mode in ("history", "chain") else Need("v", slot)
            dm = self.memory.query(DQuery((need,), float(t), scope=self.scope), budget)
        out = {"slot": (ent, fac), "mode": mode, "at": at,
               "state": st["state"], "value": st["value"], "alternative": st["alternative"],
               "since": st["at"], "event_id": st["event_id"],
               "chain": c.get("chain", []), "reason": None,
               "events": c.get("evidence", []),
               "sources": [] if dm is None else dm["evidence"],
               "memory": None if dm is None else dm["answers"],
               "agree": self._agree(st, dm, mode)}
        if mode == "reason":
            out["reason"] = c["value"]
            out["reason_event"] = c["event_id"]
        return out

    def _last_time(self, ent: str, fac: str):
        ev = self.timeline.events(ent, fac)
        return ev[-1].effective_at if ev else None

    @staticmethod
    def _agree(st: dict, dm: dict | None, mode: str) -> bool | None:
        if dm is None:
            return st["state"] == "absent"
        if mode in ("history", "chain"):
            return None   # 历史以编年为准，Memory 历史只作旁证
        a = dm["answers"]["v"]
        if st["state"] == "active":
            return a["status"] == "known" and a["value"] == _norm(st["value"])
        if st["state"] == "unresolved":
            want = sorted(map(json.dumps, (_norm(st["value"]), _norm(st["alternative"]))))
            return a["status"] == "conflict" and sorted(map(json.dumps, a["value"] or [])) == want
        return a["status"] == "unknown"   # 已撤销 / 不存在

    # ---------- 给 LLM 读者的材料 ----------
    @staticmethod
    def render(result: dict[str, Any]) -> str:
        ent, fac = result["slot"]
        when = "最新" if not math.isfinite(result["at"]) else f"第{result['at']:g}"
        lines = [f"槽位：{ent} · {fac}　查询时点：{when}",
                 f"状态：{_STATE_ZH[result['state']]}；取值：{result['value']}"
                 + (f" / {result['alternative']}（并存）" if result["alternative"] is not None else "")
                 + (f"；自第{result['since']:g}起" if result["since"] is not None else ""),
                 f"两核心一致：{ {True: '是', False: '否', None: '—'}[result['agree']] }"]
        if result.get("reason") is not None or result["mode"] == "reason":
            lines.append(f"缘由：{result.get('reason')}")
        if result["chain"]:
            lines.append("版本链：")
            for r in result["chain"]:
                lines.append(f"- 第{r['seq']:g}：{r['from']} → {r['to']}（{_STATE_ZH[r['state']]}）"
                             + (f"，缘由：{r['reason']}" if r.get("reason") else ""))
        return "\n".join(lines)

    def search_raw(self, text: str, *, budget: int = 4000, limit: int = 20):
        return self.memory.search_raw(text, scope=self.scope, budget=budget, limit=limit)

    def statistics(self) -> dict[str, Any]:
        return {"timeline": self.timeline.statistics(), "memory": self.memory.statistics()}

    def close(self) -> None:
        self.memory.close()


__all__ = ["ChronicleDM", "OPS", "MODES"]
