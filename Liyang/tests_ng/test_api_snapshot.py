# -*- coding: utf-8 -*-
"""stab-r6 #4：公开 API 签名快照。公开名字 / 签名（参数名、种类、缺省值）/ 兼容门面支持状态与
``tests_ng/api_snapshot.json`` 不同就失败——按 docs/STABILITY_ng.md §3 升级版本号或在 CHANGELOG 中说明，
然后运行 ``python tools/ci/gen_api_appendix.py --snapshot`` 更新快照（该命令会检查放行规则）。"""
import importlib.util
import json
import os

import lingshu_ng

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("api_surface", os.path.join(ROOT, "tools", "ci", "api_surface.py"))
api_surface = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api_surface)
SNAP = os.path.join(ROOT, "tests_ng", "api_snapshot.json")


def _ver(v):
    return tuple(int(x) for x in v.split(".")[:3])


def test_public_api_matches_snapshot(monkeypatch):
    monkeypatch.delenv("LINGSHU_NG_STRICT_UNSUPPORTED", raising=False)
    snap = json.load(open(SNAP, encoding="utf-8"))
    d = api_surface.diff(snap["surface"], api_surface.surface())
    assert not any(d.values()), (
        "公开 API 签名与快照不同：" + json.dumps({k: v[:15] for k, v in d.items() if v}, ensure_ascii=False) +
        "\n⇒ 按 docs/STABILITY_ng.md §3：删除 / 改签名须升主版本号或在 CHANGELOG 逐个点名（并先走弃用流程），"
        "新增须升次版本号或在 CHANGELOG 点名；然后运行 python tools/ci/gen_api_appendix.py --snapshot 更新快照。")


def test_snapshot_version_not_ahead():
    """快照不能来自比代码更新的版本（防止旧代码配新快照）。"""
    snap = json.load(open(SNAP, encoding="utf-8"))
    assert _ver(snap["version"]) <= _ver(lingshu_ng.__version__)


def test_surface_diff_detects_changes():
    a = {"m.f": "(x)", "m.g": "(y=1)"}
    assert api_surface.diff(a, {"m.f": "(x, z=None)", "m.h": "()"}) == {"removed": ["m.g"], "added": ["m.h"], "changed": ["m.f"]}
    assert api_surface.sig(lambda a, *b, c=2, **d: 0) == "(a, *b, c=2, **d)"
    assert api_surface.sig(lambda a, *, c: 0) == "(a, *, c)"
