"""stab-r5：examples/ 下的最小示例必须能直接运行（子进程、干净的工作目录、只靠本仓 PYTHONPATH）。
示例 3 在零模型档（LINGSHU_NG_SEM=off）总要跑；本机有模型件时再按缺省档跑一遍。"""
import os
import subprocess
import sys

import pytest

from tests_ng._optdeps import require

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples")


def _run(name, **env):
    e = dict(os.environ, PYTHONPATH=ROOT, PYTHONDONTWRITEBYTECODE="1")
    e.pop("LINGSHU_NG_CHAIN", None)
    e.update(env)
    p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(EX, name)], env=e, cwd=os.path.dirname(ROOT),
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-2000:]
    return p.stdout


def test_example_list():
    assert sorted(f for f in os.listdir(EX) if f.endswith(".py")) == [
        "01_basic_memory.py", "02_chinese_dialogue.py", "03_semantic_bge.py"]


def test_basic_memory():
    out = _run("01_basic_memory.py")
    assert "merged" in out and "reopened:" in out


def test_chinese_dialogue():
    out = _run("02_chinese_dialogue.py")
    assert "版本链现值： 周四下午三点" in out


def test_semantic_example_without_models():
    out = _run("03_semantic_bge.py", LINGSHU_NG_SEM="off")
    assert "semantic_tier: v4" in out and "零模型档" in out


def test_semantic_example_with_models():
    from lingshu_ng import semrank
    root = semrank.model_root(warn=False)
    if not root or root == "off" or not os.path.isfile(os.path.join(root, "bge-reranker-base", "tokenizer.json")):
        pytest.skip("本机无 bge-reranker-base 模型件")
    require("onnxruntime")  # 不用 pytest.importorskip：它只认 ModuleNotFoundError，装了但 DLL 加载失败会变成 failed
    require("tokenizers")
    out = _run("03_semantic_bge.py", LINGSHU_NG_SEM=root)
    assert "semantic_tier: v7.1" in out or "semantic_tier: v11c" in out
