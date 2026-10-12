# -*- coding: utf-8 -*-
"""zh-v1 Q11 联想扩展（lingshu_ng.assoc）：配置、锚定局部展开、联想扩散、关闭即逐位回退、英文通路不经过、退役不补入。"""
import json

import pytest

from lingshu_ng import assoc as ax
from lingshu_ng.engine import MemoryEngine

STORY = [
    "第一章 迷雾小镇。阿青走进小镇，街上空无一人，只有钟楼的影子。",
    "钟楼的守夜人告诉阿青，镇上的人三年前一夜之间全部离开了。",
    "阿青在守夜人的抽屉里找到一封旧信，信上写着去北方的盐湖。",
    "第二章 盐湖。阿青跋涉七天抵达盐湖，湖边有一座白色的石屋。",
    "石屋里住着一位老渔夫，他说小镇的人每年冬至都会回来一次。",
    "老渔夫交给阿青一把铜钥匙，说它能打开钟楼顶层的门。",
    "第三章 钟楼顶层。阿青用铜钥匙打开了门，里面是整面墙的名字。",
    "墙上的名字正是小镇居民，每个名字旁都刻着同一个日期。",
]


def _eng(tmp_path, docs=STORY, **cfg):
    e = MemoryEngine(str(tmp_path / "m.db"))
    for d in docs:
        e.perceive(d)
    e.retriever.assoc = ax.AssocConfig(**cfg) if cfg else ax.AssocConfig()
    return e


def _ids(e, q, k):
    return [n.content for n, _ in e.retriever.recall(q, k)]


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("LINGSHU_NG_ASSOC", json.dumps({"enabled": False, "gamma": 0.3, "nope": 1}))
    c = ax.config_from_env()
    assert c.enabled is False and c.gamma == 0.3
    monkeypatch.setenv("LINGSHU_NG_ASSOC", "{bad json")
    assert ax.config_from_env() == ax.AssocConfig()


def test_disabled_equals_no_expansion(tmp_path):
    a = _eng(tmp_path / "a", enabled=False)
    b = _eng(tmp_path / "b", anchor_beta=0.0, gamma=0.0, sp_K=0)
    for q in ("阿青在盐湖遇见了谁？", "钟楼顶层有什么？", "铜钥匙"):
        assert _ids(a, q, 4) == _ids(b, q, 4)


def test_anchor_pulls_following_passage(tmp_path):
    # 题面点名「盐湖」一章：锚块（第二章标题块）之后的下文被带进前 3
    off = _eng(tmp_path / "off", enabled=False)
    on = _eng(tmp_path / "on", gamma=0.0, sp_K=0, anchor_len=3, anchor_df=1)
    q = "「跋涉七天」那一段讲了什么？"
    got, base = _ids(on, q, 5), _ids(off, q, 5)
    assert STORY[3] == got[0] == base[0]          # 锚块本身仍居首
    assert STORY[4] in got and STORY[4] not in base  # 题面词零重合的下文（老渔夫一段）被带入


def test_no_anchor_no_change_when_gamma_zero(tmp_path):
    off = _eng(tmp_path / "off", enabled=False)
    on = _eng(tmp_path / "on", gamma=0.0, sp_K=0)
    q = "大家都去了哪里？"            # 无稀有片段 ⇒ AX1 不触发
    assert _ids(off, q, 5) == _ids(on, q, 5)


def test_scores_non_increasing_and_limit(tmp_path):
    e = _eng(tmp_path, anchor_len=3, anchor_df=1)
    res = e.retriever.recall("铜钥匙打开了哪扇门？", 5)
    assert len(res) <= 5
    s = [x for _, x in res]
    assert all(a >= b for a, b in zip(s, s[1:]))


def test_retired_neighbor_not_added(tmp_path):
    e = _eng(tmp_path, gamma=0.0, sp_K=0, anchor_len=3, anchor_df=1)
    nid = e.store.db.scalar("SELECT id FROM nodes WHERE content=?", [STORY[4]])
    e.store.nodes.update(nid, importance=0.01)
    e.store.nodes.add_tags(nid, ["archived"])
    got = _ids(e, "「跋涉七天」那一段讲了什么？", 5)
    assert STORY[4] not in got


def test_latin_query_bypasses(tmp_path, monkeypatch):
    docs = [f"meeting notes about the garden project, item {w}" for w in ("alpha", "bravo", "delta", "omega")]
    b = _eng(tmp_path / "b", docs)

    def boom(*a, **k):
        raise AssertionError("拉丁查询不应进入 AX")
    monkeypatch.setattr(b.retriever.associator, "expand", boom)
    assert _ids(b, "garden project meeting", 3)


def test_norm_scores_monotone():
    s = ax._norm_scores([("a", 0.9), ("b", 0.95), ("c", 0.5), ("d", 0.5)])
    assert s["a"] == 1.0 and s["b"] == 1.0 and s["d"] == 0.0 and s["c"] == 0.0


