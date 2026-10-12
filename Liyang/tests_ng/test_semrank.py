# -*- coding: utf-8 -*-
"""zh-v1 v7：SR 语义重排 + 自适应截断（lingshu_ng.assoc._semantic / lingshu_ng.semrank）。
可选依赖缺失 → 逐位退回 v4；交付默认 = v7（模型存在时）；只在无序语料（连贯度 < sem_coh）的长请求上生效；短请求不经过。"""
import pytest

from lingshu_ng import assoc as ax
from lingshu_ng import semrank
from lingshu_ng.engine import MemoryEngine

WEB = [
    "丰巢快递柜取件码忘了，可以在丰巢微信公众号里查看取件码。",
    "西红柿炒鸡蛋要先炒鸡蛋，盛出后再炒西红柿。",
    "笔记本电脑电池鼓包要立刻停止使用，送售后更换。",
    "快递柜的取件码也会通过短信发送，短信删了可以联系快递员重发。",
    "红烧肉先焯水去血沫，再小火慢炖一小时。",
    "手机充电很慢，可能是数据线老化或者充电头功率不够。",
    "丰巢柜子超时取件会收取保管费，会员可以免费延长。",
    "台风天出门注意远离广告牌和临时搭建物。",
]


class _Stub:
    """假打分件：含「取件码」的段落高分，其余低分。"""

    def __init__(self):
        self.calls = 0

    def score(self, q, passages, batch=16):
        self.calls += 1
        return [5.0 if "取件码" in p else (-1.0 if "丰巢" in p else -9.0) for p in passages]


#: v7.1 的稠密补入开关（交付缺省自 v11c 起改为补入开；以下 v8/v10/v11 单测以 v7.1 为基线显式关闭）
V71 = dict(sem_dense=0, sem_dense_m=0, sem_dense_cap=0, sem_dense_tau=-99.0)


def _eng(tmp_path, docs=WEB, **cfg):
    e = MemoryEngine(str(tmp_path / "m.db"))
    for d in docs:
        e.perceive(d)
    e.retriever.assoc = ax.AssocConfig(**cfg) if cfg else ax.AssocConfig()
    return e


def _ids(e, q, k):
    return [n.content for n, _ in e.retriever.recall(q, k)]


def test_default_v7():
    """交付默认 = v7.1（PREREG_ZH 修订 5.3 / 5b；REPORT_ZH_v1 §11）：TP 头 5 + SR（N 40、τ −3.25、至少 3 条、TP 与 LC 通路），短请求不经过。"""
    c = ax.AssocConfig()
    assert (c.tp_head, c.sem_n, c.sem_tau, c.sem_min, c.sem_paths, c.sem_v4fb) == (5, 40, -3.25, 3, "tp,lc", 1)
    assert c.sem_short == 0 and c.sem_coh == 1.0 and c.sem_lam == 0.0 and c.sem_tail == 0 and c.sem_chain == 1


def test_default_v11c():
    """交付默认 = v11c（PREREG_ZH 修订 9b 冻结 / 9c 判定）：v7.1 + 自适应稠密补入 20、m 5、cap 2、τd 0。"""
    c = ax.AssocConfig()
    assert (c.sem_dense, c.sem_dense_m, c.sem_dense_cap, c.sem_dense_tau, c.sem_fuse) == (20, 5, 2, 0.0, 0.0)


def test_default_without_embedder_is_v71(tmp_path, monkeypatch):
    """稠密件不可用 ⇒ 交付默认与 v7.1（稠密补入关）逐位相同。"""
    monkeypatch.setattr(semrank, "get_scorer", lambda: _Stub())
    monkeypatch.setattr(semrank, "get_embedder", lambda: None)
    for lh in (2, 15):
        _same(_eng(tmp_path / str(lh)), dict(lc_head=lh, tp_coh=0.0), dict(V71, lc_head=lh, tp_coh=0.0),
              (("丰巢取件码忘了怎么办", 8), ("红烧肉怎么做", 6), ("取件码", 2)))


def test_default_without_scorer_is_v4(tmp_path, monkeypatch):
    """打分件不可用 ⇒ 交付默认与 v4（tp_head 0、sem_n 0）逐位相同（长、短请求都是）。"""
    monkeypatch.setattr(semrank, "get_scorer", lambda: None)
    for lh in (2, 15):
        _same(_eng(tmp_path / str(lh)), dict(lc_head=lh, tp_coh=0.0), dict(lc_head=lh, tp_coh=0.0, tp_head=0, sem_n=0),
              (("丰巢取件码忘了怎么办", 8), ("红烧肉怎么做", 6), ("取件码", 2)))


