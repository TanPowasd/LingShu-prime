"""stab-r10：近重复候选拆到 store/neardup.py 并降常数后，与 rel-v1.25 实现（tests_ng/ndc_ref_v125.py）及全层暴力比对逐值相同；
倒排数组读（postings.read_arrays）与逐块解码相同（含宽编码块）。"""
import array
import random

import pytest

from lingshu_ng import dedup
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.store import neardup, postings
from tests_ng.ndc_ref_v125 import ndc_v125


def _texts(n, seed, long_every=0):
    rng = random.Random(seed)
    pool = "的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处理"
    out = []
    for i in range(n):
        if long_every and i % long_every == 0:
            out.append("".join(rng.choice(pool) for _ in range(rng.randrange(150, 400))))
            continue
        base = "".join(rng.choice(pool[:60]) for _ in range(rng.randrange(8, 40)))
        out.append(base)
        if rng.random() < .3 and out:
            t = rng.choice(out)
            j = rng.randrange(len(t))
            out.append(t[:j] + rng.choice(pool) + t[j + 1:])
    return out


def _brute(e, grams, t):
    rows = e.store.db.all("SELECT n.id, n.content FROM nodes n JOIN node_index ni ON ni.node_id = n.id")
    return {nid for nid, c in rows if dedup.jaccard(grams, dedup.bigrams(c or "")) >= t}


@pytest.mark.parametrize("t,long_every", [(0.3, 5), (0.5, 0), (0.6, 7), (0.8, 0), (0.9, 3), (1.0, 0)])
def test_same_as_v125_and_bruteforce(t, long_every):
    e = MemoryEngine(":memory:")
    try:
        for s in _texts(500, 5, long_every):
            e.perceive(s, skip_dedup=True)
        ti = e.store.text
        ti.flush()
        for q in _texts(80, 9, long_every):
            g = dedup.bigrams(q)
            got = ti.near_duplicate_candidates(g, t)
            assert got == ndc_v125(ti, g, t), (q, t)
            assert got == _brute(e, g, t), (q, t)
    finally:
        e.close()


def test_select_matches_table():
    rng = random.Random(3)
    gs = array.array("H", [rng.choice([0, 1, 255, 256, 257, 511, 65535] + list(range(2, 300))) for _ in range(5000)])
    for lo, hi in [(0, 0), (1, 1), (10, 40), (40, 255), (200, 300), (0, 65535), (300, 299)]:
        tbl = neardup._mask(lo, hi)
        want = [1 if (g == 0 or lo <= g <= hi) else 0 for g in gs]
        assert list(neardup._select(gs, lo, hi, tbl)) == want


def test_read_arrays_same_as_blocks():
    e = MemoryEngine(":memory:")
    try:
        c = e.store.db.conn
        rows = [("x", 1, [1, 5, 9], [3, 0, 70000]), ("x", 10, [10, 1 << 33], [2, 4]), ("y", 2, [2, 3], [1, 2])]
        for t, bno, ks, gs in rows:
            c.execute(postings._PUT, (t, bno) + postings.encode(ks, gs))
        for t in ("x", "y", "z"):
            ks, gs = postings.read_arrays(c, t)
            want = [(k, g) for tt, _, kk, gg in rows if tt == t for k, g in zip(kk, gg)]
            assert list(zip(ks, gs)) == want
            assert postings.read(c, t) == ([k for k, _ in want], [g for _, g in want])
    finally:
        e.close()


def _blocks(c):
    return c.execute("SELECT term, bno, n, nk, gr FROM term_blocks ORDER BY term, bno").fetchall()


@pytest.mark.parametrize("seed", range(6))
def test_remove_same_as_v125(seed):
    """随机倒排（多块、小块、宽编码）上随机删除：新 remove 与 v1.25 实现写出的块逐字节相同、返回条数相同。"""
    from tests_ng.postings_ref_v125 import remove_v125
    rng = random.Random(seed)
    dbs = [MemoryEngine(":memory:"), MemoryEngine(":memory:")]
    try:
        terms = [f"t{i}" for i in range(12)]
        ents = {t: sorted(rng.sample(range(1, 3000), rng.randrange(1, 500))) for t in terms}
        if seed % 2:
            ents["t0"] = ents["t0"] + [1 << 33]
        for e in dbs:
            c = e.store.db.conn
            rng_l = random.Random(seed + 100)
            for t, ks in ents.items():
                i = 0
                while i < len(ks):                       # 块长随机（5–128）：造出可并入前一块的小块
                    ch = ks[i:i + rng_l.randrange(5, 129)]
                    i += len(ch)
                    gs = [70000 if (seed % 3 == 0 and k % 97 == 0) else k % 300 for k in ch]
                    c.execute(postings._PUT, (t, ch[0]) + postings.encode(ch, gs))
        for _ in range(25):
            by = {}
            for t in rng.sample(terms, rng.randrange(1, len(terms))):
                pool = ents[t] + [rng.randrange(1, 3000)]
                by[t] = set(rng.sample(pool, min(len(pool), rng.choice([1, 1, 2, 5, 40, 200]))))
            c0, c1 = dbs[0].store.db.conn, dbs[1].store.db.conn
            c0.execute("BEGIN"); c1.execute("BEGIN")
            r0 = postings.remove(c0, by)
            r1 = remove_v125(c1, by)
            c0.execute("COMMIT"); c1.execute("COMMIT")
            assert r0 == r1
            assert _blocks(c0) == _blocks(c1)
            for t, ks in by.items():
                ents[t] = [k for k in ents[t] if k not in ks]
        assert postings.check(dbs[0].store.db.conn)
    finally:
        for e in dbs:
            e.close()
