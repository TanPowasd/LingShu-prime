# -*- coding: utf-8 -*-
"""v7.1 交叉编码打分：问句本身超过 max_len 个 token 时不崩（stab-r5b）。

rel-v1.19 及以前 tokenizers 的 only_second 截断在「问句已超 max_len」时抛 ``Truncation error``，
limit > 15 的中文长请求随之崩溃（tests_ng/test_input_safety.py 模糊测试在带模型环境下发现）。
修复只在这种情形下截问句（经 recall 的端到端覆盖见 test_input_safety.py 的模糊测试）；其余输入的分词结果须与直接 ``encode_batch`` 逐位相同。缺模型 / 缺依赖 → skip。
"""
import os

import pytest

from tests_ng._optdeps import model_dir, require


def _scorer(monkeypatch):
    """不读写磁盘分数缓存的新打分件（否则命中缓存就测不到分词）。"""
    require("onnxruntime")
    require("tokenizers")
    if not os.path.exists(model_dir("bge-reranker-base", "tokenizer.json")):
        pytest.skip("缺 bge-reranker-base 模型件")
    from lingshu_ng import semrank
    monkeypatch.setenv("LINGSHU_NG_SEM_CACHE", "")
    monkeypatch.setattr(semrank, "_SCORERS", {})
    sc = semrank.get_scorer()
    if sc is None:
        pytest.skip(f"打分件不可用：{semrank.unavailable_reason()}")
    return sc


def test_normal_pairs_tokenize_identically(monkeypatch):
    sc = _scorer(monkeypatch)
    q = "猫喜欢吃什么鱼"
    ps = ["猫喜欢吃鱼。" * 80, "狗喜欢啃骨头", ""]
    a = sc.encode_pairs(q, ps)
    b = sc.tok.encode_batch([(q, p) for p in ps])
    assert [e.ids for e in a] == [e.ids for e in b]


def test_overlong_query_scores_without_error(monkeypatch):  # 旧版：Truncation error
    sc = _scorer(monkeypatch)
    assert sc.cache_dir is None
    q = "青" * (sc.max_len + 50)
    out = sc.score(q, ["青色的天空", "一段无关的文字"])
    assert len(out) == 2 and all(isinstance(x, float) for x in out)