def test_get_scorer_off_or_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("LINGSHU_NG_SEM", "off")
    semrank._SCORERS.clear()
    assert semrank.get_scorer() is None
    monkeypatch.setenv("LINGSHU_NG_SEM", str(tmp_path / "nope"))
    semrank._SCORERS.clear()
    assert semrank.get_scorer() is None
    semrank._SCORERS.clear()


def test_missing_scorer_is_bitwise_fallback(tmp_path, monkeypatch):
    """打分件不可用（缺依赖 / 缺模型）且不退回 v4（sem_v4fb 0）⇒ sem_n > 0 与 sem_n = 0 逐位相同。"""
    monkeypatch.setattr(semrank, "get_scorer", lambda: None)
    base = dict(tp_head=1, tp_coh=0.0, lc_head=2, sem_v4fb=0)
    _same(_eng(tmp_path), base, dict(base, sem_n=40, sem_tau=0.0, sem_paths="tp,lc", sem_short=1),
          (("丰巢取件码忘了怎么办", 8), ("红烧肉怎么做", 6), ("取件码", 2)))


def e_rows(e, q, k):
    return [(n.content, s) for n, s in e.retriever.recall(q, k)]


def _same(e, cfg_a, cfg_b, qs):
    """同一引擎上切换配置比较（避免两库节点 id 不同导致同分序不同）。"""
    for q, k in qs:
        e.retriever.assoc = ax.AssocConfig(**cfg_a); x = e_rows(e, q, k)
        e.retriever.assoc = ax.AssocConfig(**cfg_b); y = e_rows(e, q, k)
        assert x == y, (q, k)


def test_semantic_reorders_and_truncates_long_requests(tmp_path, monkeypatch):
    st = _Stub()
    monkeypatch.setattr(semrank, "get_scorer", lambda: st)
    on = _eng(tmp_path / "on", tp_head=1, tp_coh=0.0, lc_head=2, sem_n=40, sem_tau=0.0, sem_min=1)
    got = _ids(on, "丰巢取件码忘了怎么办", 8)
    assert st.calls >= 1
    assert got and all("取件码" in g for g in got)          # 截断：低于阈值的不返回（上下文不填满）
    sc = [s for _, s in on.retriever.recall("丰巢取件码忘了怎么办", 8)]
    assert all(a >= b for a, b in zip(sc, sc[1:]))
    tail = _eng(tmp_path / "tail", tp_head=1, tp_coh=0.0, lc_head=2, sem_n=40, sem_tail=1)
    got2 = _ids(tail, "丰巢取件码忘了怎么办", 8)
    assert len(got2) > len(got) and all("取件码" in g for g in got2[:len(got)])


def test_semantic_min_keep(tmp_path, monkeypatch):
    monkeypatch.setattr(semrank, "get_scorer", lambda: _Stub())
    on = _eng(tmp_path / "on", tp_head=1, tp_coh=0.0, lc_head=2, sem_n=40, sem_tau=99.0, sem_min=3)
    assert len(_ids(on, "丰巢取件码忘了怎么办", 8)) == 3


def test_short_requests_untouched_by_default(tmp_path, monkeypatch):
    st = _Stub()
    monkeypatch.setattr(semrank, "get_scorer", lambda: st)
    _same(_eng(tmp_path), dict(lc_head=5), dict(lc_head=5, sem_n=40, sem_tau=0.0, sem_paths="tp,lc"),
          (("丰巢取件码忘了怎么办", 5), ("西红柿炒鸡蛋", 5)))
    assert st.calls == 0


def test_coherent_corpus_skips_semantic_on_lc(tmp_path, monkeypatch):
    """写入序连贯（连贯度 ≥ sem_coh）的长请求走 LC 且不经过 SR。"""
    st = _Stub()
    monkeypatch.setattr(semrank, "get_scorer", lambda: st)
    _same(_eng(tmp_path), dict(lc_head=2, tp_head=0, sem_n=0), dict(lc_head=2, tp_head=0, sem_n=40, sem_tau=0.0, sem_paths="tp,lc", sem_coh=-1.0),
          (("丰巢取件码忘了怎么办", 8), ("红烧肉", 8)))
    assert st.calls == 0


@pytest.mark.skipif(semrank.get_scorer() is None, reason="可选语义模型未安装")
def test_real_scorer_smoke():
    sc = semrank.get_scorer()
    v = sc.score("丰巢取件码忘了怎么办", ["丰巢快递柜取件码忘了，可以在丰巢微信公众号里查看取件码。", "台风天出门注意远离广告牌。"])
    assert v[0] > v[1]


