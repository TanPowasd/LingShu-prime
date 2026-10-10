"""Generic version-chain memory.

The core is deliberately independent of domain words and language parsers.
Callers submit confirmed events; every event remains immutable evidence.  A
query is routed by its information need before any lexical fallback is used:
point-in-time and current questions use interval lookup, history/change
questions expand a chain, and reason questions select one transition.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
import copy
import json
import math
import re
from typing import Any, Iterable, Mapping


OPS = frozenset({"set", "correct", "restore", "retire", "unresolved", "resolve"})
MODES = frozenset({"current", "state", "at", "history", "chain", "reason"})
_MISSING = object()


def _finite(value: float | int, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _copy(value: Any) -> Any:
    return json.loads(_json(value))


@dataclass(frozen=True)
class Event:
    """One immutable state transition.

    ``previous`` is the value before this event.  ``alternative`` is used by
    an ``unresolved`` event.  A retired event has ``value=None`` while still
    proving that the slot existed before retirement.
    """

    event_id: str
    source_id: str
    entity: str
    facet: str
    operation: str
    effective_at: float
    recorded_at: float
    value: Any = None
    previous: Any = None
    alternative: Any = None
    reason: str | None = None
    quote: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    ordinal: int = 0

    def __post_init__(self) -> None:
        if not all(isinstance(x, str) and x.strip() for x in
                   (self.event_id, self.source_id, self.entity, self.facet)):
            raise ValueError("event/source/entity/facet must be nonempty strings")
        if self.operation not in OPS:
            raise ValueError(f"unknown operation: {self.operation}")
        _finite(self.effective_at, "effective_at")
        _finite(self.recorded_at, "recorded_at")
        if not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a mapping")
        # Fail early on unsupported values and detach caller-owned objects.
        _json(self.value)
        _json(self.previous)
        _json(self.alternative)
        object.__setattr__(self, "value", _copy(self.value))
        object.__setattr__(self, "previous", _copy(self.previous))
        object.__setattr__(self, "alternative", _copy(self.alternative))
        object.__setattr__(self, "effective_at", float(self.effective_at))
        object.__setattr__(self, "recorded_at", float(self.recorded_at))
        object.__setattr__(self, "metadata", _copy(dict(self.metadata)))

    @property
    def slot(self) -> tuple[str, str]:
        return self.entity, self.facet

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source_id": self.source_id,
            "entity": self.entity,
            "facet": self.facet,
            "operation": self.operation,
            "effective_at": self.effective_at,
            "recorded_at": self.recorded_at,
            "value": _copy(self.value),
            "previous": _copy(self.previous),
            "alternative": _copy(self.alternative),
            "reason": self.reason,
            "quote": self.quote,
            "metadata": _copy(dict(self.metadata)),
        }


@dataclass(frozen=True)
class Query:
    entity: str
    facet: str
    mode: str = "current"
    at: float = math.inf
    event_at: float | None = None
    conditions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all(isinstance(x, str) and x.strip() for x in (self.entity, self.facet)):
            raise ValueError("query entity/facet must be nonempty strings")
        if self.mode not in MODES:
            raise ValueError(f"unknown query mode: {self.mode}")
        if self.at != math.inf:
            _finite(self.at, "query.at")
        if self.event_at is not None:
            _finite(self.event_at, "query.event_at")
        if not isinstance(self.conditions, Mapping):
            raise ValueError("query.conditions must be a mapping")


class ChronicleMemory:
    """Append-only state chains with hard temporal query constraints."""

    def __init__(self) -> None:
        self._events: dict[str, Event] = {}
        self._by_slot: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._aliases: dict[str, dict[str, str]] = {"entity": {}, "facet": {}}
        self._raw: dict[str, dict[str, Any]] = {}
        self._ordinal = 0

    # ---------- identity and append-only storage ----------
    def add_alias(self, kind: str, alias: str, canonical: str) -> None:
        if kind not in self._aliases:
            raise ValueError("alias kind must be entity or facet")
        if not all(isinstance(x, str) and x.strip() for x in (alias, canonical)):
            raise ValueError("aliases must be nonempty strings")
        if alias == canonical:
            return
        probe = canonical
        seen = {alias}
        while True:
            if probe == alias:
                raise ValueError("alias cycle")
            if probe not in self._aliases[kind]:
                break
            if probe in seen:
                raise ValueError("alias cycle")
            seen.add(probe)
            probe = self._aliases[kind][probe]
        self._aliases[kind][alias] = canonical

    def _canonical(self, kind: str, value: str) -> str:
        seen = set()
        while value in self._aliases[kind]:
            if value in seen:
                raise ValueError("alias cycle")
            seen.add(value)
            value = self._aliases[kind][value]
        return value

    def _ordered(self, slot: tuple[str, str], at: float = math.inf) -> list[Event]:
        ids = self._by_slot.get(slot, ())
        return sorted((self._events[i] for i in ids if self._events[i].effective_at <= at),
                      key=lambda e: (e.effective_at, e.recorded_at, e.ordinal))

    def add_event(self, event: Event) -> Event:
        if event.event_id in self._events:
            raise ValueError(f"event id already exists: {event.event_id}")
        entity = self._canonical("entity", event.entity)
        facet = self._canonical("facet", event.facet)
        if (entity, facet) != event.slot:
            event = replace(event, entity=entity, facet=facet)
        self._ordinal += 1
        event = replace(event, ordinal=self._ordinal)
        self._events[event.event_id] = event
        self._by_slot[event.slot].append(event.event_id)
        return event

    def emit(self, event_id: str, source_id: str, entity: str, facet: str,
             operation: str, *, effective_at: float, recorded_at: float,
             value: Any = None, alternative: Any = None,
             previous: Any = _MISSING, reason: str | None = None,
             quote: str = "", metadata: Mapping[str, Any] | None = None) -> Event:
        slot = (self._canonical("entity", entity), self._canonical("facet", facet))
        if previous is _MISSING:
            previous = self.state_at(Query(*slot, mode="state", at=effective_at))["value"]
        return self.add_event(Event(
            event_id=event_id, source_id=source_id, entity=slot[0], facet=slot[1],
            operation=operation, effective_at=effective_at, recorded_at=recorded_at,
            value=value, previous=previous, alternative=alternative, reason=reason,
            quote=quote, metadata={} if metadata is None else metadata))

    def set(self, event_id: str, source_id: str, entity: str, facet: str, value: Any,
            *, effective_at: float, recorded_at: float, reason: str | None = None,
            quote: str = "", metadata: Mapping[str, Any] | None = None) -> Event:
        return self.emit(event_id, source_id, entity, facet, "set", value=value,
                         effective_at=effective_at, recorded_at=recorded_at,
                         reason=reason, quote=quote, metadata=metadata)

    def correct(self, event_id: str, source_id: str, entity: str, facet: str, value: Any,
                *, effective_at: float, recorded_at: float, reason: str | None = None,
                quote: str = "", metadata: Mapping[str, Any] | None = None) -> Event:
        return self.emit(event_id, source_id, entity, facet, "correct", value=value,
                         effective_at=effective_at, recorded_at=recorded_at,
                         reason=reason, quote=quote, metadata=metadata)

    def restore(self, event_id: str, source_id: str, entity: str, facet: str, value: Any,
                *, effective_at: float, recorded_at: float, reason: str | None = None,
                quote: str = "", metadata: Mapping[str, Any] | None = None) -> Event:
        return self.emit(event_id, source_id, entity, facet, "restore", value=value,
                         effective_at=effective_at, recorded_at=recorded_at,
                         reason=reason, quote=quote, metadata=metadata)

    def retire(self, event_id: str, source_id: str, entity: str, facet: str, *,
               effective_at: float, recorded_at: float, reason: str | None = None,
               quote: str = "", metadata: Mapping[str, Any] | None = None) -> Event:
        return self.emit(event_id, source_id, entity, facet, "retire", value=None,
                         effective_at=effective_at, recorded_at=recorded_at,
                         reason=reason, quote=quote, metadata=metadata)

    def unresolved(self, event_id: str, source_id: str, entity: str, facet: str,
                   value: Any, alternative: Any, *, effective_at: float,
                   recorded_at: float, reason: str | None = None, quote: str = "",
                   metadata: Mapping[str, Any] | None = None) -> Event:
        return self.emit(event_id, source_id, entity, facet, "unresolved", value=value,
                         alternative=alternative, effective_at=effective_at,
                         recorded_at=recorded_at, reason=reason, quote=quote,
                         metadata=metadata)

    def resolve(self, event_id: str, source_id: str, entity: str, facet: str, value: Any,
                *, effective_at: float, recorded_at: float, reason: str | None = None,
                quote: str = "", metadata: Mapping[str, Any] | None = None) -> Event:
        return self.emit(event_id, source_id, entity, facet, "resolve", value=value,
                         effective_at=effective_at, recorded_at=recorded_at,
                         reason=reason, quote=quote, metadata=metadata)

    # ---------- raw fallback ----------
    def append_raw(self, source_id: str, text: str, *, recorded_at: float,
                   searchable: bool = True) -> None:
        if source_id in self._raw or not isinstance(text, str) or not text:
            raise ValueError("raw source ids must be unique and text must be nonempty")
        self._raw[source_id] = {"id": source_id, "text": text,
                                "recorded_at": _finite(recorded_at, "recorded_at"),
                                "searchable": bool(searchable)}

    @staticmethod
    def _grams(text: str) -> set[str]:
        text = re.sub(r"\s+", "", text.lower())
        return {text[i:i + 2] for i in range(max(0, len(text) - 1))} or ({text} if text else set())

    def search_raw(self, text: str, *, limit: int = 20) -> dict[str, Any]:
        q = self._grams(text)
        scored = []
        for row in self._raw.values():
            if not row["searchable"]:
                continue
            grams = self._grams(row["text"])
            score = len(q & grams) / max(1, len(q))
            if score > 0:
                scored.append((score, -row["recorded_at"], row))
        scored.sort(key=lambda x: (-x[0], x[1], x[2]["id"]))
        return {"status": "evidence_only", "hits": [dict(x[2], score=x[0]) for x in scored[:limit]]}

    # ---------- state projections and query routing ----------
    @staticmethod
    def _state_from(events: list[Event]) -> dict[str, Any]:
        if not events:
            return {"state": "absent", "value": None, "alternative": None,
                    "at": None, "event_id": None}
        e = events[-1]
        if e.operation == "retire":
            state = "retired"
            value = None
            alt = None
        elif e.operation == "unresolved":
            state = "unresolved"
            value = e.value
            alt = e.alternative
        else:
            state = "active"
            value = e.value
            alt = None
        return {"state": state, "value": _copy(value), "alternative": _copy(alt),
                "at": e.effective_at, "event_id": e.event_id}

    def state_at(self, query: Query) -> dict[str, Any]:
        slot = (self._canonical("entity", query.entity), self._canonical("facet", query.facet))
        events = self._ordered(slot, query.at)
        state = self._state_from(events)
        state["slot"] = slot
        return state

    def _chain(self, events: list[Event]) -> list[dict[str, Any]]:
        out = []
        for e in events:
            to = None if e.operation == "retire" else _copy(e.value)
            row = {"event_id": e.event_id, "source_id": e.source_id,
                   "seq": e.effective_at, "from": _copy(e.previous), "to": to,
                   "state": "retired" if e.operation == "retire" else
                            "unresolved" if e.operation == "unresolved" else "active",
                   "alternative": _copy(e.alternative), "reason": e.reason,
                   "quote": e.quote}
            out.append(row)
        return out

    def query(self, query: Query) -> dict[str, Any]:
        slot = (self._canonical("entity", query.entity), self._canonical("facet", query.facet))
        events = self._ordered(slot, query.at)
        base = {"slot": slot, "mode": query.mode, "status": "unknown",
                "state": "absent", "value": None, "at": None,
                "event_id": None, "selected": [], "evidence": [], "chain": []}
        if query.mode in ("current", "state", "at"):
            state = self._state_from(events)
            base.update({"status": "known" if state["state"] == "active" else state["state"],
                         "state": state["state"], "value": state["value"],
                         "alternative": state["alternative"], "at": state["at"],
                         "event_id": state["event_id"]})
            if events:
                selected = [events[-1]]
                base["selected"] = [e.event_id for e in selected]
                base["evidence"] = [e.as_dict() for e in selected]
            return base
        chain = self._chain(events)
        base["chain"] = chain
        if query.mode == "chain":
            base.update(status="chain", value=chain, state=self._state_from(events)["state"])
            base["selected"] = [e["event_id"] for e in chain]
            base["evidence"] = [self._events[eid].as_dict() for eid in base["selected"]]
            return base
        if query.mode == "history":
            base.update(status="history", value=[dict(x) for x in chain],
                        state=self._state_from(events)["state"])
            base["selected"] = [e["event_id"] for e in chain]
            base["evidence"] = [self._events[eid].as_dict() for eid in base["selected"]]
            return base
        if query.mode == "reason":
            target = query.event_at if query.event_at is not None else query.at
            hits = [e for e in events if e.effective_at == target]
            if hits:
                e = hits[-1]
                event_state = ("retired" if e.operation == "retire" else
                               "unresolved" if e.operation == "unresolved" else "active")
                base.update(status="known" if event_state == "active" else event_state,
                            state=event_state,
                            value=e.reason, at=e.effective_at, selected=[e.event_id],
                            event_id=e.event_id, evidence=[e.as_dict()])
            else:
                base.update(status="unknown", selected=[], evidence=[])
            return base
        raise AssertionError(query.mode)

    def events(self, entity: str, facet: str, *, at: float = math.inf) -> tuple[Event, ...]:
        slot = (self._canonical("entity", entity), self._canonical("facet", facet))
        return tuple(self._ordered(slot, at))

    def statistics(self) -> dict[str, int]:
        return {"events": len(self._events), "slots": len(self._by_slot),
                "raw_sources": len(self._raw), "aliases": sum(len(x) for x in self._aliases.values())}


VersionChainMemory = ChronicleMemory  # 旧名兼容

__all__ = ["Event", "Query", "ChronicleMemory", "VersionChainMemory"]
