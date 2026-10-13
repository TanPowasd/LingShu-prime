# -*- coding: utf-8 -*-
"""可选依赖的稳健跳过（stab-r1）。

``pytest.importorskip`` 只把 ``ModuleNotFoundError`` 当「没装」处理；「装了但导入失败」（例如 Windows 上
onnxruntime 的 DLL 加载被拒，抛 ``ImportError``/``OSError``）会直接打断整个收集，把单文件的环境问题放大成
「一个测试都跑不了」。这里捕获导入期的任何异常并 skip，原因里带异常原文。
"""
import importlib

import pytest


def require(name: str):
    """导入可选依赖 ``name``；任何导入期异常 → skip（模块级或用例内均可调用）。返回模块对象。"""
    try:
        return importlib.import_module(name)
    except Exception as e:  # 第三方包导入期失败类型不可枚举：全部视为「此环境不可用」
        pytest.skip(f"可选依赖 {name} 不可用：{type(e).__name__}: {e}", allow_module_level=True)


def model_dir(*parts: str) -> str:
    """本地模型根目录（``LINGSHU_NG_SEM``，缺省同 :data:`lingshu_ng.semrank.DEFAULT_DIR`）下的子路径。"""
    import os

    from lingshu_ng import semrank
    return os.path.join(os.environ.get("LINGSHU_NG_SEM", semrank.DEFAULT_DIR).strip(), *parts)
