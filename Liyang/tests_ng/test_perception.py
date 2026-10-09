# -*- coding: utf-8 -*-
"""感知判据重写（lingshu_ng.perception）：与旧实现在合法输入上逐值相同 + 修复的缺陷类别。"""
import itertools
import math
import random

import pytest

from lingshu.core import condition_normalize as old_cn
from lingshu.core import verdict as old_v
from lingshu_ng.perception import conditions as cn
from lingshu_ng.perception import verdict as v

PARTS = ["head", "torso", "upper_arm_L", "hand_L", "upper_leg_L", "lower_leg_R", "foot_L"]


def _random_domains(rng, illegal=True):
    d = {}
    for k, allowed in cn.IMAGE_DOMAINS.items():
        r = rng.random()
        if r < 0.6:
            d[k] = rng.choice(allowed)
        elif r < 0.75:
            syn = [w for w, t in cn.SYNONYMS.items() if illegal or t in allowed]
            if syn:
                d[k] = rng.choice(syn)
        elif r < 0.85 and illegal:
            d[k] = "随便写的"
    return d


# ---------------------------------------------------------------- 与旧实现等价（合法输入）
def test_conditions_equal_legacy_on_legal_inputs():
    rng = random.Random(0)
    for _ in range(300):
        d = _random_domains(rng)
        assert cn.canonical_condition(d) == old_cn.canonical_condition(d)
        assert cn.validate_edges(d) == old_cn.validate_edges(d)
        legal = _random_domains(rng, illegal=False)          # 非法声明的身份见 test_invalid_value_*（#138）
        assert cn.cond_hash(legal) == old_cn.cond_hash(legal)
        assert cn.cond_hash(legal, "s") == old_cn.cond_hash(legal, "s")
        assert cn.canonical_sourced(legal) == old_cn.canonical_sourced(legal)
    assert cn.part_cond_hash("head", "abc", 3) == old_cn.part_cond_hash("head", "abc", 3)
    assert cn.img0_domains() == old_cn.img0_domains()


def test_verdict_equal_legacy_on_legal_inputs():
    rng = random.Random(1)
    for _ in range(600):
        d = {k: rng.choice(cn.IMAGE_DOMAINS[k]) for k in ("occlusion", "clothing", "contrast")
             if rng.random() < 0.8}                            # 合法输入 = 枚举值或缺键
        area = rng.choice([1, 50, 10000])
        fg = rng.randrange(0, area + 1)
        part = {"type": rng.choice(PARTS)}
        assert v.assess(part, d, fg, area) == old_v.assess(part, d, fg, area)


# ---------------------------------------------------------------- C1/V3：未声明语义统一
@pytest.mark.parametrize("part", PARTS)
@pytest.mark.parametrize("key", ["occlusion", "clothing", "contrast"])
def test_unasserted_equals_missing_none_and_invalid(part, key):
    base = {"occlusion": "无遮挡", "clothing": "无", "contrast": "清晰"}
    outs = []
    for val in (None, cn.UNASSERTED, "", "  ", 3, ["x"], "不在枚举里"):
        d = dict(base)
        d[key] = val
        outs.append(v.assess({"type": part}, d, 9000, 10000)["verdict"])
    d = dict(base)
    d.pop(key)
    outs.append(v.assess({"type": part}, d, 9000, 10000)["verdict"])
    assert len(set(outs)) == 1


def test_canonicalisation_never_changes_verdict():
    rng = random.Random(2)
    for _ in range(300):
        d = _random_domains(rng)
        for part in PARTS:
            assert v.assess({"type": part}, d, 9000, 10000) == \
                v.assess({"type": part}, cn.canonical_condition(d), 9000, 10000)


def test_canonical_idempotent_and_type_safe():
    d = {"style": ["动漫"], "pose": 3, "occlusion": None, "color": "柔和"}
    c = cn.canonical_condition(d)                              # 旧实现对列表取值抛 TypeError
    assert c["style"] == c["pose"] == c["occlusion"] == cn.UNASSERTED and c["color"] == "柔和"
    assert cn.canonical_condition(c) == c
    with pytest.raises(TypeError):
        cn.canonical_condition([("style", "动漫")])


# ---------------------------------------------------------------- V1/V2：数值闸门与零面积
@pytest.mark.parametrize("fg,area", [(math.nan, 100), (5, math.nan), (math.inf, 100), (5, math.inf),
                                     (5, -math.inf), (-1, 100), (True, 100), ("9000", 10000), (None, 1)])
def test_non_finite_or_invalid_counts_rejected(fg, area):
    with pytest.raises(ValueError):
        v.assess({"type": "head"}, {}, fg, area)


def test_legacy_raw_vs_canonical_split_on_illegal_value():
    """对照：旧实现对非法遮挡值「原样当遮挡」，规范化后却成未声明 ⇒ 同一张图两种结论（ng 统一为未声明）。"""
    raw = {"occlusion": "随便写的"}
    canon = old_cn.canonical_condition(raw)
    assert old_v.assess({"type": "head"}, raw, 9000, 10000)["verdict"] == "DEFER"
    assert old_v.assess({"type": "head"}, canon, 9000, 10000)["verdict"] == "ACCEPT"
    assert v.assess({"type": "head"}, raw, 9000, 10000) == v.assess({"type": "head"}, canon, 9000, 10000)


def test_legacy_nan_was_accepted():
    """对照：旧实现把 NaN 前景当成 ACCEPT（所有比较为假一路落到底）。"""
    assert old_v.assess({"type": "head"}, {}, math.nan, 100)["verdict"] == "ACCEPT"


@pytest.mark.parametrize("fg,area", itertools.product([0, 5, 10 ** 6], [0, -5, 0.0]))
def test_zero_area_always_reject(fg, area):
    r = v.assess({"type": "head"}, {}, fg, area)
    assert r == {"verdict": "REJECT", "reason": "part region empty", "fg_ratio": 0.0}


def test_ratio_clamped_and_part_validated():
    assert v.assess({"type": "head"}, {}, 20000, 10000)["fg_ratio"] == 1.0
    with pytest.raises(ValueError):
        v.assess({}, {}, 1, 1)


@pytest.mark.parametrize("idx", [1.9, True, -1, "1"])
def test_part_cond_hash_rejects_non_int_index(idx):
    with pytest.raises(ValueError):
        cn.part_cond_hash("head", "abc", idx)


# ---------------------------------------------------------------- #138：非法声明不与未声明同桶
def test_invalid_value_not_same_identity_as_unasserted():
    base = {"subject": "人物", "style": "动漫"}
    assert cn.cond_hash({"subject": "人物"}) != cn.cond_hash({**base, "style": "油画"})
    assert cn.cond_hash({**base, "style": "油画"}) != cn.cond_hash({**base, "style": "水墨"})
    assert cn.cond_hash(base) == cn.cond_hash({**base, "style": " 动漫 "})
    for missing in ({"subject": "人物"}, {"subject": "人物", "style": None}, {"subject": "人物", "style": "  "},
                    {"subject": "人物", "style": cn.UNASSERTED}):
        assert cn.cond_hash(missing) == cn.cond_hash({"subject": "人物"})
    src = cn.canonical_sourced({**base, "style": "油画"})["style"]
    assert src["value"] == cn.UNASSERTED and src["invalid"] == "油画"
    assert cn.invalid_values({**base, "count": 3}) == {"count": "3"}
