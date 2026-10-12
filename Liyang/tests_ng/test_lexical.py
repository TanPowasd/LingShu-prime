# -*- coding: utf-8 -*-
"""gen-v1 Q10 词级通路：分词/词干、路由、长度归一、SDM、上下文聚合、暴力等价、旧库升级、配置 API、中文逐位不变。"""
import json
import os
import random
import sqlite3

import pytest

from lingshu_ng import lexical as lx
from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.retrieval import brute_force

EN = ["guitar", "piano", "concert", "ticket", "museum", "garden", "recipe", "pasta", "flight", "hotel", "camera",
      "lens", "marathon", "training", "budget", "invoice", "meeting", "project", "deadline", "puppy", "vet", "yoga",
      "the", "and", "with", "I", "my", "was", "running", "loved", "cities", "books"]


def _en(rng, k=10):
    return " ".join(rng.choice(EN) for _ in range(k)) + f" #{rng.randrange(10 ** 6)}"


# ---------------------------------------------------------------- L1
def test_tokens_split_by_script():
    t = lx.tokens("I'm running to the cities; John's guitars were loved. 我们去北京 2023")
    assert "run" in t and "city" in t and "john" in t and "guitar" in t and "lov" in t
    assert "the" not in t and "i'm" not in t                      # 停用词
    assert "我们" in t and "北京" in t and "2023" in t              # 中文字二元组、数字原样


@pytest.mark.parametrize("a,b", [("running", "runs"), ("loved", "loving"), ("cities", "city"), ("stopped", "stop"),
                                 ("recommendations", "recommend"), ("happiness", "happily")])
def test_stem_conflates(a, b):
    assert lx.stem(a) == lx.stem(b)


def test_stem_leaves_short_and_non_ascii():
    assert lx.stem("use") == "use" and lx.stem("café") == "café" and lx.stem("bus") == "bus"


def test_routing():
    c = lx.LexicalConfig()
    assert lx.is_latin_query("What guitar did I buy last week?", c)
    assert not lx.is_latin_query("猎户服务的依赖名现在是什么？", c)
    assert not lx.is_latin_query("redis 的依赖名是什么", c)       # 中文为主（含少量英文）仍走旧通路
    assert not lx.is_latin_query("%", c) and not lx.is_latin_query("the of and", c)   # 无可用词元
    assert not lx.is_latin_query("What guitar?", c.with_overrides(enabled=False))


# ---------------------------------------------------------------- L3
def test_length_normalisation_short_exact_turn_wins():
    e = MemoryEngine()
    long = ("Sure! Here are some ideas about weekend plans, hobbies, cooking, travel, music, guitar lessons. "
            + "Fitness, books and movies you might enjoy, plus podcasts and board games. " * 12)
    e.perceive(long)
    short = e.perceive("I bought a Fender guitar yesterday.").node_id
    for i in range(6):
        e.perceive(f"Unrelated chat number {i} about the weather and traffic downtown.")
    e.set_lexical(ctx_beta=0.0)                    # 只测长度归一（上下文聚合另测）
    top = e.search("Which guitar did I buy?", limit=3)
    assert top and top[0][0].id == short


def test_sdm_prefers_adjacent_phrase():
    e = MemoryEngine()
    a = e.perceive("We booked the hotel near the museum and then took a long walk in the garden.").node_id
    b = e.perceive("The museum hotel was fully booked so we stayed elsewhere, garden view though.").node_id
    for i in range(5):
        e.perceive(f"filler line {i} about pasta and recipes")
    e.set_lexical(w_t=0.5, w_o=0.5, w_u=0.0)
    r = [n.id for n, _ in e.search("museum hotel", limit=2)]
    assert r[0] == b and a in r


def test_context_lifts_neighbour_turn():
    e = MemoryEngine()
    for i in range(6):
        e.perceive(f"Filler {i}: the station near the river was busy, trains near the station delayed.")
    q = e.perceive("What was the name of the bakery you recommended near the station?").node_id
    a = e.perceive("It was called Crumb and Co, a small place near the old mill.").node_id
    for i in range(6):
        e.perceive(f"Later filler {i}: yoga training budget invoices.")

    def rank_of(nid):
        r = [n.id for n, _ in e.search("bakery recommended near the station", limit=20)]
        return r.index(nid) if nid in r else 99

    e.set_lexical(ctx_beta=0.0)
    before = rank_of(a)
    e.set_lexical(ctx_beta=0.8, ctx_span=3, ctx_decay=0.6)
    assert rank_of(q) == 0 and rank_of(a) < before