def test_spread_keeps_head_and_reaches_neighbors(tmp_path):
    off = _eng(tmp_path / "off", enabled=False)
    on = _eng(tmp_path / "on", ax2="spread", anchor_beta=0.0, head=1, sp_seeds=1, sp_K=3, sp_wr=0.0)
    q = "老渔夫交给阿青什么？"
    a, b = _ids(off, q, 8), _ids(on, q, 8)
    assert a[0] == b[0]                                    # 头部直接命中保持
    k = STORY.index(b[0])
    assert set(b[1:3]) <= {STORY[k - 1], STORY[k + 1]}     # 激活最高者是写入序前后邻块


def test_ppr_mode_still_available(tmp_path):
    e = _eng(tmp_path, ax2="ppr")
    s = [x for _, x in e.retriever.recall("钟楼顶层有什么？", 5)]
    assert s and all(a >= b for a, b in zip(s, s[1:]))


def test_default_is_ax1_only():
    c = ax.AssocConfig()
    assert c.enabled and c.ax2 == "off" and c.anchor_beta > 0


# ---------------------------------------------------------------- v4 LC 长预算邻接补全
def test_lc_head_prefix_unchanged(tmp_path):
    """limit ≤ lc_head 的召回与关闭 LC 逐位相同（T2 limit=10 口径不受影响的依据）。"""
    off = _eng(tmp_path / "off", lc_beta=0.0)
    on = _eng(tmp_path / "on", lc_beta=0.5, lc_head=3)
    for q in ("阿青在盐湖遇见了谁？", "钟楼顶层有什么？", "铜钥匙", "旧信"):
        assert _ids(on, q, 3) == _ids(off, q, 3)


def test_lc_promotes_neighbor_of_strong_seed(tmp_path):
    """头部之后：强命中块的写入序紧邻块排到孤立弱命中之前；名单分数保持非增。"""
    on = _eng(tmp_path / "on", anchor_beta=0.0, lc_beta=5.0, lc_head=1, lc_seeds=1, lc_span=1, lc_decay=0.5)
    off = _eng(tmp_path / "off", anchor_beta=0.0, lc_beta=0.0)
    q = "老渔夫"
    got, base = _ids(on, q, 8), _ids(off, q, 8)
    k = STORY.index(base[0])
    assert got[0] == base[0]
    assert set(got[1:3]) == {STORY[k - 1], STORY[k + 1]}   # 种子前后各一块紧随其后
    assert any(x not in base for x in got[1:3])            # 题面词零重合的邻块被补入
    sc = [s for _, s in on.retriever.recall(q, 8)]
    assert all(a >= b for a, b in zip(sc, sc[1:]))


def test_lc_disabled_equals_v3(tmp_path):
    a = _eng(tmp_path / "a", lc_beta=0.0, hd_beta=0.0)          # v5：HD 以 limit > lc_head 为启用条件，v3 对照须关 HD
    b = _eng(tmp_path / "b", lc_beta=0.0, hd_beta=0.0, lc_head=0, lc_seeds=50)
    for q in ("阿青在盐湖遇见了谁？", "钟楼顶层有什么？"):
        x, y = _ids(a, q, 8), _ids(b, q, 8)      # 尾部同分按墙钟近因/随机 id 定序（ng 已知非确定），比集合与头部
        assert sorted(x) == sorted(y) and x[:3] == y[:3]


# ---------------------------------------------------------------- v5 HD 头部邻接重排 / LC 误用门
def test_hd_inactive_for_short_requests(tmp_path, monkeypatch):
    """limit ≤ lc_head：HD 不启用（T2 limit=10 口径不受影响）；limit > lc_head 才调用。"""
    on = _eng(tmp_path / "on", hd_beta=5.0, hd_gate=0.0, lc_head=5)
    calls = []
    orig = on.retriever.associator._head_context
    monkeypatch.setattr(on.retriever.associator, "_head_context", lambda *a, **k: calls.append(1) or orig(*a, **k))
    for q in ("阿青在盐湖遇见了谁？", "钟楼顶层有什么？", "迷雾小镇的钟楼", "旧信"):
        on.retriever.recall(q, 5)
    assert not calls
    on.retriever.recall("迷雾小镇的钟楼", 6)
    assert calls


_HDKW = dict(anchor_beta=0.0, lc_beta=0.0, lc_head=2, hd_n=2, hd_seeds=1, hd_span=1, rare_frac=1.0)


