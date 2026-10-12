# -*- coding: utf-8 -*-
"""版本链核心（lingshu_ng.chain）单元与接入测试：抽取、账本四态、别名、路由、作答、召回编排、开关、持久化。"""
import os

import pytest

from lingshu_ng.chain import Ledger, answer, extract, parse_header, plan, read_material, route
from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.engine import MemoryEngine

SEGS = [
    "第 1 次提交（甲项目）。甲服务 的依赖名首次确立为 redis。甲服务 的签名首次确立为 get(key, ttl)。闲话一句。",
    "第 2 次提交（甲项目）。甲项目 的依赖名调整为 lmdb，起因是容量评估。甲服务 自第 2 次提交起改名为 甲项目。",
    "第 3 次提交（甲项目）。甲项目 的依赖名出现两种并存的取值：sled 与 bbolt，尚未裁定，起因是评审分歧。",
    "第 4 次提交（甲项目）。甲项目 的依赖名的争议就此裁定为 bbolt，起因是压测结论。甲项目·下属 的依赖名首次确立为 rocksdb。",
    "第 5 次提交（甲项目）。甲项目 的依赖名被撤销，此后不再保留取值，起因是架构收敛。",
    "第 6 次提交（甲项目）。甲项目 的依赖名此后确立为 redis，起因是回归验证。",
]


def ledger():
    L = Ledger()
    for i, s in enumerate(SEGS, 1):
        L.add_text(s, ref=f"甲项目#{i}")
    return L


def test_extract_ops_and_reason():
    evs = extract(SEGS[2])
    assert len(evs) == 1 and evs[0].op == "unresolve" and evs[0].value == "sled" and evs[0].alt == "bbolt"
    assert evs[0].reason == "评审分歧"
    e1 = extract(SEGS[0])
    assert [(e.entity, e.attr, e.value) for e in e1] == [("甲服务", "依赖名", "redis"), ("甲服务", "签名", "get(key, ttl)")]
    assert extract("老周 移到了 后山，起因是避雨。")[0].attr == "位置"
    assert extract("这句没有任何版本事件。") == []


def test_header():
    h = parse_header(SEGS[3])
    assert (h.seq, h.ns) == (4, "甲项目")
    assert parse_header("随便一段话").seq is None


def test_four_states_and_alias():
    L = ledger()
    evs = L.events("甲项目", "甲项目", "依赖名")
    assert [e.seq for e in evs] == [1, 2, 3, 4, 5, 6]          # 改名前的事件经别名并入
    st = {T: Ledger.status_at(evs, T) for T in range(0, 7)}
    assert st[0].state == "absent"
    assert (st[1].value, st[1].state) == ("redis", "active")
    assert (st[3].value, st[3].state) == ("sled", "unresolved")
    assert (st[4].value, st[4].state) == ("bbolt", "active")
    assert (st[5].value, st[5].state) == (None, "retired")
    assert (st[6].value, st[6].state, st[6].at_seq) == ("redis", "active", 6)
    tl = Ledger.timeline(evs)
    assert [(r["from"], r["to"]) for r in tl] == [(None, "redis"), ("redis", "lmdb"), ("lmdb", "sled"), ("sled", "bbolt"),
                                                   ("bbolt", None), (None, "redis")]


def test_nested_subject_not_confused():
    L = ledger()
    assert L.locate("截至第 6 次提交，甲项目·下属 的依赖名当前是什么值？")[1] == "甲项目·下属"
    assert L.locate("截至第 6 次提交，甲项目 的依赖名当前是什么值？")[1] == "甲项目"


def test_route():
    assert route("甲 的依赖名从最初到现在经历过哪些变更？").intent == "change"
    assert route("甲 的依赖名为什么在第 2 次提交被修改？").intent == "reason"
    r = route("在第 3 次提交这个时间点，甲 的依赖名处于什么状态？")
    assert (r.intent, r.T) == ("state", 3)
    assert route("在第 3 次提交时，甲 的依赖名是什么值？").intent == "history"
    assert route("截至第 6 次提交，甲 的依赖名当前是什么值？").intent == "present"


