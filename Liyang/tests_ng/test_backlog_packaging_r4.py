# -*- coding: utf-8 -*-
"""上游老 issue 逐条复核（r4）packaging 段：#237 license 用 SPDX 字符串；#253 extras 覆盖包内第三方 import。"""
import ast
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PP = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
MAP = {"numpy": "numpy", "PIL": "pillow", "scipy": "scipy", "pyarrow": "pyarrow", "torch": "torch",
       "diffusers": "diffusers"}


def _names(spec_list):
    import re
    return {re.split(r"[<>=!~ ;\[]", s, 1)[0].strip().lower() for s in spec_list}


def test_237_license_is_spdx_string():
    assert isinstance(PP["project"]["license"], str) and PP["project"]["license"] == "MIT"
    req = PP["build-system"]["requires"][0]
    assert req.replace(" ", "").startswith("setuptools>=") and int(req.split(">=")[1].split(".")[0]) >= 77


def test_253_world_extra_has_pillow():
    assert "pillow" in _names(PP["project"]["optional-dependencies"]["world"])


def test_253_every_third_party_import_declared():
    extras = PP["project"]["optional-dependencies"]
    declared = set().union(*(_names(v) for v in extras.values()))
    missing = set()
    for pkg in ("lingshu_ng", "lingshu"):
        for f in (ROOT / pkg).rglob("*.py"):
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                        else [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level
                        else [])
                for m in mods:
                    top = m.split(".")[0]
                    if top in MAP and MAP[top] not in declared:
                        missing.add((str(f.relative_to(ROOT)), top))
    assert not missing, sorted(missing)