def test_chain_intent_lexicon():
    """v7.1：链式请求识别（纯词面）。"""
    assert semrank.chain_intent("猎户项目 的配置值从最初到现在经历过哪些变更？请按序号顺序列出每一次变更前后的值。")
    assert semrank.chain_intent("老陈的立场经历了哪些变化")
    assert semrank.chain_intent("公司名称的历次变更")
    assert not semrank.chain_intent("丰巢取件码忘了怎么办")
    assert not semrank.chain_intent("艾佛森安东尼历史地位")
    assert not semrank.chain_intent("")


def test_chain_requests_exempt_from_truncation(tmp_path, monkeypatch):
    """v7.1：链式请求只重排不截断（取回条数同 sem_tail）；sem_chain=0 时照旧截断。"""
    monkeypatch.setattr(semrank, "get_scorer", lambda: _Stub())
    kw = dict(tp_head=1, tp_coh=0.0, lc_head=2, sem_n=40, sem_tau=99.0, sem_min=1)
    q = "丰巢取件码从最初到现在经历过哪些变更"
    on = _eng(tmp_path / "on", **kw)
    off = _eng(tmp_path / "off", sem_chain=0, **kw)
    tail = _eng(tmp_path / "tail", sem_tail=1, **kw)
    assert len(_ids(off, q, 8)) == 1
    assert _ids(on, q, 8) == _ids(tail, q, 8) and len(_ids(on, q, 8)) > 1
    assert len(_ids(on, "丰巢取件码忘了怎么办", 8)) == 1


class _DenseStub:
    """假稠密件：含「短信」的段落与问句最近（模拟词面零重叠但语义相关）。"""
    INST = semrank.DenseEmbedder.INST

    def encode(self, texts, batch=16):
        import numpy as np
        return np.array([[1.0, 0.0] if ("短信" in t or t.startswith(self.INST)) else [0.0, 1.0] for t in texts], dtype=np.float32)


def test_dense_off_by_default_and_missing_is_v71(tmp_path, monkeypatch):
    """v8：sem_dense = 0 即 v7.1；稠密件不可用时 sem_dense>0 与 v7.1 逐位相同。"""
    monkeypatch.setattr(semrank, "get_scorer", lambda: _Stub())
    monkeypatch.setattr(semrank, "get_embedder", lambda: None)
    kw = dict(V71, tp_head=1, tp_coh=0.0, lc_head=2, sem_n=2, sem_tau=-99.0, sem_min=1)
    _same(_eng(tmp_path), dict(kw), dict(kw, sem_dense=3), (("丰巢取件码忘了怎么办", 8), ("红烧肉怎么做", 6)))


def test_dense_injects_candidates_beyond_head(tmp_path, monkeypatch):
    """v8：稠密补入词面头部之外的候选，经同一打分件重排；链式请求不补。"""
    monkeypatch.setattr(semrank, "get_scorer", lambda: _Stub())
    monkeypatch.setattr(semrank, "get_embedder", lambda: _DenseStub())
    kw = dict(V71, tp_head=1, tp_coh=0.0, lc_head=2, sem_n=1, sem_tau=-99.0, sem_min=1)
    q = "丰巢取件码忘了怎么办"
    off = _ids(_eng(tmp_path / "off", **kw), q, 8)
    on = _ids(_eng(tmp_path / "on", **dict(kw, sem_dense=1)), q, 8)
    sms = [d for d in WEB if "短信" in d][0]
    assert sms in on and on.index(sms) <= 1
    assert sms not in off[:1]
    qc = "丰巢取件码从最初到现在经历过哪些变更"
    assert _ids(_eng(tmp_path / "c1", **dict(kw, sem_dense=1)), qc, 8) == _ids(_eng(tmp_path / "c0", **kw), qc, 8)


def test_real_embedder_smoke():
    em = semrank.get_embedder()
    if em is None:
        pytest.skip("bge-small-zh 不可用")
    v = em.encode([semrank.DenseEmbedder.INST + "取件码忘了", "快递柜取件码可在公众号查看。", "红烧肉先焯水。"])
    assert float(v[0] @ v[1]) > float(v[0] @ v[2])
    assert (em.encode(["快递柜取件码可在公众号查看。"]) == v[1:2]).all()


