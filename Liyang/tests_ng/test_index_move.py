# -*- coding: utf-8 -*-
"""stab-r5（schema v4）：单节点重建的原位差量路径（``trg_index_upd`` + ``TextIndex._move_row``）
与旧的「删旧行 + 插新行」逐值相同——node_index（含 nkey 分配）、倒排（v5 解码后的倒排块）、term_df、feature_df 全表相等。"""
import json
import random

from lingshu_ng.engine import MemoryEngine
from lingshu_ng.layers import LayerViolation
from lingshu_ng.store import postings
from lingshu_ng.store.textindex import TextIndex
from lingshu_ng.types import MemoryLayer

WORDS = ["记忆", "视觉", "图像", "语义", "识别", "灵枢", "协议", "robot", "Memory", "graph", "running", "v2.1"]


def _dump(e):
    c = e.store.conn
    out = {t: [tuple(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()]
           for t in ("term_df", "feature_df")}
    # v5：倒排块的切分随历史而异，比较解码后的 (词元, nkey, grams) 全量（与 v4 node_terms 行逐条对应）
    out["postings"] = sorted((t, k, g) for t, v in postings.all_postings(c).items() for k, g in v)
    # 节点 id 含时间戳、两次运行不同：换成 nodes.rowid（同一操作序列下确定）
    out["node_index"] = [tuple(r) for r in c.execute(
        "SELECT ni.nkey, n.rowid, ni.feats, ni.grams FROM node_index ni JOIN nodes n ON n.id = ni.node_id "
        "ORDER BY 1").fetchall()]
    assert len(out["node_index"]) == c.execute("SELECT COUNT(*) FROM node_index").fetchone()[0]
    return out


def _script(e, seed, feats=True):
    rng = random.Random(seed)
    s = lambda: "".join(rng.choice(WORDS) for _ in range(rng.randrange(1, 9))) + f"#{rng.randrange(50)}"
    ids = [e.perceive(s(), tags=[rng.choice(WORDS)], skip_dedup=True).node_id for _ in range(60)]
    e.recall("记忆 robot", limit=5)                        # 派生索引就绪、新奇特征按需构建
    if feats:
        e.store.text.ensure_feats()
    for step in range(120):
        nid = rng.choice(ids)
        op = rng.randrange(6)
        if e.store.nodes.get(nid) is None:
            continue
        if op == 0:
            e.store.nodes.update(nid, content=s())
        elif op == 1:
            e.store.nodes.add_tags(nid, [rng.choice(WORDS), f"t{rng.randrange(5)}"])
        elif op == 2:
            n = e.store.nodes.get(nid)
            e.store.nodes.remove_tags(nid, n.tags[:1])
        elif op == 3:
            try:
                e.store.nodes.update(nid, allow_transition=True,
                                     layer=rng.choice([MemoryLayer.CONTEXT, MemoryLayer.KNOWLEDGE, MemoryLayer.STRUCTURE]))
            except LayerViolation:
                pass
        elif op == 4:
            ids.append(e.perceive(s(), skip_dedup=True).node_id)
        else:
            e.store.nodes.update(nid, content=e.store.nodes.get(nid).content)   # 内容不变的重写
        if step % 17 == 0:
            e.recall(rng.choice(WORDS), limit=5)
    e.store.text.flush()
    return _dump(e)


def test_move_row_equals_delete_insert(monkeypatch):
    for seed, feats in ((1, True), (2, True), (3, False), (4, False)):
        a = MemoryEngine()
        fast = _script(a, seed, feats)
        assert a.store.text.rebuild_equals()
        a.close()
        with monkeypatch.context() as m:
            m.setattr(TextIndex, "_move_row", staticmethod(lambda c, row: False))
            b = MemoryEngine()
            slow = _script(b, seed, feats)
            b.close()
        assert fast == slow


def test_move_row_used_for_single_update():
    e = MemoryEngine()
    nid = e.perceive("灵枢 协议 记忆", skip_dedup=True).node_id
    e.perceive("别的 节点", skip_dedup=True)
    e.recall("灵枢", limit=3)
    calls = []
    orig = TextIndex._move_row
    TextIndex._move_row = staticmethod(lambda c, row: calls.append(row[0]) or orig(c, row))
    try:
        e.store.nodes.add_tags(nid, ["新标签"])
    finally:
        TextIndex._move_row = staticmethod(orig)
    assert calls == [nid]
    assert e.store.text.rebuild_equals()
    k = e.store.conn.execute("SELECT nkey FROM node_index WHERE node_id=?", (nid,)).fetchone()[0]
    assert k in e.store.text.postings("\x1f新标签")
    e.close()
