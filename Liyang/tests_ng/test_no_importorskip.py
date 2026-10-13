# -*- coding: utf-8 -*-
"""stab-r5c：tests_ng 内不得直接用 ``pytest.importorskip`` 导入可选依赖。

它只把 ``ModuleNotFoundError`` 当「没装」；「装了但导入失败」（Windows 上 onnxruntime DLL 被拒抛 ``ImportError``）
会变成 failed。rel-v1.20 草稿里 test_examples.py 正因此在 DLL 坏环境 1 failed。统一改用 tests_ng._optdeps.require。
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PAT = re.compile(r"\bimportorskip\s*\(")


def test_no_direct_importorskip():
    bad = []
    for d, _, fs in os.walk(HERE):
        if "__pycache__" in d or "_envsim" in d:
            continue
        for f in fs:
            if not f.endswith(".py") or f in ("_optdeps.py", "test_no_importorskip.py"):
                continue
            p = os.path.join(d, f)
            for i, line in enumerate(open(p, encoding="utf-8"), 1):
                if PAT.search(line) and not line.lstrip().startswith("#"):
                    bad.append(f"{os.path.relpath(p, HERE)}:{i}")
    assert not bad, "改用 tests_ng._optdeps.require：" + ", ".join(bad)