def test_window_count():
    assert lx._window_count([0, 20], [3, 30], 8) == 1
    assert lx._window_count([5], [1], 8) == 1 and lx._window_count([20], [1], 8) == 0


def test_context_aggregate():
    raw = {"a": 1.0, "b": 0.2, "c": 0.0001}
    seq = {"a": 10, "b": 11, "c": 13}
    out = lx.context_aggregate(raw, seq, 0.5, 2, 0.5)
    assert out["b"] == pytest.approx(0.2 + 0.5)
    assert out["c"] == pytest.approx(0.0001 + 0.5 * 0.5 * 0.2)
    assert lx.context_aggregate(raw, seq, 0.0, 2) is raw


# ---------------------------------------------------------------- L4：与暴力精排逐名次相同
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_search_equals_brute_force(seed):
    rng = random.Random(seed)
    e = MemoryEngine()
    for _ in range(300):
        e.perceive(_en(rng), skip_dedup=True)
    for _ in range(15):
        q = " ".join(rng.choice(EN) for _ in range(rng.randint(1, 4))) + "?"
        got = [(n.id, s) for n, s in e.search(q, limit=10)]
        want = brute_force(e.store, q, limit=10, lexical=e.lexical)
        assert e.retriever.last_plan.get("lexical") in (True, None)
        assert got == want, q


@pytest.mark.parametrize("over", [{"prf_docs": 5, "prf_terms": 8, "prf_weight": 0.3}, {"ctx_fill": 10, "ctx_span": 2},
                                  {"ctx_prev": 1.0, "ctx_next": 0.3}])
def test_options_keep_brute_force_equivalence(over):
    rng = random.Random(11)
    e = MemoryEngine()
    e.set_lexical(**over)
    for _ in range(250):
        e.perceive(_en(rng), skip_dedup=True)
    for _ in range(10):
        q = " ".join(rng.choice(EN) for _ in range(rng.randint(1, 3)))
        assert [(n.id, s) for n, s in e.search(q, limit=10)] == brute_force(e.store, q, limit=10, lexical=e.lexical), q


def test_context_direction():
    raw = {"a": 1.0, "b": 0.1, "c": 0.1}
    seq = {"a": 5, "b": 6, "c": 4}
    out = lx.context_aggregate(raw, seq, 1.0, 1, 1.0, prev=1.0, nxt=0.0)
    assert out["b"] == pytest.approx(1.1) and out["c"] == pytest.approx(0.1)


def test_recall_lexical_route_and_off_switch():
    e = MemoryEngine()
    a = e.perceive("My puppy had a vet appointment on Tuesday.").node_id
    for i in range(30):
        e.perceive(f"Long assistant style answer {i}: budgeting tips, invoices, meetings, deadlines and project plans. " * 3)
    hits = e.recall("When was the puppy's vet appointment?", limit=5)["hits"]
    assert hits[0][0].id == a and e.retriever.last_plan["lexical"] is True
    e.set_lexical(enabled=False)
    e.recall("When was the puppy's vet appointment?", limit=5)
    assert "lexical" not in e.retriever.last_plan


# ---------------------------------------------------------------- 中文逐位不变
def test_chinese_queries_unchanged_by_switch():
    rng = random.Random(5)
    words = ["记忆", "视觉", "图像", "语义", "识别", "实验", "对话", "语音", "因果", "灵枢", "协议", "redis", "max_conn"]
    e = MemoryEngine()
    for _ in range(200):
        e.perceive("".join(rng.choice(words) for _ in range(8)) + f"#{rng.randrange(10 ** 6)}", skip_dedup=True)
    qs = ["".join(rng.choice(words[:11]) for _ in range(3)) for _ in range(20)] + ["redis 的依赖名是什么", "灵枢 max_conn 现值"]
    on = [[(n.id, s) for n, s in e.retriever.search(q, limit=10, touch=False)] for q in qs]
    e.set_lexical(enabled=False)
    off = [[(n.id, s) for n, s in e.retriever.search(q, limit=10, touch=False)] for q in qs]
    assert on == off


