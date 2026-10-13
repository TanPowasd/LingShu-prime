# -*- coding: utf-8 -*-
"""split-r1（rel-v1.24）：插件发现 / 显式注册 / 缺插件退回 / 旧导入路径兼容。"""
import json
import os
import subprocess
import sys
import types as _types

import pytest

from lingshu_ng import diag, plugins, semrank
from lingshu_ng.capabilities import capabilities

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakeBackend:
    """确定性假后端：logit = 段落长度 − 问句长度/10（未取整，核心负责 round(…, 5)）。"""

    def __init__(self, mdir, onnx_name, model="m"):
        self.tag = f"{model}/{onnx_name}/fake"
        self.calls = 0
        self.max_len = 7

    def encode_pairs(self, q, ps):
        return [(q, p) for p in ps]

    def logits(self, q, ps):
        self.calls += 1
        return [len(p) - len(q) / 10 + 1e-7 for p in ps]


class _FakePlugin:
    name = "embed"
    distribution = "lingshu-ng-embed-fake"
    version = "0.0.1"
    dependencies = ()
    provides = {"cross_backend": _FakeBackend}


def _no_plugins(monkeypatch):
    monkeypatch.setattr(plugins, "_discover_external", lambda: {})
    plugins.refresh()


def _model_tree(tmp_path, model="bge-reranker-base", onnx="model_quantized.onnx"):
    d = tmp_path / model
    (d / "onnx").mkdir(parents=True)
    (d / "tokenizer.json").write_text("{}", encoding="utf-8")
    (d / "onnx" / onnx).write_bytes(b"")
    return tmp_path


def test_protocols_are_stdlib_typing_protocols():
    import typing
    for P in (plugins.Plugin, plugins.CrossScorerBackend, plugins.DenseEmbedderProtocol,
              plugins.EmbeddingProvider, plugins.CrossEncoder):
        assert typing.Protocol in P.__mro__
    assert isinstance(_FakeBackend("d", "x"), plugins.CrossScorerBackend)
    assert isinstance(_FakePlugin(), plugins.Plugin)


def test_explicit_register_drives_cross_scorer(tmp_path, monkeypatch):
    _no_plugins(monkeypatch)
    plugins.register(_FakePlugin())
    monkeypatch.setenv("LINGSHU_NG_SEM", str(_model_tree(tmp_path)))
    monkeypatch.setenv("LINGSHU_NG_SEM_CACHE", str(tmp_path / "cache"))
    semrank._SCORERS.clear()
    sc = semrank.get_scorer()
    assert isinstance(sc, semrank.CrossScorer) and sc.tag.endswith("/fake")
    assert sc.max_len == 7                                           # 后端属性经 CrossScorer 照旧可读
    a = sc.score("问句", ["一", "二三", "四五六"])
    assert a == [round(len(p) - 0.2 + 1e-7, 5) for p in ["一", "二三", "四五六"]]
    n = sc._be.calls
    assert sc.score("问句", ["二三", "一"]) == [a[1], a[0]] and sc._be.calls == n   # 内存缓存命中，不再前向
    info = capabilities()["plugins"]["embed"]
    assert info["source"] == "register" and info["version"] == "0.0.1" and info["error"] is None
    assert capabilities()["models"]["cross_scorer"]["available"] is True
    assert plugins.unregister("embed") and not plugins.unregister("embed")


def test_missing_plugin_falls_back_with_one_warning(tmp_path, monkeypatch, caplog):
    _no_plugins(monkeypatch)
    diag.reset()
    monkeypatch.setenv("LINGSHU_NG_SEM", str(_model_tree(tmp_path)))
    semrank._SCORERS.clear()
    semrank._EMBEDDERS.clear()
    with caplog.at_level("WARNING"):
        assert semrank.get_scorer() is None
        assert semrank.get_embedder() is None
        semrank._SCORERS.clear()
        assert semrank.get_scorer() is None
    reason = semrank.unavailable_reason("scorer")
    assert "pip install lingshu-ng-embed" in reason
    fb = diag.fallbacks()
    assert "plugin_missing:embed" in fb and "pip install lingshu-ng-embed" in fb["plugin_missing:embed"]
    assert sum("plugin_missing:embed" in r.getMessage() for r in caplog.records) == 1
    c = capabilities()
    assert c["plugins"] == {} and c["dependencies"] == {} and c["semantic_tier"] == "v4"
    with pytest.raises(ImportError, match="pip install lingshu-ng-embed"):
        from lingshu_ng.embed import OnnxEmbedder  # noqa: F401
    with pytest.raises(plugins.PluginMissingError, match="lingshu-ng-embed"):
        from lingshu_ng.embed.cross import OnnxCrossEncoder  # noqa: F401
    with pytest.raises(ImportError, match="lingshu-ng-embed"):
        semrank.DenseEmbedder
    from lingshu_ng.embed import split_sentences          # 纯标准库部分不需要插件
    assert split_sentences("第一句很长很长很长很长很长很长很长很长很长很长。第二句也很长很长很长很长很长很长很长很长很长。")


