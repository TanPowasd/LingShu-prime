import json
import math
import unittest

from chronicle import Query, ChronicleMemory


class VersionChainTests(unittest.TestCase):
    def setUp(self):
        self.m = ChronicleMemory()

    def test_repeated_change_and_time_interval(self):
        self.m.set("e1", "s1", "person", "residence", "A", effective_at=1, recorded_at=1,
                   quote="person residence A")
        self.m.set("e2", "s2", "person", "residence", "B", effective_at=4, recorded_at=2,
                   quote="person residence B")
        self.m.set("e3", "s3", "person", "residence", "A", effective_at=7, recorded_at=3,
                   quote="person residence A again")
        self.assertEqual(self.m.query(Query("person", "residence", at=3))["value"], "A")
        self.assertEqual(self.m.query(Query("person", "residence", at=5))["value"], "B")
        self.assertEqual(self.m.query(Query("person", "residence", at=9))["value"], "A")
        chain = self.m.query(Query("person", "residence", mode="chain"))
        self.assertEqual([(x["from"], x["to"]) for x in chain["chain"]],
                         [(None, "A"), ("A", "B"), ("B", "A")])
        self.assertEqual(len(chain["evidence"]), 3)

    def test_retired_unresolved_and_resolved_are_distinct(self):
        self.m.set("e1", "s1", "item", "value", "old", effective_at=1, recorded_at=1)
        self.m.unresolved("e2", "s2", "item", "value", "new-a", "new-b",
                          effective_at=2, recorded_at=2, reason="two sources")
        unresolved = self.m.query(Query("item", "value", mode="state", at=2))
        self.assertEqual({k: unresolved[k] for k in ("state", "value", "alternative", "at", "event_id", "slot")}, {
            "state": "unresolved", "value": "new-a", "alternative": "new-b",
            "at": 2.0, "event_id": "e2", "slot": ("item", "value")})
        self.m.resolve("e3", "s3", "item", "value", "new-b", effective_at=3, recorded_at=3)
        self.assertEqual(self.m.query(Query("item", "value", mode="state", at=3))["state"], "active")
        self.m.retire("e4", "s4", "item", "value", effective_at=4, recorded_at=4,
                      reason="removed")
        retired = self.m.query(Query("item", "value", mode="state", at=4))
        self.assertEqual(retired["state"], "retired")
        self.assertIsNone(retired["value"])
        self.assertEqual(retired["selected"], ["e4"])

    def test_restore_and_reason_query_keep_provenance(self):
        self.m.set("e1", "s1", "service", "region", "east", effective_at=1, recorded_at=1,
                   reason="initial", quote="region is east")
        self.m.retire("e2", "s2", "service", "region", effective_at=2, recorded_at=2,
                      reason="decommission", quote="region retired")
        self.m.restore("e3", "s3", "service", "region", "west", effective_at=3, recorded_at=3,
                       reason="relaunch", quote="region restored west")
        result = self.m.query(Query("service", "region", mode="reason", event_at=2, at=2))
        self.assertEqual(result["value"], "decommission")
        self.assertEqual(result["evidence"][0]["quote"], "region retired")
        self.assertEqual(self.m.query(Query("service", "region", at=4))["value"], "west")

    def test_aliases_are_canonical_and_cycles_are_rejected(self):
        self.m.add_alias("entity", "她", "alice")
        self.m.add_alias("facet", "住址", "residence")
        self.m.set("e1", "s1", "alice", "residence", "Nanjing", effective_at=1, recorded_at=1)
        result = self.m.query(Query("她", "住址", at=2))
        self.assertEqual(result["value"], "Nanjing")
        with self.assertRaises(ValueError):
            self.m.add_alias("entity", "alice", "她")

    def test_late_effective_event_and_duplicate_ids(self):
        self.m.set("new", "s1", "x", "v", "new", effective_at=10, recorded_at=1)
        self.m.set("late", "s2", "x", "v", "old", effective_at=3, recorded_at=2)
        self.assertEqual(self.m.query(Query("x", "v", at=4))["value"], "old")
        self.assertEqual(self.m.query(Query("x", "v", at=11))["value"], "new")
        with self.assertRaises(ValueError):
            self.m.set("late", "s3", "x", "v", "duplicate", effective_at=12, recorded_at=3)

    def test_raw_fallback_never_becomes_confirmed_fact(self):
        self.m.append_raw("r1", "Alice moved to Nanjing", recorded_at=1)
        raw = self.m.search_raw("moved Nanjing")
        self.assertEqual(raw["status"], "evidence_only")
        self.assertEqual(raw["hits"][0]["id"], "r1")
        result = self.m.query(Query("Alice", "residence", at=2))
        self.assertEqual(result["state"], "absent")

    def test_json_values_are_detached_and_history_contains_all_events(self):
        value = {"cities": ["A", "B"], "active": True}
        self.m.set("e1", "s1", "x", "profile", value, effective_at=1, recorded_at=1)
        value["cities"].append("C")
        result = self.m.query(Query("x", "profile", mode="history"))
        self.assertEqual(result["value"][0]["to"], {"cities": ["A", "B"], "active": True})
        json.dumps(result, ensure_ascii=False, allow_nan=False)


class QueryRoutingTests(unittest.TestCase):
    def test_empty_slot_is_absent_and_reason_missing_is_unknown(self):
        m = ChronicleMemory()
        self.assertEqual(m.query(Query("none", "field", mode="state", at=9))["state"], "absent")
        self.assertEqual(m.query(Query("none", "field", mode="reason", event_at=1))["status"], "unknown")

    def test_same_effective_time_uses_recorded_order(self):
        m = ChronicleMemory()
        m.set("a", "s1", "x", "v", "first", effective_at=2, recorded_at=1)
        m.set("b", "s2", "x", "v", "second", effective_at=2, recorded_at=2)
        self.assertEqual(m.query(Query("x", "v", at=2))["value"], "second")


if __name__ == "__main__":
    unittest.main(verbosity=2)