# ---------------------------------------------------------------- 旧库升级 / 配置 API
def test_legacy_index_upgraded_on_open(tmp_path):
    p = str(tmp_path / "m.db")
    e = MemoryEngine(p)
    nid = e.perceive("The marathon training plan starts in March.").node_id
    e.store.text.flush()
    e.close()
    con = sqlite3.connect(p)          # 模拟 gen-v1 之前的库：去掉词干词元与版本标记
    con.execute("DELETE FROM index_state WHERE key='lexv'")
    con.execute("DELETE FROM node_index")
    con.execute("INSERT INTO index_dirty(node_id) SELECT id FROM nodes")
    con.commit(); con.close()
    e2 = MemoryEngine(p)
    hits = e2.search("marathon training", limit=3)
    assert hits and hits[0][0].id == nid and e2.retriever.last_plan["lexical"] is True
    assert e2.store.text.rebuild_equals()
    e2.close()


def test_config_api(monkeypatch):
    monkeypatch.setenv("LINGSHU_NG_LEXICAL", json.dumps({"b": 0.3, "bogus": 1}))
    e = MemoryEngine()
    assert e.lexical.b == 0.3
    assert e.set_lexical({"k1": 2.0}).k1 == 2.0 and e.lexical.b == lx.LexicalConfig().b
    assert e.set_lexical(None).b == 0.3                        # None ⇒ 默认 + 环境覆盖
    e2 = MemoryEngine(lexical=lx.LexicalConfig(enabled=False))
    assert e2.lexical.enabled is False
    c = SpacetimeMemoryEngine(":memory:")
    assert c.set_lexical_config(ctx_beta=0.0).ctx_beta == 0.0
    with pytest.raises(TypeError):
        e.set_lexical(3)
    monkeypatch.setenv("LINGSHU_NG_LEXICAL", "not json")
    assert lx.config_from_env() == lx.LexicalConfig()


def test_index_terms_include_words_and_rebuild_consistent():
    e = MemoryEngine()
    e.perceive("Booked flights and hotels for the Lisbon trip.")
    e.store.text.flush()
    terms = json.loads(e.store.db.scalar("SELECT terms FROM node_index LIMIT 1"))
    assert lx.WORD_PREFIX + "flight" in terms and lx.WORD_PREFIX + "lisbon" in terms
    assert e.store.text.rebuild_equals()


# ---------------------------------------------------------------- v2 库感知混合路由（route_corpus）
def _mixed_engine(tmp_path, docs):
    from lingshu_ng.compat import SpacetimeMemoryEngine
    e = SpacetimeMemoryEngine(str(tmp_path / "m.db"))
    for d in docs:
        e.add_perception(d)
    e.ng.store.text.flush()
    return e


_MQ = "Melanie 是在什么时候去参加的那个 support group 活动呢？"


def test_mixed_route_english_corpus_goes_lexical(tmp_path):
    from lingshu_ng import lexical as L
    from lingshu_ng.retrieval import corpus_cjk_share
    e = _mixed_engine(tmp_path, ["Melanie went to the LGBTQ support group yesterday.",
                                 "Caroline painted a sunrise over the lake last week.",
                                 "我今天很累。"])
    st = e.ng.store
    assert L.cjk_ratio(_MQ) >= 0.3
    assert corpus_cjk_share(st) < 0.5
    on, off = L.LexicalConfig(route_corpus=0.5), L.LexicalConfig(route_corpus=-1.0)
    assert L.LexicalConfig().route_corpus == 0.5             # v2 默认开
    assert L.mixed_route(_MQ, on, st.text.df, lambda: corpus_cjk_share(st)) is True
    assert L.mixed_route(_MQ, off, st.text.df, lambda: corpus_cjk_share(st)) is False
    e.set_lexical_config({"route_corpus": -1.0})
    assert not e.ng.retriever.routes_lexical(_MQ)          # 关 = v1 行为
    e.set_lexical_config({})
    assert e.ng.retriever.routes_lexical(_MQ)
    top = e.recall(_MQ, limit=1)
    assert top and "LGBTQ" in top[0][0].content
    e.close()