# ---------------------------------------------------------------- v9：判别头 D（PREREG_ZH 修订 7）
class _DiscStub:
    """假判别头：含「短信」者判为满足需求（高分），其余低分。"""

    def score(self, q, passages, batch=16):
        return [6.0 if "短信" in p else -6.0 for p in passages]


def test_disc_off_by_default_and_missing_is_v71(tmp_path, monkeypatch):
    """sem_disc 缺省 0；头缺失（get_disc → None）或打分件不是真 CrossScorer ⇒ 与 v7.1 逐位相同。"""
    assert ax.AssocConfig().sem_disc == 0.0
    st = _Stub()
    monkeypatch.setattr(semrank, "get_scorer", lambda: st)
    assert semrank.get_disc(st) is None
    base = dict(tp_head=1, tp_coh=0.0, lc_head=2, sem_n=40, sem_tau=0.0, sem_min=1)
    _same(_eng(tmp_path), base, dict(base, sem_disc=1.0), (("丰巢取件码忘了怎么办", 8), ("红烧肉怎么做", 6)))


def test_disc_reorders_and_gates(tmp_path, monkeypatch):
    """头存在且 sem_disc > 0：排序 / 截断分 = logit + α·D；D 低的段被挤出阈值。"""
    st = _Stub()
    monkeypatch.setattr(semrank, "get_scorer", lambda: st)
    monkeypatch.setattr(semrank, "get_disc", lambda sc: _DiscStub())
    base = dict(tp_head=1, tp_coh=0.0, lc_head=2, sem_n=40, sem_tau=0.0, sem_min=1)
    e = _eng(tmp_path)
    e.retriever.assoc = ax.AssocConfig(**base); off = _ids(e, "丰巢取件码忘了怎么办", 8)
    e.retriever.assoc = ax.AssocConfig(**dict(base, sem_disc=1.0)); on = _ids(e, "丰巢取件码忘了怎么办", 8)
    assert len(off) == 2 and len(on) == 1 and "短信" in on[0]


def test_disc_skips_chain_requests(tmp_path, monkeypatch):
    """链式请求不经过判别头（v7.1 行为）。"""
    st = _Stub()
    monkeypatch.setattr(semrank, "get_scorer", lambda: st)
    monkeypatch.setattr(semrank, "get_disc", lambda sc: _DiscStub())
    base = dict(tp_head=1, tp_coh=0.0, lc_head=2, sem_n=40, sem_tau=0.0, sem_min=1)
    _same(_eng(tmp_path), base, dict(base, sem_disc=1.0), (("丰巢取件码经历过哪些变更", 8),))


def test_anstype_features_and_weights():
    """答案类型相容（修订 7b）：问价格时，含金额的段落分高于只有商品名的段落；权重文件存在且维度一致。"""
    from lingshu_ng import anstype, anstype_w
    assert len(anstype_w.W) == len(anstype_w.MU) == len(anstype_w.SD) == anstype.DIM
    a, b = anstype.score("五星迎宾酒52度价格多少钱一瓶", ["五星迎宾酒52度 零售参考价:99.00元", "五星迎宾酒52度 浓香型白酒 产地四川"])
    assert a > b


def test_ans_off_by_default_and_chain_exempt(tmp_path, monkeypatch):
    """sem_ans 缺省 0（= v7.1）；链式请求不加答案类型分。"""
    assert ax.AssocConfig().sem_ans == 0.0
    st = _Stub()
    monkeypatch.setattr(semrank, "get_scorer", lambda: st)
    base = dict(tp_head=1, tp_coh=0.0, lc_head=2, sem_n=40, sem_tau=0.0, sem_min=1)
    _same(_eng(tmp_path), base, dict(base, sem_ans=50.0), (("丰巢取件码经历过哪些变更", 8),))


# ---------------------------------------------------------------- v10：稠密 z 分融合排序（PREREG_ZH 修订 8）
def test_fuse_off_by_default_and_missing_is_v71(tmp_path, monkeypatch):
    """v10：sem_fuse 缺省 0（= v7.1）；稠密件不可用时 sem_fuse>0 与 v7.1 逐位相同。"""
    assert ax.AssocConfig().sem_fuse == 0.0
    monkeypatch.setattr(semrank, "get_scorer", lambda: _Stub())
    monkeypatch.setattr(semrank, "get_embedder", lambda: None)
    kw = dict(tp_head=1, tp_coh=0.0, lc_head=2, sem_n=40, sem_tau=-99.0, sem_min=1)
    _same(_eng(tmp_path), dict(kw), dict(kw, sem_fuse=2.0), (("丰巢取件码忘了怎么办", 8), ("红烧肉怎么做", 6)))


