# -*- coding: utf-8 -*-
"""stab-r3 #1：id 按写入序单调 ⇒ 同分候选的断开规则可复现（版本链 h100/h50 尾序运行间不定的根因修复）。"""
import threading

from lingshu_ng.ids import new_id
from lingshu_ng.compat import SpacetimeMemoryEngine


def test_new_id_monotonic_and_shape():
    ids = [new_id("p") for _ in range(5000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert all(i.startswith("p_") and len(i) == 2 + 18 for i in ids)
    assert all(c in "0123456789abcdef" for c in ids[0][2:])


def test_new_id_threadsafe_unique():
    out, lock = [], threading.Lock()

    def work():
        mine = [new_id("t") for _ in range(2000)]
        assert mine == sorted(mine)
        with lock:
            out.extend(mine)

    ts = [threading.Thread(target=work) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(set(out)) == len(out) == 16000


def _ranked(tmp, tag):
    e = SpacetimeMemoryEngine(str(tmp / f"{tag}.db"))
    # 内容不同但对查询词频完全相同的若干段 ⇒ 词面分数相同，只靠断开规则定序
    texts = [f"项目周报 记录编号{c} 进度正常" for c in "甲乙丙丁戊己庚辛"]
    order = [e.add_perception(t) for t in texts]
    order = [n if isinstance(n, str) else n.id for n in order]
    res = e.recall("项目周报 进度正常", limit=8)
    pos = {nid: i for i, nid in enumerate(order)}
    out = [pos[n.id] for n, _ in res if n.id in pos]
    return out


def test_tie_order_reproducible_across_engines(tmp_path):
    a, b, c = (_ranked(tmp_path, t) for t in "abc")
    assert a == b == c        # 三个独立引擎、不同 id，同分段先后逐位相同