def test_mixed_route_chinese_corpus_stays_old_path(tmp_path):
    from lingshu_ng import lexical as L
    from lingshu_ng.retrieval import corpus_cjk_share
    e = _mixed_engine(tmp_path, ["我在 support group 里认识了 Melanie，聊了很久。", "今天去湖边画了日出，风很大。",
                                 "第 60 次提交：依赖名改为 redis。"])
    st = e.ng.store
    assert corpus_cjk_share(st) > 0.5
    assert L.mixed_route(_MQ, L.LexicalConfig(route_corpus=0.5), st.text.df, lambda: corpus_cjk_share(st)) is False
    e.set_lexical_config({"route_corpus": 0.5})
    assert not e.ng.retriever.routes_lexical(_MQ)
    assert not e.ng.retriever.routes_lexical("截至第 60 次提交，依赖名是什么值？")   # 纯数字不算拉丁证据
    e.close()


def test_mixed_route_pure_queries_never_read_corpus():
    from lingshu_ng import lexical as L
    cfg = L.LexicalConfig(route_corpus=0.5)
    boom = lambda *a: (_ for _ in ()).throw(AssertionError("纯中文/数字查询不应读库"))
    assert L.mixed_route("她什么时候去的互助小组？", cfg, boom, boom) is False
    assert L.mixed_route("截至第 60 次提交的值？", cfg, boom, boom) is False
    assert L.mixed_route("", cfg, boom, boom) is False


def test_corpus_cjk_share_empty_and_english(tmp_path):
    from lingshu_ng.retrieval import corpus_cjk_share
    e = _mixed_engine(tmp_path, [])
    assert corpus_cjk_share(e.ng.store) == 1.0
    e.close()
    e = _mixed_engine(tmp_path / "x", ["Only English words here, nothing else 42."]) if (tmp_path / "x").mkdir() is None else None
    assert corpus_cjk_share(e.ng.store) == 0.0
    e.close()


def test_route_corpus_no_side_effect_on_cjk_queries(tmp_path, monkeypatch):
    """v2 修复回归：纯中文查询在 route_corpus 开/关下的组合召回逐名次相同（钉住墙钟，排除 recency 抖动），
    且路由判定不 flush、不读库份额。"""
    import time as _t
    monkeypatch.setattr(_t, "time", lambda: 1.76e9)
    from lingshu_ng.compat import SpacetimeMemoryEngine
    import lingshu_ng.retrieval as R
    docs = ["派蒙接过了方案，答应下来。", "诺艾尔在蒙德城外巡逻。", "巨子拒绝了永生，留下宪法第二条。",
            "I met Melanie at the support group.", "如果派蒙没有接过方案，结局会怎样？"] * 3
    outs = []
    for i, cfg in enumerate(({"route_corpus": -1.0}, {"route_corpus": 0.5})):
        e = SpacetimeMemoryEngine(str(tmp_path / f"m{i}.db"))
        e.set_lexical_config(cfg)
        for d in docs:
            e.add_perception(d)
        outs.append([[n.content for n, _ in e.recall(q, limit=5)] for q in
                     ("如果派蒙没有接过方案会怎样？", "巨子为什么拒绝永生？", "第 2 条宪法")])
        if cfg["route_corpus"] > 0:
            calls = []
            monkeypatch.setattr(R, "corpus_cjk_share", lambda st: calls.append(1) or 1.0)
            monkeypatch.setattr(e.ng.store.text, "flush", lambda: calls.append(2) or 0)
            assert not R._route(e.ng.store, "如果派蒙没有接过方案会怎样？", e.ng.retriever.lexical)
            assert calls == []
        e.close()
    assert outs[0] == outs[1]


