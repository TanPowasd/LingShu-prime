# -*- coding: utf-8 -*-
"""lingshu-ng-embed 插件测试（split-r1，rel-v1.24）：被核心发现、旧导入路径委托到插件、带模型时与核心缓存路径逐位一致。"""
import os

import pytest

from _plugin_testutil import model_dir, require

import lingshu_ng_embed
from lingshu_ng import plugins, semrank
from lingshu_ng.capabilities import capabilities


def test_plugin_discovered_with_version():
    plugins.refresh()
    info = plugins.installed().get("embed")
    assert info is not None and info["error"] is None, plugins.installed()
    assert info["version"] == lingshu_ng_embed.__version__ and info["distribution"] == "lingshu-ng-embed"
    assert info["source"] in ("entry_point", "source_tree")
    assert set(info["provides"]) == {"cross_backend", "dense_embedder", "disc_head", "onnx_embedder", "onnx_cross_encoder"}
    assert capabilities()["plugins"]["embed"]["version"] == lingshu_ng_embed.__version__


def test_old_import_paths_resolve_to_plugin_classes():
    from lingshu_ng.embed import OnnxEmbedder
    from lingshu_ng.embed.cross import OnnxCrossEncoder
    from lingshu_ng_embed.cross import OnnxCrossEncoder as C2
    from lingshu_ng_embed.onnx_embed import OnnxEmbedder as E2
    from lingshu_ng_embed.semrank_backend import CrossBackend, DenseEmbedder, DiscHead
    assert OnnxEmbedder is E2 and OnnxCrossEncoder is C2
    assert semrank.DenseEmbedder is DenseEmbedder and semrank.DiscHead is DiscHead
    assert DenseEmbedder.INST == semrank.DENSE_INST
    assert plugins.provider("cross_backend") is CrossBackend


def test_plugin_import_loads_no_third_party_until_used():
    import subprocess
    import sys
    code = ("import sys, lingshu_ng_embed.plugin, lingshu_ng_embed.onnx_embed, lingshu_ng_embed.cross, "
            "lingshu_ng_embed.semrank_backend\n"
            "print([m for m in ('numpy', 'onnxruntime', 'tokenizers') if m in sys.modules])\n")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "[]"


def _scorer_or_skip():
    require("onnxruntime")
    require("tokenizers")
    semrank._SCORERS.clear()
    sc = semrank.get_scorer()
    if sc is None:
        pytest.skip(f"交叉编码模型不可用：{semrank.unavailable_reason('scorer')}")
    return sc


def test_cross_scorer_backend_matches_cache_path(tmp_path, monkeypatch):
    """核心缓存 / 取整路径的分数 = 后端前向 round(float(v), 5)；冷缓存与热缓存逐位相同。"""
    monkeypatch.setenv("LINGSHU_NG_SEM_CACHE", str(tmp_path / "c"))
    sc = _scorer_or_skip()
    q = "快递柜的取件码在哪里看"
    ps = ["快递柜取件码可在公众号查看。", "红烧肉先焯水。", "取件码忘了可以在柜机上重发。"]
    cold = sc.score(q, ps)
    raw = [round(float(v), 5) for v in sc._be.logits(q, ps)]
    assert cold == raw
    semrank._SCORERS.clear()
    assert semrank.get_scorer().score(q, ps) == cold           # 新单例：从磁盘缓存读回
    assert cold[0] > cold[1]


def test_dense_embedder_with_model():
    require("onnxruntime")
    em = semrank.get_embedder()
    if em is None:
        pytest.skip(f"稠密模型不可用：{semrank.unavailable_reason('dense')}")
    z = semrank.dense_z("取件码忘了", ["快递柜取件码可在公众号查看。", "红烧肉先焯水。"])
    assert len(z) == 2 and z[0] > z[1]


def test_model_dir_helper():
    assert model_dir("x").endswith(os.sep + "x")
