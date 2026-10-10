# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import rrf3 as R  # noqa: E402


def mem(turns):
    m = R.RRF3Memory()
    for role, t in turns:
        m.add_turn(role, t)
    return m


def test_empty():
    m = R.RRF3Memory()
    assert m.rank("任何") == [] and m.retrieve("任何") == [] and m.context("x") == ""


def test_chunking_and_edges():
    long = "\n".join("第%d行" % k + "字" * 60 for k in range(12))
    m = mem([("user", "你好"), ("ai", long)])
    assert m.N >= 3
    assert m.out[0][1] == R.W_QA and m.out[1][0] == R.W_BWD
    assert m.out[1][2] == R.W_FWD and m.out[2][1] == R.W_BWD
    assert all(s >= R.CHUNK for s in m.size[1:-1])


def test_bm25_finds_rare_term():
    turns = [("user", "今天天气%d" % k) for k in range(40)] + [("ai", "蜂巢世界的巨子塔")] + \
            [("user", "闲聊%d" % k) for k in range(40)]
    m = mem(turns)
    sc = m.bm25("巨子塔在哪")
    assert max(sc, key=sc.get) == 40


def test_agm_pulls_neighbor_of_seed():
    turns = [("user", "填充内容%d号" % k) for k in range(30)]
    turns += [("user", "巨子塔是什么"), ("ai", "那是陈默出生的地方")]
    turns += [("user", "别的话题%d号" % k) for k in range(30)]
    m = mem(turns)
    o = m.rank_agm(m.bm25("巨子塔"))
    assert o[:2] == [30, 31]          # 种子 + 问答邻接的回答块


def test_rrf_mixes_recent_and_relevant():
    turns = [("user", "填充内容%d号" % k) for k in range(30)] + [("ai", "关键线索是青铜钥匙")] + \
            [("user", "别的话题%d号" % k) for k in range(30)]
    m = mem(turns)
    ids = [h.id for h in m.retrieve("青铜钥匙", budget=60)]
    assert 30 in ids and m.N - 1 in ids


def test_budget_first_chunk_always():
    m = mem([("ai", "字" * 900)])
    hits = m.retrieve("字字", budget=10)
    assert len(hits) == 1


def test_context_chronological():
    m = mem([("user", "甲乙丙丁"), ("ai", "戊己庚辛"), ("user", "甲乙")])
    c = m.context("甲乙", budget=100)
    assert c.index("甲乙丙丁") < c.index("戊己庚辛")


def test_v11_versioned_subject_recall():
    """v1.1 回归：同一主体每段都出现主体名/槽位名时，v1.0 截断把它们全跳过；v1.1 应能召回该主体的段。"""
    m = R.RRF3Memory()
    old = R.RRF3Memory(df_cap=R.BM25_DF_CAP_V10)
    for k in range(40):
        for mem in (m, old):
            mem.add_turn("doc", f"第{k}次提交。甲项目的依赖名调整为v{k}。")
            mem.add_turn("doc", f"无关记录{k}号，天气晴，会议照常。")
    q = "甲项目的依赖名当前是什么"
    assert all("甲项目" in h.text for h in m.retrieve(q, budget=200))
    assert not old.bm25(q)          # v1.0：所有查询二元组都超 df 截断，BM25 全零