# ---------------------------------------------------------------- gen-v3 D1：种子扩散第二路 + RRF
def test_seed_diffusion_basic():
    act = lx.seed_diffusion({10: 2.0}, range(5, 16), span=1, decay=1.0, steps=1, alpha=0.5)
    assert act[10] == pytest.approx(0.5) and act[9] == pytest.approx(0.25) and act[11] == pytest.approx(0.25)
    assert sum(act.values()) == pytest.approx(1.0)                 # 一步后质量守恒（无孤立点）
    act2 = lx.seed_diffusion({10: 1.0}, range(5, 16), span=1, decay=1.0, steps=2, alpha=0.5)
    assert 8 in act2 and 12 in act2 and 7 not in act2               # 两步可达 ±2
    assert sum(act2.values()) == pytest.approx(1.0)
    assert lx.seed_diffusion({}, range(3), 1, 1.0, 2, 0.5) == {}
    assert lx.seed_diffusion({10: 1.0}, [10], 2, 0.6, 3, 0.5) == {10: pytest.approx(1.0)}   # 孤立种子
    # 不可参与的 rowid（层外/退役）不接收质量
    act3 = lx.seed_diffusion({10: 1.0}, [10, 11], 1, 1.0, 1, 0.5)
    assert 9 not in act3 and act3[11] == pytest.approx(0.5)


def test_rrf_fuse():
    f = lx.rrf_fuse(["a", "b"], ["b", "c"], 0.5, 10)
    assert f["a"] == pytest.approx(1 / 11) and f["b"] == pytest.approx(1 / 12 + 0.5 / 11) and f["c"] == pytest.approx(0.5 / 12)
    assert lx.rrf_fuse(["a"], ["b"], 0.0, 10) == {"a": pytest.approx(1 / 11)}


def test_diffusion_off_is_identity():
    rng = random.Random(5)
    e = MemoryEngine()
    for _ in range(120):
        e.perceive(_en(rng), skip_dedup=True)
    q = "guitar concert ticket"
    base = [(n.id, s) for n, s in e.search(q, limit=10)]
    e.set_lexical(dif_w=0.0, dif_seeds=5, dif_steps=3)             # 权重 0 ⇒ 其它扩散参数不起作用
    assert [(n.id, s) for n, s in e.search(q, limit=10)] == base


def test_diffusion_keeps_brute_force_equivalence():
    rng = random.Random(13)
    e = MemoryEngine()
    e.set_lexical(dif_w=0.7, dif_seeds=10, dif_span=2, dif_steps=2, dif_alpha=0.5, rrf_k=20)
    for _ in range(250):
        e.perceive(_en(rng), skip_dedup=True)
    for _ in range(10):
        q = " ".join(rng.choice(EN) for _ in range(rng.randint(1, 3)))
        assert [(n.id, s) for n, s in e.search(q, limit=10)] == brute_force(e.store, q, limit=10, lexical=e.lexical), q


def test_diffusion_surfaces_zero_overlap_reply():
    e = MemoryEngine()
    for i in range(30):
        e.perceive(f"Filler chat {i} about weather, traffic and lunch plans number {i}.")
    e.perceive("How long have you and your husband been married now?")
    ans = e.perceive("Five years already! Time flies.").node_id          # 与问句零词面重合
    for i in range(30):
        e.perceive(f"More filler {i}: husband cooked dinner, friends visited, {i} times.")
    e.set_lexical(ctx_beta=0.0)
    off = [n.id for n, _ in e.search("How long have Mel and her husband been married?", limit=60)]
    e.set_lexical(ctx_beta=0.0, dif_w=1.0, dif_seeds=1, dif_span=1, dif_steps=1, dif_alpha=0.5, rrf_k=10)
    on = [n.id for n, _ in e.search("How long have Mel and her husband been married?", limit=60)]
    assert ans not in off and ans in on[:10]


def test_cluster_diversify():
    sc = {"a": 1.0, "b": 0.9, "c": 0.8, "d": 0.5}
    seq = {"a": 10, "b": 11, "c": 50, "d": 12}
    out = lx.cluster_diversify(sc, seq, 2, 0.5, 60)
    assert out["a"] == 1.0 and out["b"] == pytest.approx(0.45) and out["c"] == 0.8 and out["d"] == pytest.approx(0.125)
    assert lx.cluster_diversify(sc, seq, 0, 0.5, 60) is sc
    assert lx.cluster_diversify(sc, seq, 2, 0.5, 1)["b"] == 0.9            # 只动前 top 名


