# -*- coding: utf-8 -*-
"""上游老 issue 逐条复核（r4，#226 起）nn 段在 ng 上的回归测试。"""
import numpy as np

from lingshu_ng.nn import cards as K
from lingshu_ng.nn.cards import calibrate_class_cards, calibrate_hier_cards, four_state_classify


# ---- #254：校准集缺类 → 保守卡（missing，永不 ACCEPT）；层级卡缺类不给零原型/0 阈值 ----
def test_254_missing_class_card():
    rng = np.random.default_rng(0)
    logits = rng.normal(0, 1, (40, 10))
    y = rng.integers(0, 9, 40)                      # 缺类 9
    cards = calibrate_class_cards(logits, y, 10)
    assert [c["class"] for c in cards if c.get("missing")] == [9]
    logits[:, 9] += 50                              # 让类 9 绝对占优
    assert all(v["verdict"] != "ACCEPT" for v in four_state_classify(logits, cards))


def test_254_hier_missing_cards():
    rng = np.random.default_rng(1)
    n = 12
    feat, color = rng.normal(0, 1, (n, 8)), rng.normal(0, 1, (n, 3))
    logits = rng.normal(0, 1, (n, len(K.OBJ)))
    labels = {"shape": np.array([K.SHAPES[0]] * n), "color": np.array([K.COLORS[0]] * n),
              "obj": np.array([K.OBJ[0]] * n)}
    cards = calibrate_hier_cards(feat, color, logits, labels)
    assert sum(bool(c.get("missing")) for c in cards["shape"]) == len(K.SHAPES) - 1
    assert sum(bool(c.get("missing")) for c in cards["color"]) == len(K.COLORS) - 1
    assert sum(bool(c.get("missing")) for c in cards["obj"]) == len(K.OBJ) - 1
    assert all(c["p_q25"] is None for c in cards["obj"] if c.get("missing"))


def test_254_infogap_zero_steps():
    from lingshu_ng.nn.compat.hex_train import HexNet, train_infogap
    rng = np.random.default_rng(0)
    x, y = rng.normal(0, 1, (40, 6, 8, 1)), rng.integers(0, 9, 40)
    r = train_infogap(HexNet(), x, y, max_steps=0)
    assert r["steps"] == 0 and isinstance(r["final_D"], float)
