# -*- coding: utf-8 -*-
"""stab-r13：冷 import 守卫——``import lingshu_ng.compat`` 不载入存储层 / 检索层 / 可选依赖。

``SpacetimeMemoryEngine`` 的构造函数才用到 :class:`lingshu_ng.engine.MemoryEngine`（连带约 40 个模块与 sqlite3）；
``lingshu_ng.compat`` 旧版顶层再导出的其余名字改为首次属性访问时载入（PEP 562），取到的是同一对象。
在独立子进程里检查（测试进程本身早已载入这些模块）。"""
import importlib
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: ``import lingshu_ng.compat`` 之后不得出现在 sys.modules 里的模块（前缀匹配：名字本身或其子模块）
HEAVY = (
    "lingshu_ng.engine", "lingshu_ng.store", "lingshu_ng.retrieval", "lingshu_ng.lexical", "lingshu_ng.assoc",
    "lingshu_ng.conflict", "lingshu_ng.causal", "lingshu_ng.graphquery", "lingshu_ng.compat_store",
    "lingshu_ng.self_model", "lingshu_ng.negative", "lingshu_ng.skills", "lingshu_ng.insight", "lingshu_ng.decay",
    "lingshu_ng.exchange", "lingshu_ng.scheduler", "lingshu_ng.semindex", "lingshu_ng.semrank", "lingshu_ng.rerank",
    "lingshu_ng.headrank", "lingshu_ng.densefuse", "lingshu_ng.expansion", "lingshu_ng.cooc", "lingshu_ng.lexpath",
    "lingshu_ng.embed", "lingshu_ng.chain", "lingshu_ng.perception",
    "sqlite3", "numpy", "onnxruntime", "tokenizers",
)

_PROBE = r"""
import json, sys
import lingshu_ng.compat
print(json.dumps(sorted(sys.modules)))
"""


def _modules_after(code: str):
    env = dict(os.environ, PYTHONPATH=ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""))
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_import_compat_does_not_load_heavy_modules():
    mods = _modules_after(_PROBE)
    bad = [m for m in mods if any(m == h or m.startswith(h + ".") for h in HEAVY)]
    assert not bad, f"import lingshu_ng.compat 载入了重模块：{bad}"
    assert "lingshu_ng.compat_engine" in mods


def test_constructing_engine_loads_them():
    code = _PROBE.replace("print(", "e = lingshu_ng.compat.SpacetimeMemoryEngine(); e.close(); print(")
    mods = _modules_after(code)
    for m in ("lingshu_ng.engine", "lingshu_ng.store", "lingshu_ng.retrieval", "lingshu_ng.compat_store", "sqlite3"):
        assert m in mods


def test_lazy_names_resolve_to_same_objects():
    compat = importlib.import_module("lingshu_ng.compat")
    for name, (sub, attr) in compat._LAZY.items():
        mod = importlib.import_module("lingshu_ng." + sub)
        assert getattr(compat, name) is (mod if attr is None else getattr(mod, attr)), name
        assert name in dir(compat)
    ns = {}
    exec("from lingshu_ng.compat import *", ns)
    for name in compat.__all__:
        assert ns[name] is getattr(compat, name)
    with pytest.raises(AttributeError):
        compat.no_such_name


def test_consts_are_the_same_objects():
    from lingshu_ng import _consts, compat_engine, compat_store, exchange, self_model
    assert exchange.TABLES is _consts.TABLES is compat_engine.SpacetimeMemoryEngine.M13_TABLES
    assert self_model.SNAPSHOT_KEEP == 200 == compat_engine.SpacetimeMemoryEngine.SELF_SNAPSHOT_MAX
    assert compat_store.CAUSAL_MAX_PATHS == 1000
