"""evalsuite_hard 适配层：记忆引擎复用 evalsuite/adapters.py（只读引用，不改），
世界/生成/网络模块按「旧模块名」统一取用：

  impl=legacy → lingshu.<pkg>.<mod>（快照里旧项目自己的模块）
  impl=ng     → lingshu_ng 的同名 compat 模块（nn: lingshu_ng.nn.compat.<mod>；
                world: lingshu_ng.world.compat.legacy_modules()[<mod>]）

两边取到的都是「旧 API 名字」，HARD 维度代码只按旧 API 调用，不对任何实现开特例。
缺模块 / 缺属性 → NA（计 0 分）。
"""
from __future__ import annotations

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVS = os.path.join(os.path.dirname(HERE), "evalsuite")
if EVS not in sys.path:
    sys.path.append(EVS)

from adapters import NA, Adapter, Mem, norm_node, submodule  # noqa: E402,F401


def legacy_mod(impl: str, pkg: str, name: str):
    """取旧模块名对应的实现模块。pkg ∈ {nn, world}。"""
    try:
        if impl == "legacy":
            return importlib.import_module(f"lingshu.{pkg}.{name}")
        if pkg == "nn":
            return importlib.import_module(f"lingshu_ng.nn.compat.{name}")
        if pkg == "world":
            comp = importlib.import_module("lingshu_ng.world.compat")
            mods = comp.legacy_modules()
            if name not in mods:
                raise NA(f"ng world 无 {name}")
            return mods[name]
    except NA:
        raise
    except Exception as ex:
        raise NA(f"import:{pkg}.{name}:{type(ex).__name__}:{ex}")
    raise NA(f"pkg:{pkg}")


def need(mod, name):
    try:
        return getattr(mod, name)
    except AttributeError:
        raise NA(f"missing:{getattr(mod, '__name__', mod)}.{name}")
