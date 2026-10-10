import math, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chronicle_dm import ChronicleDM


def build():
    m = ChronicleDM()
    m.record("e1", "猎户", "依赖", "set", value="bbolt", effective_at=1, recorded_at=1,
             reason="安全审计", quote="猎户 的依赖名调整为 bbolt，起因是安全审计要求")
    m.record("e2", "猎户", "依赖", "set", value="rocksdb", effective_at=2, recorded_at=2, reason="性能")
    m.record("e3", "猎户", "依赖", "retire", effective_at=3, recorded_at=3, reason="下线")
    m.record("e4", "猎户", "依赖", "unresolved", value="a", alternative="b", effective_at=4, recorded_at=4)
    m.record("e5", "猎户", "依赖", "resolve", value="a", effective_at=5, recorded_at=5, reason="评审裁定")
    return m


class T(unittest.TestCase):
    def test_four_states_and_agreement(self):
        m = build()
        cases = {0.5: ("absent", None), 1: ("active", "bbolt"), 2.5: ("active", "rocksdb"),
                 3: ("retired", None), 4: ("unresolved", "a"), 6: ("active", "a")}
        for t, (st, v) in cases.items():
            r = m.ask("猎户", "依赖", at=t)
            self.assertEqual((r["state"], r["value"]), (st, v), t)
            self.assertTrue(r["agree"], t)

    def test_retired_vs_absent_distinguished(self):
        m = build()
        self.assertEqual(m.ask("猎户", "依赖", at=3)["state"], "retired")
        self.assertEqual(m.ask("猎户", "依赖", at=0.5)["state"], "absent")
        self.assertEqual(m.ask("别的", "槽", at=3)["state"], "absent")

    def test_chain_and_history(self):
        m = build()
        r = m.ask("猎户", "依赖", "chain", at=10)
        self.assertEqual([(x["from"], x["to"]) for x in r["chain"]],
                         [(None, "bbolt"), ("bbolt", "rocksdb"), ("rocksdb", None), (None, "a"), ("a", "a")])
        self.assertEqual(r["memory"]["h"]["status"], "history")

    def test_reason(self):
        m = build()
        self.assertEqual(m.ask("猎户", "依赖", "reason", at=10, event_at=2)["reason"], "性能")
        self.assertEqual(m.ask("猎户", "依赖", "reason", at=10, event_at=5)["reason"], "评审裁定")

    def test_memory_evidence_carries_quote_and_reason(self):
        m = build()
        r = m.ask("猎户", "依赖", at=1)
        self.assertIn("安全审计", r["sources"][0]["text"])

    def test_rejects_bad_writes_atomically(self):
        m = build()
        with self.assertRaises(ValueError):
            m.record("e1", "猎户", "依赖", "set", value="x", effective_at=9, recorded_at=9)
        with self.assertRaises(ValueError):
            m.record("e9", "猎户", "依赖", "set", effective_at=9, recorded_at=9)
        with self.assertRaises(ValueError):   # 记录时钟倒退：Memory 拒收，编年也不落
            m.record("e9", "猎户", "依赖", "set", value="x", effective_at=9, recorded_at=0)
        self.assertNotIn("e9", m.timeline._events)

    def test_alias(self):
        m = ChronicleDM()
        m.add_alias("entity", "猎户项目", "猎户")
        m.record("e1", "猎户项目", "依赖", "set", value="x", effective_at=1, recorded_at=1)
        self.assertEqual(m.ask("猎户", "依赖")["value"], "x")
        self.assertTrue(m.ask("猎户", "依赖")["agree"])

    def test_render(self):
        m = build()
        text = m.render(m.ask("猎户", "依赖", "chain", at=10))
        self.assertIn("rocksdb", text)
        self.assertIn("缘由：性能", text)

    def test_raw_search(self):
        m = ChronicleDM()
        m.append_raw("r1", "上游接口刚调整过", recorded_at=1)
        self.assertEqual([h["id"] for h in m.search_raw("接口调整")["hits"]], ["r1"])


if __name__ == "__main__":
    unittest.main()
