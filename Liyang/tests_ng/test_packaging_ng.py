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


KNOWN = {"numpy": "numpy", "PIL": "pillow", "onnxruntime": "onnxruntime", "tokenizers": "tokenizers",
         "scipy": "scipy", "torch": "torch", "pyarrow": "pyarrow"}
PLUGINS = ("embed", "world", "nn", "gen")


def _plugin_pyproject(name):
    return tomllib.loads((ROOT / "plugins" / f"lingshu-ng-{name}" / "pyproject.toml").read_text(encoding="utf-8"))


def _imports(f):
    src = f.read_text(encoding="utf-8")
    out = set()
    for node in ast.walk(ast.parse(src)):
        mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                else [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else [])
        out |= {m.split(".")[0] for m in mods}
    out |= set(re.findall(r"import_module\(\"(onnxruntime|tokenizers|numpy|PIL)\"\)", src))
    return out


def test_core_package_zero_deps_no_extras():
    """split-r1（1.24）：核心 dependencies 为空、没有 optional-dependencies（第三方依赖只写在各插件包）；只打包 lingshu_ng。"""
    pp = _ng_pyproject()
    assert pp["project"]["dependencies"] == []                       # 核心纯标准库
    assert "optional-dependencies" not in pp["project"], pp["project"].get("optional-dependencies")
    find = pp["tool"]["setuptools"]["packages"]["find"]["include"]
    assert all(x.startswith("lingshu_ng") and not x.startswith("lingshu_ng_") for x in find)  # 不含旧包 lingshu/、不含插件包


def test_plugin_packages_declared():
    """四个插件包：各自 pyproject（name / 版本单一来源 / 入口点 lingshu_ng.plugins / 依赖核心 1.24+）、README、测试目录。"""
    for name in PLUGINS:
        d = ROOT / "plugins" / f"lingshu-ng-{name}"
        pp = _plugin_pyproject(name)
        top = f"lingshu_ng_{name}"
        assert pp["project"]["name"] == f"lingshu-ng-{name}"
        assert pp["tool"]["setuptools"]["dynamic"]["version"] == {"attr": f"{top}.__version__"}
        assert pp["project"]["entry-points"]["lingshu_ng.plugins"] == {name: f"{top}.plugin:PLUGIN"}
        assert any(s.replace(" ", "").startswith("lingshu-ng>=1.24") for s in pp["project"]["dependencies"])
        assert (d / "README.md").exists() and (d / f"tests_{name}").is_dir() and (d / "src" / top / "plugin.py").exists()
        m = re.search(r'^__version__ = "(\d+\.\d+\.\d+)"', (d / "src" / top / "__init__.py").read_text(encoding="utf-8"), re.M)
        assert m, top
    assert {"onnxruntime", "tokenizers", "numpy"} <= _names(_plugin_pyproject("embed")["project"]["dependencies"])
    assert "lingshu-ng-nn" in _names(_plugin_pyproject("gen")["project"]["dependencies"])


def test_every_third_party_import_declared_in_its_plugin():
    """每个插件源码里的第三方导入都写在该插件（或它依赖的插件）的 dependencies 里；核心一个都没有（见 test_core_zero_deps）。"""
    missing = set()
    for name in PLUGINS:
        pp = _plugin_pyproject(name)
        declared = _names(pp["project"]["dependencies"])
        for dep in [x for x in declared if x.startswith("lingshu-ng-")]:
            declared |= _names(_plugin_pyproject(dep[len("lingshu-ng-"):])["project"]["dependencies"])
        for f in (ROOT / "plugins" / f"lingshu-ng-{name}" / "src").rglob("*.py"):
            for top in _imports(f):
                if top in KNOWN and KNOWN[top] not in declared:
                    missing.add((str(f.relative_to(ROOT)), top))
    for f in (ROOT / "lingshu_ng").rglob("*.py"):
        for top in _imports(f):
            if top in KNOWN:
                missing.add((str(f.relative_to(ROOT)), top))
    assert not missing, sorted(missing)


def test_every_subpackage_has_init():
    for d in (ROOT / "lingshu_ng").rglob("*"):
        if d.is_dir() and d.name != "__pycache__" and any(d.glob("*.py")):
            assert (d / "__init__.py").exists(), d