def test_cluster_diversify_keeps_brute_force_equivalence():
    rng = random.Random(17)
    e = MemoryEngine()
    e.set_lexical(div_win=2, div_pen=0.6, dif_w=0.5, dif_seeds=10)
    for _ in range(250):
        e.perceive(_en(rng), skip_dedup=True)
    for _ in range(10):
        q = " ".join(rng.choice(EN) for _ in range(rng.randint(1, 3)))
        assert [(n.id, s) for n, s in e.search(q, limit=10)] == brute_force(e.store, q, limit=10, lexical=e.lexical), q


# ---------------------------------------------------------------- gen-v3 r3：C1 词元共现扩散 / C2 种子层邻轮补位（lingshu_ng.cooc）
from lingshu_ng import cooc  # noqa: E402


def test_cooc_activation_pure():
    act = cooc.activation([("s1", 0.6), ("s2", 0.4)], {"s1": [("a", 2.0), ("b", 1.0)], "s2": [("b", 1.0)]},
                          {"a": {"s1", "x"}, "b": {"s1", "s2", "x", "y"}})
    assert set(act) == {"x", "y"}                                        # 种子本身不计
    assert act["x"] == pytest.approx(0.6 * 1.0 + 0.4 * 1.0) and act["y"] == pytest.approx(0.6 / 3 + 0.4)


def test_cooc_fuse_and_gate():
    f = cooc.cooc_fuse(["a", "b"], ["c", "a"], 1.0, 10.0)
    assert f["a"] == pytest.approx(1 / 11 + 1 / 12) and f["c"] == pytest.approx(1 / 11) and f["b"] == pytest.approx(1 / 12)
    g = cooc.cooc_fuse(["a", "b"], ["c", "a"], 1.0, 10.0, gate=5)
    assert g["a"] == pytest.approx(1 / 11) and g["c"] == pytest.approx(1 / 11)   # 主前 10 名不加第二路项


def test_neighbor_slots_pure():
    sc = {"a": 1.0, "b": 0.9, "c": 0.8, "d": 0.7}
    out = cooc.neighbor_slots(["a", "b", "c", "d"], sc, {"a": ["z"], "b": ["c"]}, 2, 2)
    order = sorted(out, key=lambda n: -out[n])
    assert order == ["a", "b", "z", "c", "d"] and out["a"] == 1.0 and out["d"] == 0.7


def test_cooc_off_is_identity():
    rng = random.Random(23)
    e = MemoryEngine()
    for _ in range(120):
        e.perceive(_en(rng), skip_dedup=True)
    q = "guitar concert ticket"
    e.set_lexical(co_w=0.0)
    base = [(n.id, s) for n, s in e.search(q, limit=10)]
    e.set_lexical(co_w=0.0, co_seeds=3, nb_s0=0, nb_m=3)                 # 权重 0 / s0 = 0 ⇒ 其它参数不起作用
    assert [(n.id, s) for n, s in e.search(q, limit=10)] == base


def test_cooc_keeps_brute_force_equivalence():
    rng = random.Random(29)
    e = MemoryEngine()
    e.set_lexical(co_w=0.6, co_seeds=10, co_terms=5, co_dfmax=0.2, co_k=10, nb_s0=6, nb_m=2, nb_prev=True)
    for _ in range(250):
        e.perceive(_en(rng), skip_dedup=True)
    for _ in range(10):
        q = " ".join(rng.choice(EN) for _ in range(rng.randint(1, 3)))
        assert [(n.id, s) for n, s in e.search(q, limit=10)] == brute_force(e.store, q, limit=10, lexical=e.lexical), q


def test_cooc_surfaces_far_turn_sharing_rare_term():
    e = MemoryEngine()
    e.perceive("Maria: My aunt Rosalind helped us when money was tight.")
    for i in range(40):
        e.perceive(f"Filler chat {i} about weather, traffic and lunch plans number {i}.")
    far = e.perceive("Rosalind also taught me to volunteer at the shelter.").node_id   # 与问句零词面重合
    q = "Who helped Maria's family with money?"
    e.set_lexical(ctx_beta=0.0, co_w=0.0)
    off = [n.id for n, _ in e.search(q, limit=60)]
    e.set_lexical(ctx_beta=0.0, co_w=1.0, co_seeds=1, co_terms=3, co_dfmax=0.5, co_k=10)
    on = [n.id for n, _ in e.search(q, limit=60)]
    assert far not in off and far in on[:2]


