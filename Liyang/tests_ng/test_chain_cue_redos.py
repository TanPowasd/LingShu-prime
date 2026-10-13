# -*- coding: utf-8 -*-
"""chain-r20：速记体分句提示正则 _CUE_ONLY 的无灾难回溯等价实现 _cue_only。"""
import random
import time

from lingshu_ng.chain import shorthand as S
from lingshu_ng.chain.ledger import Ledger


def test_cue_only_equivalent_fuzz(monkeypatch):
    monkeypatch.setattr(S, "_CUE_SHORT", 0)              # 强制走动态规划路径，与原式逐条比对
    toks = ["tbd", "pending", "no longer", "no value retained", "n/a", "none", "final", "ok", "dispute settled", " ",
            "待定", "未定", "裁定", "尘埃落定", "不再保留", "导致", "甲", "乙丙", "x", "A", "_", "1", "/", "since then",
            "anymore", "，", "with no value kept", "ſ", "K"]
    rnd = random.Random(20)
    for _ in range(4000):
        c = "".join(rnd.choice(toks) for _ in range(rnd.randint(1, 6)))
        if len(c) <= 24:
            assert S._cue_only(c) == bool(S._CUE_ONLY.fullmatch(c)), c


def test_cue_only_basic():
    assert S._cue_only("待定")
    assert S._cue_only("tbd 未定")
    assert S._cue_only("因为供应商临时调整所致")
    assert not S._cue_only("甲")
    assert not S._cue_only("tbdx")
    assert not S._cue_only("")


def test_cue_only_long_no_backtracking():
    long_fail = "汉" * 400 + "x"                         # 原式在此类串上指数回溯
    long_punct = ("苏州北站到崇福大概一个多小时车程，" * 20).replace("，", ",")
    t = time.time()
    assert S._cue_only(long_fail) is False
    assert S._cue_only(long_punct) is False
    assert S._cue_only("汉" * 300) is True
    assert time.time() - t < 5


def test_ledger_long_unpunctuated_paragraph_fast():
    p = "苏州南站--崇福 苏州汽车北站 桐乡 17:30 大一20 35。0 1 " + "中国与欧美女性对待男人的不同关注爱马的人们拥有爱心幸福财富与学识" * 6 + ",欧美女性分享男人的生活,夫妻间平等相处。"
    L = Ledger(); t = time.time()
    L.add_text(p, ref="x#1")
    assert time.time() - t < 5