def test_fuse_reorders_but_keeps_truncation_set(tmp_path, monkeypatch):
    """v10：融合只改排序，截断集合仍按 logit ≥ τ；链式请求不融合。"""
    monkeypatch.setattr(semrank, "get_scorer", lambda: _Stub())
    monkeypatch.setattr(semrank, "get_embedder", lambda: _DenseStub())
    kw = dict(tp_head=1, tp_coh=0.0, lc_head=2, sem_n=40, sem_tau=-2.0, sem_min=1)
    q = "丰巢取件码忘了怎么办"
    off = _ids(_eng(tmp_path / "off", **kw), q, 8)
    on = _ids(_eng(tmp_path / "on", sem_fuse=5.0, **kw), q, 8)
    assert set(on) == set(off)
    sms = [d for d in WEB if "短信" in d][0]
    assert sms in on and on[0] == sms
    qc = "丰巢取件码从最初到现在经历过哪些变更"
    assert _ids(_eng(tmp_path / "c1", sem_fuse=5.0, **kw), qc, 8) == _ids(_eng(tmp_path / "c0", **kw), qc, 8)


def test_dense_z_shape():
    import numpy as np
    z = None
    em = semrank.get_embedder()
    if em is not None:
        z = semrank.dense_z("取件码忘了", ["快递柜取件码可在公众号查看。", "红烧肉先焯水。", "短信取件码"])
        assert len(z) == 3 and abs(float(np.mean(z))) < 1e-4


def test_adaptive_dense_fires_only_when_head_weak(tmp_path, monkeypatch):
    """v10：sem_dense_m > 0 时，词面头部 logit ≥ τ 者 ≥ m 条 → 与 v7.1 逐位相同（不补）；少于 m 条 → 与 v8 总补逐位相同。"""
    monkeypatch.setattr(semrank, "get_scorer", lambda: _Stub())
    monkeypatch.setattr(semrank, "get_embedder", lambda: _DenseStub())
    kw = dict(V71, tp_head=1, tp_coh=0.0, lc_head=2, sem_n=1, sem_tau=-99.0, sem_min=1)
    q = "丰巢取件码忘了怎么办"
    e = _eng(tmp_path)
    _same(e, dict(kw), dict(kw, sem_dense=1, sem_dense_m=1), ((q, 8),))            # 头部 1 条 ≥ τ，不补
    _same(e, dict(kw, sem_dense=1), dict(kw, sem_dense=1, sem_dense_m=2), ((q, 8),))   # 1 < 2，补 = v8
    qc = "丰巢取件码从最初到现在经历过哪些变更"
    _same(e, dict(kw), dict(kw, sem_dense=1, sem_dense_m=5), ((qc, 8),))             # 链式请求不补


def test_adaptive_dense_cap_and_tau(tmp_path, monkeypatch):
    """v11（PREREG_ZH 修订 9）：sem_dense_cap / sem_dense_tau 只作用于被触发的自适应补入
    （未触发或总补 m = 0 时逐位不变）；cap = k → 取段 ≤ k·sem_min；补入段 logit < τd → 不保留（= 不补）。"""
    monkeypatch.setattr(semrank, "get_scorer", lambda: _Stub())
    monkeypatch.setattr(semrank, "get_embedder", lambda: _DenseStub())
    kw = dict(V71, tp_head=1, tp_coh=0.0, lc_head=2, sem_n=1, sem_tau=-99.0, sem_min=1)
    q = "丰巢取件码忘了怎么办"
    e = _eng(tmp_path)
    _same(e, dict(kw), dict(kw, sem_dense=3, sem_dense_m=1, sem_dense_cap=1, sem_dense_tau=99.0), ((q, 8),))   # 未触发
    _same(e, dict(kw, sem_dense=1), dict(kw, sem_dense=1, sem_dense_cap=1, sem_dense_tau=99.0), ((q, 8),))       # 总补不受影响
    _same(e, dict(kw), dict(kw, sem_dense=3, sem_dense_m=2, sem_dense_tau=99.0), ((q, 8),))                      # 补入段全不过 τd
    e.retriever.assoc = ax.AssocConfig(**dict(kw, sem_dense=3, sem_dense_m=2)); full = e_rows(e, q, 8)
    e.retriever.assoc = ax.AssocConfig(**dict(kw, sem_dense=3, sem_dense_m=2, sem_dense_cap=1)); capped = e_rows(e, q, 8)
    assert len(full) > 1 and capped == full[:1]
