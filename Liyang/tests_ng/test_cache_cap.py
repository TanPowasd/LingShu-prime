# -*- coding: utf-8 -*-
"""stab-r11：进程内缓存上限可由环境变量调（LINGSHU_NG_TOKEN_CACHE / _BIGRAM_CACHE / _NORM_CACHE），非法值退缺省并告警。"""
import os
import subprocess
import sys

from lingshu_ng.diag import cache_cap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_cache_cap_parse(monkeypatch, caplog):
    monkeypatch.delenv("LS_T_CAP", raising=False)
    assert cache_cap("LS_T_CAP", 7) == 7
    monkeypatch.setenv("LS_T_CAP", " 0 ")
    assert cache_cap("LS_T_CAP", 7) == 0
    monkeypatch.setenv("LS_T_CAP", "-3")
    with caplog.at_level("WARNING", logger="lingshu_ng"):
        assert cache_cap("LS_T_CAP", 7) == 7
    assert "LS_T_CAP" in caplog.text


def test_env_sets_lru_sizes():
    env = dict(os.environ, LINGSHU_NG_TOKEN_CACHE="64", LINGSHU_NG_BIGRAM_CACHE="0", LINGSHU_NG_NORM_CACHE="5",
               PYTHONPATH=ROOT)
    out = subprocess.run([sys.executable, "-c", "import lingshu_ng.lexical as l, lingshu_ng.dedup as d; "
                          "print(l._tokens.cache_info().maxsize, d.bigrams.cache_info().maxsize, d.normalize.cache_info().maxsize, "
                          "sorted(d.bigrams('记忆视觉')) == ['忆视', '视觉', '记忆'])"],
                         env=env, capture_output=True, text=True, check=True).stdout.split()
    assert out == ["64", "0", "5", "True"]
