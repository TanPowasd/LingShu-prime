# -*- coding: utf-8 -*-
"""compat · 旧 ``lingshu.nn.<mod>`` 的同名适配（底层全部走 lingshu_ng.nn / lingshu_ng.gen）。

覆盖旧 tests/test_hex_*.py、test_stcnn_*.py、test_rust_bridge_plan.py 实际调用的 API：
hex_cnn / hex_train / hex_hier / hex_text / hex_search / hex_gen / hex_composite / hex_ortho /
hex_recon / stcnn / rust_bridge。

``install_legacy_aliases()`` 把这些模块注册到 ``sys.modules['lingshu.nn.<mod>']`` 并挂到
``lingshu.nn`` 包属性上（``import lingshu.nn.hex_gen as hg`` 与 ``from lingshu.nn.hex_gen import x``
都命中 compat）。旧源码与旧断言零改动。

有意的行为差异（旧行为是缺陷）见各模块 docstring 与 BENCH_NN.md。
"""
from __future__ import annotations

import importlib
import sys
from typing import List

MODULES = ("hex_cnn", "hex_train", "hex_hier", "hex_text", "hex_search", "hex_gen", "hex_composite",
           "hex_ortho", "hex_recon", "stcnn", "rust_bridge")


#: 旧 ``lingshu.gen`` 下的纯重导出 shim → 同一个 compat 模块（旧契约：gen 侧与 nn 侧是同一对象）。
#: 其余 ``lingshu.gen.hexgen_*`` 是带语料 / 命令行入口的研究脚本，ng 只迁了算法核（lingshu_ng.gen.
#: pack_certify / multi_seed / align_probe，函数名与旧脚本不一一对应），不装别名，见 INTENT_FIDELITY.md。
GEN_SHIMS = {"hex_composite": "hex_composite"}


def install_legacy_aliases() -> List[str]:
    """注册别名，返回已安装的旧模块名列表。"""
    pkg = importlib.import_module("lingshu.nn")
    done = []
    for name in MODULES:
        mod = importlib.import_module(f"{__name__}.{name}")
        sys.modules[f"lingshu.nn.{name}"] = mod
        setattr(pkg, name, mod)
        done.append(f"lingshu.nn.{name}")
    try:
        gen = importlib.import_module("lingshu.gen")
    except ImportError:          # 旧树无 gen 子包（上游早期形态）：只装 nn
        return done
    for old, new in GEN_SHIMS.items():
        mod = importlib.import_module(f"{__name__}.{new}")
        sys.modules[f"lingshu.gen.{old}"] = mod
        setattr(gen, old, mod)
        done.append(f"lingshu.gen.{old}")
    return done
