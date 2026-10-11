"""Append-only single-value fact slots with effective and recorded clocks.

Changes create episodes. Corrections revise one episode. Retraction disables
an episode; restoration uses its latest revision. Plans never set actual state.
Inputs are caller-validated structured facts, not extracted natural language.
"""
from __future__ import annotations
import json
import math

UNSET = object()


def finite(value, name):
    try:
        value = float(value)
    except (ValueError,TypeError):
        raise ValueError(name + " must be an explicit finite time") from None
    if not math.isfinite(value):
        raise ValueError(name + " must be finite")
    return value


def scalar(value):
    if not isinstance(value, (str, int, float, bool, type(None))):
        raise ValueError("Fact values must be immutable scalars")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Fact values must be finite")
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class TemporalFacts:
    def __init__(self, db):
        self.db = db
        with db.tx() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS temporal_facts (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                root_id TEXT NOT NULL, parent_id TEXT, scope TEXT NOT NULL,
                fact_key TEXT NOT NULL, kind TEXT NOT NULL, effective_at REAL,
                valid_to REAL, recorded_at REAL NOT NULL, value_json TEXT,
                source_quote TEXT NOT NULL, source_ref TEXT NOT NULL,
                related_plan TEXT)""")
            c.execute("CREATE INDEX IF NOT EXISTS tf_slot ON temporal_facts(scope,fact_key,recorded_at)")
            c.execute("CREATE INDEX IF NOT EXISTS tf_root ON temporal_facts(root_id,seq)")
            c.execute("""CREATE TRIGGER IF NOT EXISTS tf_no_update BEFORE UPDATE ON temporal_facts
                BEGIN SELECT RAISE(ABORT,'temporal facts are append-only'); END""")
            c.execute("""CREATE TRIGGER IF NOT EXISTS tf_no_delete BEFORE DELETE ON temporal_facts
                BEGIN SELECT RAISE(ABORT,'temporal facts are append-only'); END""")

    def get(self, event_id):
        rows = self.db.all("SELECT * FROM temporal_facts WHERE id=?", (event_id,))
        if not rows:
            raise ValueError("Unknown fact event: " + event_id)
        return dict(rows[0])

    def _append(self, *, event_id, root, parent, scope, key, kind, effective,
                end, recorded, value_json, source, source_ref, related_plan=None):
        recorded = finite(recorded, "recorded_at")
        if not event_id or not scope or not key or not isinstance(source, str) or not source.strip():
            raise ValueError("Event id, scope, fact key, and original source are required")
        with self.db.tx() as c:
            last = c.execute("SELECT MAX(recorded_at) FROM temporal_facts").fetchone()[0]
            if last is not None and recorded < last:
                raise ValueError("Receipt time must not move backwards; use effective_at for late history")
            if c.execute("SELECT 1 FROM temporal_facts WHERE id=?", (event_id,)).fetchone():
                raise ValueError("Event IDs cannot be reused")
            c.execute("""INSERT INTO temporal_facts
                (id,root_id,parent_id,scope,fact_key,kind,effective_at,valid_to,
                 recorded_at,value_json,source_quote,source_ref,related_plan)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id,root,parent,scope,key,kind,effective,end,recorded,value_json,
                 source,source_ref,related_plan))
        return event_id

    def assert_state(self, event_id, key, value, *, effective_at, recorded_at,
                     scope="default", source, source_ref="", valid_to=None, plan=False):
        effective = finite(effective_at, "effective_at")
        end = None if valid_to is None else finite(valid_to, "valid_to")
        if end is not None and end <= effective:
            raise ValueError("valid_to must be after effective_at")
        return self._append(event_id=event_id,root=event_id,parent=None,scope=scope,key=key,
            kind="plan" if plan else "state",effective=effective,end=end,recorded=recorded_at,
            value_json=scalar(value),source=source,source_ref=source_ref)

    def _root_rows(self, root):
        return [dict(r) for r in self.db.all("SELECT * FROM temporal_facts WHERE root_id=? ORDER BY seq", (root,))]

    def correct(self, event_id, target, *, recorded_at, source, source_ref="",
                value=UNSET, effective_at=UNSET, valid_to=UNSET):
        with self.db.tx():
            old = self.get(target)
            if old["kind"] not in ("state", "plan", "correction"):
                raise ValueError("Correction must target a fact revision")
            rows = self._root_rows(old["root_id"])
            latest = [r for r in rows if r["kind"] in ("state", "plan", "correction")][-1]
            if latest["id"] != target:
                raise ValueError("Target has a newer correction; correct the latest revision explicitly")
            start = old["effective_at"] if effective_at is UNSET else finite(effective_at, "effective_at")
            end = old["valid_to"] if valid_to is UNSET else None if valid_to is None else finite(valid_to,"valid_to")
            if end is not None and end <= start:
                raise ValueError("valid_to must be after effective_at")
            return self._append(event_id=event_id,root=old["root_id"],parent=target,
                scope=old["scope"],key=old["fact_key"],kind="correction",effective=start,end=end,
                recorded=recorded_at,value_json=old["value_json"] if value is UNSET else scalar(value),
                source=source,source_ref=source_ref)

    def set_enabled(self, event_id, target, *, enabled, recorded_at, source, source_ref=""):
        with self.db.tx():
            old = self.get(target)
            return self._append(event_id=event_id,root=old["root_id"],parent=target,
                scope=old["scope"],key=old["fact_key"],kind="restore" if enabled else "retract",
                effective=None,end=None,recorded=recorded_at,value_json=None,
                source=source,source_ref=source_ref)

    def confirm_plan(self, event_id, plan_id, *, effective_at, recorded_at,
                     source, source_ref="", value=UNSET):
        with self.db.tx():
            plan = self.get(plan_id)
            rows = self._root_rows(plan["root_id"])
            if rows[0]["kind"] != "plan":
                raise ValueError("Confirmation must reference a plan")
            controls = [r for r in rows if r["kind"] in ("retract", "restore")]
            if controls and controls[-1]["kind"] == "retract":
                raise ValueError("Cannot confirm a withdrawn plan")
            last = [r for r in rows if r["kind"] in ("plan", "correction")][-1]
            existing = self.db.all("SELECT id FROM temporal_facts WHERE related_plan=?", (plan["root_id"],))
            if existing:
                raise ValueError("Plan already has a confirmation; revise that event instead")
            start = finite(effective_at,"effective_at")
            return self._append(event_id=event_id,root=event_id,parent=None,scope=plan["scope"],
                key=plan["fact_key"],kind="state",effective=start,end=None,recorded=recorded_at,
                value_json=last["value_json"] if value is UNSET else scalar(value),
                source=source,source_ref=source_ref,related_plan=plan["root_id"])

    def _views(self, key, scope, known_at):
        rows = [dict(r) for r in self.db.all("""SELECT * FROM temporal_facts
            WHERE scope=? AND fact_key=? AND recorded_at<=? ORDER BY seq""", (scope,key,known_at))]
        roots = {}
        for row in rows:
            roots.setdefault(row["root_id"],[]).append(row)
        out = []
        for root, revisions in roots.items():
            base = revisions[0]
            controls = [r for r in revisions if r["kind"] in ("retract","restore")]
            enabled = not controls or controls[-1]["kind"] == "restore"
            versions = [r for r in revisions if r["kind"] in ("state","plan","correction")]
            tip = versions[-1]
            out.append({"root":root,"base_kind":base["kind"],"enabled":enabled,
                        "tip":tip,"versions":versions,"controls":controls})
        return out

    @staticmethod
    def _resolve(views, at):
        facts = [v for v in views if v["enabled"] and v["base_kind"] == "state"]
        past = [v for v in facts if v["tip"]["effective_at"] <= at]
        if not past:
            future = [v["tip"]["effective_at"] for v in facts if v["tip"]["effective_at"] > at]
            return {"status":"unknown","value":None,"alternatives":[],"tip_ids":[],
                    "valid_from":None,"valid_to":min(future) if future else None,"evidence":[],"revisions":[]}
        start = max(v["tip"]["effective_at"] for v in past)
        group = [v for v in past if v["tip"]["effective_at"] == start]
        live = [v for v in group if v["tip"]["valid_to"] is None or at < v["tip"]["valid_to"]]
        boundaries = [v["tip"]["effective_at"] for v in facts if v["tip"]["effective_at"] > at]
        boundaries += [v["tip"]["valid_to"] for v in group if v["tip"]["valid_to"] is not None and v["tip"]["valid_to"] > at]
        if not live:
            start = max(v["tip"]["valid_to"] for v in group)
        else:
            elapsed = [v["tip"]["valid_to"] for v in group if v["tip"]["valid_to"] is not None and v["tip"]["valid_to"] <= at]
            if elapsed:
                start = max(start,max(elapsed))
        values = list(dict.fromkeys(v["tip"]["value_json"] for v in live))
        status = "unknown" if not values or values == ["null"] else "known" if len(values) == 1 else "conflict"
        end = min(boundaries) if boundaries else None
        return {"status":status,"value":json.loads(values[0]) if status == "known" else None,
                "alternatives":[json.loads(v) for v in values] if status=="conflict" else [],
                "tip_ids":[v["tip"]["id"] for v in live],"valid_from":start,"valid_to":end,
                "evidence":[{"id":v["tip"]["id"],"root_id":v["root"],"quote":v["tip"]["source_quote"],
                             "ref":v["tip"]["source_ref"]} for v in live],
                "revisions":[{"root_id":v["root"],"versions":[{"id":r["id"],"quote":r["source_quote"],
                             "recorded_at":r["recorded_at"]} for r in v["versions"]],
                              "controls":[{"id":r["id"],"kind":r["kind"],"quote":r["source_quote"]} for r in v["controls"]]}
                             for v in live if len(v["versions"])>1 or v["controls"]]}

    def resolve(self, key, *, scope="default", at, known_at=math.inf):
        at = finite(at,"at")
        if math.isnan(float(known_at)):
            raise ValueError("known_at cannot be NaN")
        result = self._resolve(self._views(key,scope,known_at),at)
        return {"scope":scope,"fact_key":key,"at":at,"known_at":None if known_at==math.inf else known_at,**result}

    def timeline(self, key, *, scope="default", known_at=math.inf):
        views = self._views(key,scope,known_at)
        facts = [v for v in views if v["enabled"] and v["base_kind"] == "state"]
        boundaries = sorted({v["tip"]["effective_at"] for v in facts} |
                            {v["tip"]["valid_to"] for v in facts if v["tip"]["valid_to"] is not None})
        out = []
        for start in boundaries:
            r = self._resolve(views,start)
            if r["valid_from"] != start:
                continue
            out.append(r)
        return out

    def history(self, key, *, scope="default", known_at=math.inf):
        return [dict(r) for r in self.db.all("""SELECT * FROM temporal_facts
            WHERE scope=? AND fact_key=? AND recorded_at<=? ORDER BY seq""", (scope,key,known_at))]