def test_hd_pulls_neighbor_into_head_for_long_requests(tmp_path):
    """limit > lc_head：强命中块的写入序紧邻块被排进头部（题面只与它共享「钟楼」）；分数非增。"""
    off = _eng(tmp_path / "off", hd_beta=0.0, hd_gate=0.0, **_HDKW)
    on = _eng(tmp_path / "on", hd_beta=0.5, hd_gate=0.0, **_HDKW)
    q = "迷雾小镇的钟楼"
    base, got = _ids(off, q, 8), _ids(on, q, 8)
    assert base[0] == got[0] == STORY[0]
    assert STORY[1] not in base[:2] and got[1] == STORY[1]
    sc = [s for _, s in on.retriever.recall(q, 8)]
    assert all(a >= b for a, b in zip(sc, sc[1:]))


def test_hd_gate_blocks_neighbor(tmp_path):
    """重叠门：邻块与题面稀有词的重叠低于门槛则不得邻接加分（门 > 1 时头部与关闭 HD 相同）。"""
    off = _eng(tmp_path / "off", hd_beta=0.0, **_HDKW)
    on = _eng(tmp_path / "on", hd_beta=0.5, hd_gate=1.01, **_HDKW)
    for q in ("迷雾小镇的钟楼", "墙上的日期", "阿青跋涉七天"):
        assert _ids(on, q, 8)[:2] == _ids(off, q, 8)[:2]


def test_overlap_weights():
    qw = {"盐湖": 2.0, "石屋": 1.0}
    assert ax.Associator._overlap("湖边有一座白色的石屋", qw) == pytest.approx(1 / 3)
    assert ax.Associator._overlap("无关的句子", qw) == 0.0
    assert ax.Associator._overlap("任何", {}) == 0.0


# ---------------------------------------------------------------- v6 TP 话题伪相关补全 + 写入序连贯度门
WEB = [  # 无写入序话题连续性的段落集：三个话题交错写入
    "丰巢快递柜取件码忘记了，可以在柜机屏幕点击忘记取件码重新获取。",
    "西红柿炒鸡蛋先炒鸡蛋盛出，再炒西红柿出汁后倒回鸡蛋翻炒。",
    "汽车保养一般每五千公里更换一次机油和机油滤芯。",
    "快递柜验证码输错三次会被锁定，需要等待十分钟后再取快递。",
    "鸡蛋要打散加少许盐，西红柿去皮口感更好。",
    "机油的型号要看车辆手册，保养时也要检查刹车片。",
    "如果快递柜取件码短信被删，可以在丰巢公众号里查看取件码。",
    "西红柿鸡蛋汤做法和炒菜不同，水开后淋入蛋液。",
]


def test_tp_inactive_for_short_requests(tmp_path, monkeypatch):
    """limit ≤ lc_head：TP 不启用（T2 limit=10 口径逐位不变的依据）。"""
    on = _eng(tmp_path / "on", docs=WEB, tp_head=1, tp_coh=0.0, lc_head=5)
    calls = []
    orig = on.retriever.associator._topic_prf
    monkeypatch.setattr(on.retriever.associator, "_topic_prf", lambda *a, **k: calls.append(1) or orig(*a, **k))
    for q in ("快递柜取件码忘了怎么办", "西红柿炒鸡蛋"):
        on.retriever.recall(q, 5)
    assert not calls
    on.retriever.recall("快递柜取件码忘了怎么办", 6)
    assert calls


def test_tp_pulls_same_topic_passages(tmp_path):
    """长请求：头部之后同话题段落（与题面字面重叠少）排在其他话题之前；分数非增。"""
    on = _eng(tmp_path / "on", docs=WEB, anchor_beta=0.0, lc_beta=0.0, lc_head=2, tp_head=1, tp_seeds=2, tp_coh=0.0)
    q = "丰巢取件码忘了怎么办"
    got = _ids(on, q, 8)
    topic = {WEB[0], WEB[3], WEB[6]}
    assert set(got[:3]) == topic
    sc = [s for _, s in on.retriever.recall(q, 8)]
    assert all(a >= b for a, b in zip(sc, sc[1:]))


def test_tp_coherence_gate_falls_back_to_lc(tmp_path):
    """写入序连贯（小说）且门槛低于其连贯度 ⇒ 走 LC，与关 TP 相同；tp_head=0 即 v4。"""
    a = _eng(tmp_path / "a", tp_head=0)
    b = _eng(tmp_path / "b", tp_head=5, tp_coh=1e-9)
    for q in ("阿青在盐湖遇见了谁？", "钟楼顶层有什么？"):
        x, y = _ids(a, q, 20), _ids(b, q, 20)
        assert sorted(x) == sorted(y) and x[:3] == y[:3]


def test_delivery_defaults_v7():
    c = ax.AssocConfig()
    assert (c.tp_head, c.tp_seeds, c.tp_terms, c.tp_coh, c.tp_rrf) == (5, 8, 30, 0.8, 0)   # 交付 v7（模型缺失时退回 v4 = tp_head 0）
    assert (c.hd_beta, c.lc_beta, c.lc_seeds, c.lc_gate) == (0.0, 0.5, 20, 0.0)