def test_neighbor_slot_surfaces_zero_overlap_reply():
    e = MemoryEngine()
    for i in range(30):
        e.perceive(f"Filler chat {i} about weather, traffic and lunch plans number {i}.")
    e.perceive("How long have you and your husband been married now?")
    ans = e.perceive("Five years already! Time flies.").node_id
    for i in range(30):
        e.perceive(f"More filler {i}: husband cooked dinner, friends visited, {i} times.")
    e.set_lexical(ctx_beta=0.0)
    off = [n.id for n, _ in e.search("How long have Mel and her husband been married?", limit=60)]
    e.set_lexical(ctx_beta=0.0, nb_s0=1, nb_m=1)
    on = [n.id for n, _ in e.search("How long have Mel and her husband been married?", limit=60)]
    assert ans not in off and on[1] == ans


# ---------------------------------------------------------------- gen-v3 r4：E1 头部保护 / E2 门限启用（PREREG_GEN_v3 修订 4）
def test_cooc_head_protection_pure():
    f = cooc.cooc_fuse(["a", "b", "c", "d"], ["x", "c"], 1.0, 10.0, head=2)
    order = sorted(f, key=lambda n: (-f[n], n))
    assert order[:2] == ["a", "b"]                                       # 前 2 名原样居前
    assert order[2:] == ["c", "x", "d"] and f["b"] > f["c"]              # 其余按融合分（c 两路都有），分数单调
    g = cooc.cooc_fuse(["a", "b", "c", "d"], ["x", "c"], 1.0, 10.0)
    assert sorted(g, key=lambda n: (-g[n], n))[0] == "c"                 # 无保护时第二路可把 c 推过头部


def test_cooc_gates_pure():
    cfg = lx.LexicalConfig().with_overrides(co_qtype=True)
    main = list("abcdef")
    raw = {n: 1.0 for n in main}
    assert cooc.gated(main, raw, cfg, "How many hours did I practise piano last week?")
    assert cooc.gated(main, raw, cfg, "When did I move to Denver?")
    assert not cooc.gated(main, raw, cfg, "What is my favourite guitar brand?")
    c2 = lx.LexicalConfig().with_overrides(co_conf=1.3)
    assert not cooc.gated(main, raw, c2, "x")                            # 头部不集中 ⇒ 启用
    assert cooc.gated(main, dict(raw, a=2.0), c2, "x")                   # 第 1/第 6 名 = 2 ≥ 1.3 ⇒ 跳过
    assert cooc.gated(main[:4], raw, c2, "x")                            # 不足 6 名 ⇒ 跳过
    assert not cooc.gated(main, dict(raw, a=9.0), lx.LexicalConfig(), "when")   # 默认全关
    c3 = lx.LexicalConfig().with_overrides(co_qtype=2)                  # 窄版只看计数/汇总
    assert cooc.gated(main, raw, c3, "How much did I spend on gifts in total?")
    assert not cooc.gated(main, raw, c3, "When did I move to Denver?")


def test_cooc_r4_off_is_v3():
    rng = random.Random(31)
    e = MemoryEngine()
    for _ in range(150):
        e.perceive(_en(rng), skip_dedup=True)
    assert e.set_lexical().co_head == 0 and e.set_lexical().co_w == 0.3     # 默认 = v3（v3.1 未通过判定）
    for q in ("guitar concert ticket", "when did the band play"):
        e.set_lexical()                                                     # 默认 = v3
        base = [(n.id, s) for n, s in e.search(q, limit=10)]
        e.set_lexical(co_w=0.3, co_head=0, co_conf=0.0, co_qtype=0)        # r4 门限关 ⇒ 不起作用
        assert [(n.id, s) for n, s in e.search(q, limit=10)] == base


def test_cooc_r4_keeps_brute_force_equivalence():
    rng = random.Random(37)
    e = MemoryEngine()
    e.set_lexical(co_w=0.5, co_head=3, co_conf=1.2, co_qtype=True)
    for _ in range(250):
        e.perceive(_en(rng), skip_dedup=True)
    for _ in range(10):
        q = " ".join(rng.choice(EN) for _ in range(rng.randint(1, 3)))
        assert [(n.id, s) for n, s in e.search(q, limit=10)] == brute_force(e.store, q, limit=10, lexical=e.lexical), q
