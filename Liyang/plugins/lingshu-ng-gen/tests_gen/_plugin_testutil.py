# -*- coding: utf-8 -*-
"""插件测试的可选依赖稳健跳过（同 tests_ng/_optdeps.py：导入期任何异常 ⇒ skip，原因带异常原文）。"""
import importlib

import pytest


def require(name: str):
    """导入可选依赖 ``name``；任何导入期异常 → skip（模块级或用例内均可调用）。返回模块对象。"""
    try:
        return importlib.import_module(name)
    except Exception as e:  # 第三方包导入期失败类型不可枚举：全部视为「此环境不可用」
        pytest.skip(f"可选依赖 {name} 不可用：{type(e).__name__}: {e}", allow_module_level=True)