def test_answer_types():
    L = ledger()
    a = answer(L, "截至第 6 次提交，甲项目 的依赖名当前是什么值？")
    assert (a["value"], a["state"], a["at_seq"]) == ("redis", "active", 6)
    assert a["basis"][0]["file"] == "甲项目#6" and "此后确立为 redis" in a["basis"][0]["quote"]
    a = answer(L, "在第 5 次提交时，甲项目 的依赖名是什么值？")
    assert (a["value"], a["state"]) == (None, "retired")
    a = answer(L, "甲项目 的依赖名为什么在第 2 次提交被修改？")
    assert a["value"] == "容量评估"
    a = answer(L, "甲项目 的依赖名从最初到现在经历过哪些变更？")
    assert {"seq": 2, "from": "redis", "to": "lmdb"} in a["chain"]
    assert answer(L, "截至第 6 次提交，甲项目 的信任对象处于什么状态？")["state"] == "absent"
    assert answer(L, "乙项目 的依赖名是什么？")["state"] == "absent"


def test_read_material_only_sees_material():
    mat = [{"cid": "甲项目#2", "text": SEGS[1]}]
    a = read_material("截至第 6 次提交，甲项目 的依赖名当前是什么值？", mat)
    assert (a["value"], a["at_seq"]) == ("lmdb", 2)            # 材料里只有第 2 版：读者不越过材料


def test_plan_current_first_then_chrono_and_no_future():
    L = ledger()
    p = plan(L, "截至第 6 次提交，甲项目 的依赖名当前是什么值？")
    assert p[0] == "甲项目#6" and p[1] == "甲项目#2"           # 当前版本段 → 别名声明段
    assert p[2:] == ["甲项目#1", "甲项目#3", "甲项目#4", "甲项目#5"]
    p = plan(L, "在第 3 次提交时，甲项目 的依赖名是什么值？")
    assert p[0] == "甲项目#3" and all(int(x.split("#")[1]) <= 3 for x in p)
    assert plan(L, "完全无关的问题") == []


def test_engine_switch_off_by_default(monkeypatch):
    monkeypatch.delenv("LINGSHU_NG_CHAIN", raising=False)
    e = MemoryEngine()
    assert e.chain is None and e.chain_answer("x") is None
    assert "chain_events" not in e.store.db.tables()


def test_engine_chain_recall_and_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("LINGSHU_NG_CHAIN", "1")
    db = str(tmp_path / "m.db")
    e = SpacetimeMemoryEngine(db)
    ids = {}
    for i, s in enumerate(SEGS, 1):
        ids[e.add_perception(s).id] = i
    for j in range(20):
        e.add_perception(f"无关的日常记录第{j}条：甲项目 的依赖名讨论很多，但这里没有结论。")
    hits = e.recall("截至第 6 次提交，甲项目 的依赖名当前是什么值？", limit=3)
    assert [ids.get(n.id) for n, _ in hits][:2] == [6, 2]
    s = [sc for _, sc in hits]
    assert s == sorted(s, reverse=True)
    a = e.ng.chain_answer("截至第 6 次提交，甲项目 的依赖名当前是什么值？")
    assert a["value"] == "redis"
    e2 = SpacetimeMemoryEngine(db)                               # 重开库：账本从表里载回
    assert e2.ng.chain_answer("在第 3 次提交时，甲项目 的依赖名是什么值？")["state"] == "unresolved"


def test_engine_chain_unmatched_query_unchanged(monkeypatch):
    monkeypatch.delenv("LINGSHU_NG_CHAIN", raising=False)
    base = MemoryEngine()
    on = MemoryEngine()
    on.enable_chain()
    for s in SEGS + ["今天天气不错，适合散步。", "散步时遇到了老朋友。"]:
        base.perceive(s)
        on.perceive(s)
    q = "散步遇到谁"
    a = [n.content for n, _ in base.recall(q, 5)["hits"]]
    b = [n.content for n, _ in on.recall(q, 5)["hits"]]
    assert a == b


def test_enable_chain_rebuild_from_existing_nodes():
    e = MemoryEngine()
    for s in SEGS:
        e.perceive(s)
    e.enable_chain(rebuild=True)
    assert e.chain_answer("截至第 6 次提交，甲项目 的依赖名当前是什么值？")["value"] == "redis"


