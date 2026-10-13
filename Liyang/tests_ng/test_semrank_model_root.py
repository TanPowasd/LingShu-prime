# -*- coding: utf-8 -*-
"""stab-r4：semrank 模型根目录不再缺省到作者开发机路径——env → ~/.cache/lingshu_ng/models，退到缺省时有可见 WARNING。"""
import logging
import os

from lingshu_ng import diag, semrank


def _reset(monkeypatch):
    monkeypatch.setattr(diag, "_FALLBACKS", {})
    monkeypatch.setattr(semrank, "_SCORERS", {})
    monkeypatch.setattr(semrank, "_EMBEDDERS", {})
    monkeypatch.setattr(semrank, "_REASONS", {})


def test_env_wins_no_warning(monkeypatch, tmp_path):
    _reset(monkeypatch)
    monkeypatch.setenv("LINGSHU_NG_SEM", str(tmp_path))
    assert semrank.model_root() == str(tmp_path)
    assert "sem_model_dir_default" not in diag.fallbacks()


def test_off_and_empty_mean_disabled(monkeypatch):
    _reset(monkeypatch)
    for v in ("off", ""):
        monkeypatch.setenv("LINGSHU_NG_SEM", v)
        assert semrank.get_scorer() is None
    assert "sem_model_dir_default" not in diag.fallbacks()


def test_unset_falls_back_to_user_cache_with_warning(monkeypatch, tmp_path, caplog):
    _reset(monkeypatch)
    monkeypatch.delenv("LINGSHU_NG_SEM", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    with caplog.at_level(logging.WARNING, logger="lingshu_ng"):
        d = semrank.model_root()
        semrank.model_root()
    assert d == os.path.join(str(tmp_path), ".cache", "lingshu_ng", "models")
    assert "/workspace/" not in d
    msg = diag.fallbacks()["sem_model_dir_default"]
    assert d in msg and "不存在" in msg
    assert sum("sem_model_dir_default" in r.getMessage() for r in caplog.records) == 1   # 进程内只打一次
    assert semrank.get_scorer() is None                                                 # 目录不存在 → 退回无模型路径
    assert d in (semrank.unavailable_reason("scorer") or "")


def test_unset_existing_default_dir_is_used(monkeypatch, tmp_path):
    _reset(monkeypatch)
    monkeypatch.delenv("LINGSHU_NG_SEM", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    d = tmp_path / ".cache" / "lingshu_ng" / "models"
    d.mkdir(parents=True)
    assert semrank.model_root() == str(d)
    assert "目录存在" in diag.fallbacks()["sem_model_dir_default"]


def test_no_dev_machine_path_in_package():
    root = os.path.dirname(semrank.__file__)
    bad = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith(".py"):
                p = os.path.join(dp, f)
                for i, line in enumerate(open(p, encoding="utf-8"), 1):
                    if "/workspace/work" in line and not line.lstrip().startswith("#"):
                        bad.append(f"{os.path.relpath(p, root)}:{i}")
    assert not bad, bad
