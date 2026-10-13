# -*- coding: utf-8 -*-
"""stab-r3 #3：lingshu-ng 发行包定义与版本号一致性。

发行包定义：Liyang/ 发布目录的 ``pyproject.toml``（name = lingshu-ng）；开发树里是 ``release/Liyang/pyproject.toml``。
版本号唯一来源 ``lingshu_ng.__version__``，须等于最新 ``CHANGELOG_rel-vX.Y.md`` 的 ``X.Y.0``。
真实安装验收（干净 venv、非 editable、换目录 import + 最小用例）见 tools/ci/pkg_check.sh。
"""
import ast
import pathlib
import re
import tomllib

import lingshu_ng

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _ng_pyproject():
    for p in (ROOT / "pyproject.toml", ROOT / "release" / "Liyang" / "pyproject.toml"):
        if p.exists():
            d = tomllib.loads(p.read_text(encoding="utf-8"))
            if d.get("project", {}).get("name") == "lingshu-ng":
                return d
    raise AssertionError("找不到 name = lingshu-ng 的 pyproject.toml")


def _names(specs):
    return {re.split(r"[<>=!~ ;\[]", s, 1)[0].strip().lower() for s in specs}


def test_version_single_source_and_changelog():
    pp = _ng_pyproject()
    assert "version" in pp["project"]["dynamic"] and "version" not in pp["project"]
    assert pp["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "lingshu_ng.__version__"}
    assert re.fullmatch(r"\d+\.\d+\.\d+", lingshu_ng.__version__)
    logs = [tuple(map(int, m.groups())) for f in ROOT.glob("CHANGELOG_rel-v*.md")
            if (m := re.fullmatch(r"CHANGELOG_rel-v(\d+)\.(\d+)\.md", f.name))]
    if logs:                                  # 发布目录 / wt-rel 有 CHANGELOG；最小副本可以没有
        major, minor = max(logs)
        assert lingshu_ng.__version__ == f"{major}.{minor}.0"


def test_extras_and_package_scope():
    pp = _ng_pyproject()
    assert pp["project"]["dependencies"] == []                       # 核心纯标准库
    ex = pp["project"]["optional-dependencies"]
    assert {"onnxruntime", "tokenizers", "numpy"} <= _names(ex["embed"])
    assert _names(ex["embed"]) | _names(ex["world"]) <= _names(ex["full"])
    find = pp["tool"]["setuptools"]["packages"]["find"]["include"]
    assert all(x.startswith("lingshu_ng") for x in find)             # 不把旧包副本 lingshu/ 打进发行包


def test_every_third_party_import_of_lingshu_ng_declared():
    declared = set().union(*(_names(v) for v in _ng_pyproject()["project"]["optional-dependencies"].values()))
    known = {"numpy": "numpy", "PIL": "pillow", "onnxruntime": "onnxruntime", "tokenizers": "tokenizers",
             "scipy": "scipy", "torch": "torch", "pyarrow": "pyarrow"}
    missing = set()
    for f in (ROOT / "lingshu_ng").rglob("*.py"):
        src = f.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else [])
            for m in mods:
                top = m.split(".")[0]
                if top in known and known[top] not in declared:
                    missing.add((str(f.relative_to(ROOT)), top))
        for top in re.findall(r"import_module\(\"(onnxruntime|tokenizers|numpy)\"\)", src):
            if known[top] not in declared:
                missing.add((str(f.relative_to(ROOT)), top))
    assert not missing, sorted(missing)


def test_every_subpackage_has_init():
    for d in (ROOT / "lingshu_ng").rglob("*"):
        if d.is_dir() and d.name != "__pycache__" and any(d.glob("*.py")):
            assert (d / "__init__.py").exists(), d