def test_max_promote_leaves_room_for_base_recall(monkeypatch):
    monkeypatch.delenv("LINGSHU_NG_CHAIN", raising=False)
    e = MemoryEngine()
    e.enable_chain()
    assert e.chain.max_promote == 3
    for s in SEGS:
        e.perceive(s)
    q = "截至第 6 次提交，甲项目 的依赖名当前是什么值？"
    refs = e.chain.ledger and __import__("lingshu_ng.chain", fromlist=["plan"]).plan(e.chain.ledger, q)
    assert len(refs) > 3
    hits = e.recall(q, 6)["hits"]
    assert len(hits) == 6
    e.chain.max_promote = None                  # v1：编排段可占满
    assert len(e.recall(q, 6)["hits"]) == 6


def test_co_mention_guard_promotes_unparsed_newer_version(monkeypatch):
    """账本只认出第 1 版；第 3 段用句式表外的说法写了新版本（同句共现实体与属性）——共现守卫把它排到账本当前版本之前。"""
    monkeypatch.delenv("LINGSHU_NG_CHAIN", raising=False)
    import sys
    monkeypatch.setattr(sys.modules["lingshu_ng.chain.extract"], "LOOSE", False)          # 本条测的是严格抽取漏版本时的守卫（宽松抽取会直接认出第 3 段）
    monkeypatch.setattr(sys.modules["lingshu_ng.chain.anchored"], "ANCHOR", False)        # v9 词表锚定也会直接认出第 3 段
    e = MemoryEngine()
    e.enable_chain()
    segs = ["第 1 次提交（乙项目）。乙项目 的端口首次确立为 8080。",
            "第 2 次提交（乙项目）。日常维护，无配置改动。",
            "第 3 次提交（乙项目）。说到端口，乙项目 这回挪去了 9090。"]
    ids = [e.perceive(s).node_id for s in segs]
    q = "截至第 3 次提交，乙项目 的端口当前是什么值？"
    top = [n.id for n, _ in e.recall(q, 2)["hits"]]
    assert top[0] == ids[2] and ids[0] in top
    e.chain.co_guard = False
    assert [n.id for n, _ in e.recall(q, 2)["hits"]][0] == ids[0]


# ---------------------------------------------------------------- 跨命名空间同名实体（v6）
XNS = [
    "第 1 次提交（甲项目）。甲服务 的依赖名首次确立为 redis。",
    "第 2 次提交（甲项目）。甲服务 的依赖名调整为 lmdb，起因是容量评估。",
    "第 1 次提交（甲项目二期）。甲服务 的依赖名首次确立为 sled。",
    "第 2 次提交（甲项目二期）。甲服务 的依赖名调整为 bbolt，起因是压测。",
    "第 3 次提交（甲项目二期）。甲服务 的依赖名调整为 badger，起因是回归。",
]


def xledger():
    L = Ledger()
    for i, s in enumerate(XNS):
        L.add_text(s, ref=f"x#{i}")
    return L


def test_xns_namespace_cue_longest_and_not_entity_span():
    L = xledger()
    assert L.locate("在甲项目二期里，甲服务 的依赖名当前是什么值？")[0] == "甲项目二期"   # 「甲项目」被更长的「甲项目二期」覆盖
    assert L.locate("在甲项目里，甲服务 的依赖名当前是什么值？")[0] == "甲项目"
    assert answer(L, "在甲项目二期里，甲服务 的依赖名当前是什么值？")["value"] == "badger"
    assert answer(L, "在甲项目里，甲服务 的依赖名当前是什么值？")["value"] == "lmdb"
    # 实体名本身就是某命名空间名时，实体所在位置不算该命名空间的线索
    L2 = Ledger()
    L2.add_text("第 1 次提交（乙）。乙 的端口首次确立为 80。", ref="a")
    L2.add_text("第 1 次提交（丙）。乙 的端口首次确立为 90。", ref="b")
    assert L2.ambiguous("乙 的端口当前是什么值？")
    assert L2.locate("在丙里，乙 的端口当前是什么值？")[0] == "丙"