def test_entry_point_discovery_and_broken_entry(monkeypatch):
    import importlib.metadata as md

    class _EP:
        def __init__(self, name, obj=None, err=None):
            self.name, self.value, self._obj, self._err = name, f"x.{name}:PLUGIN", obj, err

        def load(self):
            if self._err:
                raise self._err
            return self._obj

    good = _types.SimpleNamespace(name="demo", distribution="lingshu-ng-demo", version="9.9.9",
                                  provides={"demo_cap": "json:dumps"}, dependencies=("json",))
    eps = [_EP("demo", obj=lambda: good), _EP("bad", err=ImportError("boom"))]
    monkeypatch.setattr(md, "entry_points", lambda group=None: eps if group == plugins.GROUP else [])
    monkeypatch.setattr(plugins._alias, "source_plugin_paths", lambda: [])
    plugins.refresh()
    got = plugins.installed()
    assert got["demo"]["source"] == "entry_point" and got["demo"]["version"] == "9.9.9"
    assert got["bad"]["error"] == "ImportError: boom"
    assert plugins.provider("demo_cap") is json.dumps      # "模块:属性" 字符串按需导入
    assert plugins.provider("no_such_cap") is None
    assert capabilities()["dependencies"]["json"]["available"] is True


def _run(code, **env):
    e = dict(os.environ, PYTHONPATH=REPO, PYTHONDONTWRITEBYTECODE="1", **env)
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=e, cwd=REPO)


def test_old_subpackage_paths_without_plugins_give_install_hint():
    code = ("import json\n"
            "out = {}\n"
            "for m in ('lingshu_ng.world', 'lingshu_ng.world.voxel', 'lingshu_ng.nn.compat', 'lingshu_ng.gen'):\n"
            "    try:\n"
            "        __import__(m)\n"
            "        out[m] = 'imported'\n"
            "    except ModuleNotFoundError as e:\n"
            "        out[m] = str(e)\n"
            "import os, tempfile\n"
            "from lingshu_ng.compat import SpacetimeMemoryEngine\n"
            "c = SpacetimeMemoryEngine(os.path.join(tempfile.mkdtemp(), 'c.db'))\n"
            "out['world3d'] = c.world3d('status', {})['status']\n"
            "c.close()\n"
            "print(json.dumps(out, ensure_ascii=False))\n")
    r = _run(code, LINGSHU_NG_SOURCE_PLUGINS="0")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    for m, dist in (("lingshu_ng.world", "lingshu-ng-world"), ("lingshu_ng.world.voxel", "lingshu-ng-world"),
                    ("lingshu_ng.nn.compat", "lingshu-ng-nn"), ("lingshu_ng.gen", "lingshu-ng-gen")):
        assert f"pip install {dist}" in out[m], out
    assert out["world3d"] == "world3d_not_ready"


def test_source_tree_plugins_keep_old_module_identity():
    """源码树里插件可见时：旧路径照常导入，模块名 / __module__ 与 1.22 相同，且与插件目录的文件是同一份。"""
    code = ("import json, lingshu_ng\n"
            "from lingshu_ng import plugins\n"
            "import lingshu_ng.world.voxel as v, lingshu_ng.nn.render as r, lingshu_ng.gen.verify as g\n"
            "print(json.dumps({'v': v.__name__, 'cls': v.VoxelWorld.__module__, 'file': v.__file__, 'r': r.__name__,\n"
            "                  'g': g.__name__, 'src': {k: i['source'] for k, i in plugins.installed().items()}}))\n")
    r = _run(code)
    if r.returncode != 0 and "numpy" in r.stderr:
        pytest.skip("本环境无 numpy：world / nn / gen 插件不可导入")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["v"] == out["cls"] == "lingshu_ng.world.voxel"
    assert out["r"] == "lingshu_ng.nn.render" and out["g"] == "lingshu_ng.gen.verify"
    assert os.path.join("plugins", "lingshu-ng-world", "src", "lingshu_ng_world") in out["file"]
    assert set(out["src"]) >= {"embed", "world", "nn", "gen"}


def test_import_lingshu_ng_stays_light():
    """import lingshu_ng 不触发插件发现（不读入口点、不扫源码树）、不载入任何第三方库。"""
    r = _run("import sys, lingshu_ng, lingshu_ng.engine\n"
             "bad = [m for m in ('numpy', 'onnxruntime', 'tokenizers', 'PIL', 'lingshu_ng.plugins', 'importlib.metadata') if m in sys.modules]\n"
             "print(bad)\n")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "[]"
