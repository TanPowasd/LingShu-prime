# -*- coding: utf-8 -*-
"""gen r10 F3L：写入时顺带保存的逐词向量与查询时现算逐位相同；MaxSim 分数逐位相同；预算 0 时退回现算；LRU 守字节预算。"""
import os

import pytest

from tests_ng._optdeps import model_dir, require

MD = os.environ.get("LINGSHU_NG_TOKVEC_MODEL", model_dir("bge-small-en-v1.5"))
require("onnxruntime")   # 装了但原生库加载失败（Windows DLL 拒绝）也 skip，不打断收集
require("tokenizers")
if not os.path.exists(os.path.join(MD, "model_quantized.onnx")):
    pytest.skip("bge-small-en-v1.5 不在本机", allow_module_level=True)

from lingshu_ng.embed import OnnxEmbedder  # noqa: E402

TEXTS = ["I adopted a beagle named Max last spring.", "Sure! Here are three tips:\n1. Hydrate\n2. Sleep\n3. Stretch",
         "ok", "What did you recommend for my sister's birthday?"]


@pytest.fixture(autouse=True)
def _nocache(monkeypatch):
    monkeypatch.delenv("LINGSHU_NG_EMBED_CACHE", raising=False)
    monkeypatch.delenv("LINGSHU_NG_EMBED_TOKVEC_MB", raising=False)


def test_precomputed_equals_fresh(monkeypatch):
    a = OnnxEmbedder(MD)
    a.add([f"n{i}" for i in range(len(TEXTS))], TEXTS)
    assert all(t in a._tokc for t in TEXTS)
    monkeypatch.setenv("LINGSHU_NG_EMBED_TOKVEC_MB", "0")
    b = OnnxEmbedder(MD)
    assert b.tok_budget == 0
    b.add([f"n{i}" for i in range(len(TEXTS))], TEXTS)
    assert not b._tokc
    for t in TEXTS:
        assert a.token_vecs(t).tobytes() == b.token_vecs(t).tobytes()
    q = "what pet did I adopt?"
    assert a.maxsim(q, TEXTS) == b.maxsim(q, TEXTS)
    assert (a.mat.tobytes() == b.mat.tobytes())          # 句向量不受影响


def test_lru_budget(monkeypatch):
    monkeypatch.setenv("LINGSHU_NG_EMBED_TOKVEC_MB", "0.02")   # ≈ 20 KB：只容得下一两条
    a = OnnxEmbedder(MD)
    a.add([f"n{i}" for i in range(len(TEXTS))], TEXTS)
    assert 1 <= len(a._tokc) < len(TEXTS)
    assert a._tokbytes <= a.tok_budget or len(a._tokc) == 1
    assert a._tokbytes == sum(v.nbytes for v in a._tokc.values())


def test_prefetch_bitwise(monkeypatch):
    """F3P：召回时后台预取查询向量 / MaxSim 逐词向量，名次与分数与不预取逐位相同。"""
    from lingshu_ng import densefuse
    from lingshu_ng.engine import MemoryEngine
    docs = TEXTS + ["My sister loves adventure biographies.", "You recommended 'Into Thin Air' for her birthday.",
                    "The weather in Boston was rainy all week.", "I moved into my new apartment on May 3rd."]
    qs = ["What book did you recommend for my sister?", "when did I move into my apartment", "rainy Boston week"]

    import random
    import time
    monkeypatch.setattr(time, "time", lambda: 1.7e9)     # recency 项依赖墙钟：钉住后只比较检索逻辑（同 bench 的 clockshim）

    def run():
        rng = random.Random(1)
        monkeypatch.setattr(os, "urandom", lambda n: rng.randbytes(n))
        e = MemoryEngine(":memory:")
        e.auto_conflicts = False
        e.set_lexical(sf=1, sf_w=2.0, sf_k=10, sf_n=60, sf_qp=2, sf_mx=1, sf_mxn=20)
        e.set_embedding_provider(OnnxEmbedder(MD))
        for d in docs:
            e.perceive(d)
        out = [[(n.content, s) for n, s in e.recall(q, 6)["hits"]] for q in qs]
        e.close()
        return out

    a = run()
    monkeypatch.setattr(densefuse, "prefetch", lambda r, q: None)
    assert run() == a


def test_blas1_bitwise(monkeypatch):
    """F3T：单线程 BLAS 下的 MaxSim 与多线程逐位相同。"""
    import lingshu_ng.embed as E
    a = OnnxEmbedder(MD)
    a.add([f"n{i}" for i in range(len(TEXTS))], TEXTS)
    q = "what pet did I adopt for my sister?"
    on = a.maxsim(q, TEXTS)
    monkeypatch.setattr(E, "_BLAS", False)
    off = a.maxsim(q, TEXTS)
    assert on == off
    import numpy as np
    rng = np.random.default_rng(0)
    qm = rng.standard_normal((17, 384)).astype(np.float32)
    ds = [rng.standard_normal((int(n), 384)).astype(np.float32) for n in rng.integers(1, 300, 30)]
    plain = [(qm @ d.T).tobytes() for d in ds]
    monkeypatch.setattr(E, "_BLAS", None)
    with E._Blas1():
        one = [(qm @ d.T).tobytes() for d in ds]
    assert plain == one