def test_xns_no_cue_is_ambiguous_and_plan_interleaves():
    L = xledger()
    q = "甲服务 的依赖名当前是什么值？"
    assert {c[0] for c in L.ambiguous(q)} == {"甲项目", "甲项目二期"}
    a = answer(L, q)
    assert a["confidence"] == "ambiguous"
    assert {(c["namespace"], c["value"]) for c in a["candidates"]} == {("甲项目", "lmdb"), ("甲项目二期", "badger")}
    assert answer(L, q, ns_pref=["甲项目二期"])["value"] == "badger"
    refs = plan(L, q, ns_pref=["甲项目二期"])
    assert refs[:2] == ["x#4", "x#1"]                   # 两个命名空间的当前版本交错，ns_pref 靠前者先
    # 时点超出某命名空间已知序号 → 该命名空间降分，不再有歧义
    assert not L.ambiguous("在第 3 次提交时，甲服务 的依赖名是什么值？", 3)
    assert answer(L, "在第 3 次提交时，甲服务 的依赖名是什么值？")["value"] == "badger"


def test_xns_engine_uses_base_recall_order(tmp_path, monkeypatch):
    monkeypatch.setenv("LINGSHU_NG_CHAIN", "1")
    e = SpacetimeMemoryEngine(os.path.join(str(tmp_path), "m.db"))
    ids = [e.add_perception(s).id for s in XNS]
    res = e.recall("在甲项目二期里，甲服务 的依赖名当前是什么值？", limit=3)
    assert res[0][0].id == ids[4]
    res = e.recall("在甲项目里，甲服务 的依赖名当前是什么值？", limit=3)
    assert res[0][0].id == ids[1]


# ---------------------------------------------------------------- 宽松抽取（v7 冷启动）
@pytest.mark.parametrize("sent,want", [
    ("出于容量评估结论，甲服务 的依赖名现在改成了 lmdb。", ("set", "甲服务", "依赖名", "lmdb", None)),
    ("压测结论让「甲服务」的「依赖名」变成了「sled」。", ("set", "甲服务", "依赖名", "sled", None)),
    ("甲服务把依赖名换成了 get(key, ttl)，这都是因为评审意见。", ("set", "甲服务", "依赖名", "get(key, ttl)", None)),
    ("说到依赖名，甲服务 这回定为 bbolt，起因是回归。", ("set", "甲服务", "依赖名", "bbolt", None)),
    ("因为一场误会，老周 搬到了 后山。", ("set", "老周", "位置", "后山", None)),
    ("由于架构收敛，甲服务的依赖名已经作废，往后不再有任何取值。", ("retire", "甲服务", "依赖名", None, None)),
    ("甲服务 的依赖名有两种说法：sled 与 bbolt，尚未裁定。", ("unresolve", "甲服务", "依赖名", "sled", "bbolt")),
    ("redis 被定为甲服务的依赖名。", ("set", "甲服务", "依赖名", "redis", None)),
])
def test_loose_extract_common_structures(sent, want):
    ev = [e for e in extract(sent) if e.op != "mention"]
    assert ev and (ev[0].op, ev[0].entity, ev[0].attr, ev[0].value, ev[0].alt) == want
    assert ev[0].extra.get("loose") or ev[0].op in ("set", "retire", "unresolve")


def test_loose_reason_and_switch_off():
    ev = extract("出于容量评估结论，甲服务 的依赖名现在改成了 lmdb。")[0]
    assert ev.reason == "容量评估结论"
    assert not [e for e in extract("出于容量评估结论，甲服务 的依赖名现在改成了 lmdb。", loose=False) if e.op != "mention"]
    # 严格句式不受影响；描述句（「是」字判断、无变更动词）不登记
    assert [(e.op, e.value) for e in extract(SEGS[1])][:1] == [("set", "lmdb")]
    assert [e for e in extract("构建产物已推送到制品库。评审记录同步到了协作平台。") if e.op != "mention"] == []


