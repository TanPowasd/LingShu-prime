"""stab-r5 规模修复的等价性守护：近重复候选（store.textindex.near_duplicate_candidates）。

新算法（前缀 + 逐步校验 + 剪枝）必须恰好等于「全层逐条算 Jaccard ≥ t」的集合，
且写入路径的去重结果与旧算法（_ndc_prefix）逐条相同。"""
import random

import pytest

from lingshu_ng import dedup
from lingshu_ng.engine import MemoryEngine


def _corpus(n, seed=7):
    rng = random.Random(seed)
    base = ["项目青鸾的周会改到周四下午三点", "Atlas meeting moved to Thursday 3pm in room 204",
            "张三负责白鹭项目的预算审批，截止日期是十月底", "the quarterly report is due next Friday",
            "李四说朱雀系统的数据库迁移推迟到下周", "remember to buy oat milk and eggs"]
    out = []
    for i in range(n):
        t = rng.choice(base)
        k = rng.randrange(4)
        if k == 0:
            t = t + str(rng.randrange(100))
        elif k == 1:
            j = rng.randrange(len(t))
            t = t[:j] + t[j + 1:]
        elif k == 2:
            t = t + "".join(rng.choice("的一是在不了有和人这中大为上个国我以要他时来用们") for _ in range(rng.randrange(1, 6)))
        out.append(t)
    return out


def _brute(e, grams, t):
    rows = e.store.db.all("SELECT n.id, n.content FROM nodes n JOIN node_index ni ON ni.node_id = n.id")
    return {nid for nid, c in rows if dedup.jaccard(grams, dedup.bigrams(c or "")) >= t}


@pytest.mark.parametrize("t", [0.5, 0.7, 0.85, 1.0])
def test_candidates_equal_bruteforce(t):
    e = MemoryEngine(":memory:")
    try:
        for s in _corpus(300):
            e.perceive(s, skip_dedup=True)
        e.store.text.flush()
        for q in _corpus(60, seed=11):
            g = dedup.bigrams(q)
            got = e.store.text.near_duplicate_candidates(g, t)
            want = _brute(e, g, t)
            assert got == want, (q, t)
            assert want <= e.store.text._ndc_prefix(g, t)     # 旧算法也是超集
    finally:
        e.close()


def test_write_path_same_as_prefix_algorithm(monkeypatch):
    seqs = []
    for use_old in (False, True):
        e = MemoryEngine(":memory:")
        if use_old:
            ti = e.store.text
            monkeypatch.setattr(ti, "near_duplicate_candidates", ti._ndc_prefix)
        idx, seq = {}, []
        try:
            for i, s in enumerate(_corpus(400, seed=3)):
                w = e.perceive(s)
                if w.action == "created":
                    idx[w.node_id] = i
                seq.append((w.action, idx.get(w.node_id)))
        finally:
            e.close()
        seqs.append(seq)
    assert seqs[0] == seqs[1]
    assert any(a == "merged" for a, _ in seqs[0])