# ---------------------------------------------------------------- 宽松抽取 v8：口语/话题承接 + 精度过滤
@pytest.mark.parametrize("sent,want", [
    ("哎，乙服务那个缓存策略啊，因为压测结论，现在改成 lru 了。", ("set", "乙服务", "缓存策略", "lru", None)),
    ("乙服务那边，由于回归失败，缓存策略被定为 fifo。", ("set", "乙服务", "缓存策略", "fifo", None)),
    ("乙服务因为评审意见，把缓存策略换成了 arc。", ("set", "乙服务", "缓存策略", "arc", None)),
    ("老吴的立场因为利益冲突变成了反对。", ("set", "老吴", "立场", "反对", None)),
    ("老吴的立场成观望了，还不是因为一桩旧账。", ("set", "老吴", "立场", "观望", None)),
    ("老吴因为一次救助，搬到磨坊那边去了。", ("set", "老吴", "位置", "磨坊", None)),
    ("乙服务的缓存策略现在有两个版本摆在那儿没定，一个是 lru，另一个是 arc。", ("unresolve", "乙服务", "缓存策略", "lru", "arc")),
    ("**老吴**搬去了**祠堂**，都是因为一场误会。", ("set", "老吴", "位置", "祠堂", None)),
])
def test_loose_v8_colloquial(sent, want):
    ev = [e for e in extract(sent) if e.op != "mention"]
    assert ev and (ev[0].op, ev[0].entity, ev[0].attr, ev[0].value, ev[0].alt) == want


@pytest.mark.parametrize("sent", [
    "震撼还在，但刚才那点扫兴，慢慢变成了一丝奇怪的感觉。",          # 「变成了」里的「成了」不当倒装
    "咱们得先想明白，要把社会建设成什么样？",                          # 「建设成」不是「设成」；问句
    "这本身就应该成为价值观的一部分。",                                  # 「成为…的一部分」描述句
    "| 与结构的关系 | 接触新思想、成为传播节点 |",                       # 表格行
    "学习是将复杂现象简化为规则的过程。",                                # 「简化为」不是「化为」
    "这封信到达月球时，他已经去世了。",                                  # 「去世」不是移动
    "在信息论里，信息就是不确定性的减少。",                              # 定义句
])
def test_loose_v8_precision(sent):
    assert [e for e in extract(sent) if e.op != "mention" and e.extra.get("loose")] == []


# ---------------------------------------------------------------- 词表锚定二次抽取（v9）
def test_anchored_second_pass_uses_confirmed_lexicon(monkeypatch):
    import sys
    from lingshu_ng.chain.ledger import Ledger
    monkeypatch.setattr(sys.modules["lingshu_ng.chain.anchored"], "ANCHOR", True)
    L = Ledger()
    L.add_text("第 1 次提交（丙项目）。丙服务 的缓存策略首次确立为 lru。", ref="a")
    # 句式表外、宽松规则也不认的写法：主体与属性都已在账本里（严格句式登记过＝已确认）
    recs = L.add_text("第 2 次提交（丙项目）。周报：丙服务缓存策略一项，经评审后由 lru 切至 arc 执行。", ref="b")
    got = [(r.op, r.entity, r.attr, r.value) for r in recs if r.op != "mention"]
    assert ("set", "丙服务", "缓存策略", "arc") in got or ("set", "丙服务", "缓存策略", "lru") not in got
    st = L.status_at(L.events("丙项目", "丙服务", "缓存策略"), 2)
    assert st.value == "arc"


def test_anchored_needs_confirmed_key_and_switch(monkeypatch):
    import sys
    from lingshu_ng.chain.ledger import Ledger
    A = sys.modules["lingshu_ng.chain.anchored"]
    monkeypatch.setattr(A, "ANCHOR", True)
    L = Ledger()
    # 只有一条宽松登记（未确认）：不当锚点
    L.add_text("第 1 次提交（丁项目）。说到缓存策略，丁服务 这回定为 lru。", ref="a")
    recs = L.add_text("第 2 次提交（丁项目）。周报：丁服务缓存策略一项，经评审后切至 arc 执行。", ref="b")
    assert [r for r in recs if r.op != "mention"] == []
    monkeypatch.setattr(A, "ANCHOR", False)
    monkeypatch.setattr(sys.modules["lingshu_ng.chain.v16"], "WIN", False)    # v16 窗口抽取是另一条路径（见 test_chain_v16）
    L2 = Ledger()
    L2.add_text("第 1 次提交（丙项目）。丙服务 的缓存策略首次确立为 lru。", ref="a")
    recs = L2.add_text("第 2 次提交（丙项目）。周报：丙服务缓存策略一项，经评审后由 lru 切至 arc 执行。", ref="b")
    assert [r for r in recs if r.op != "mention"] == []
