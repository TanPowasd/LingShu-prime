# -*- coding: utf-8 -*-
"""stab-r15：分词 / 二元组缓存改为紧凑表示后，对外结果与旧算法逐值相同（旧算法内联在此作参照）。"""
import random
import unicodedata

from lingshu_ng import dedup, lexical
from lingshu_ng.lexical import LexicalConfig, STOPWORDS, stem


def _old_tokens(text, use_stem, use_stop):
    t = unicodedata.normalize("NFKC", text).casefold().replace("\u2019", "'")
    out = []
    for m in lexical._run_re().finditer(t):
        cjk, lat = m.group(1), m.group(2)
        if cjk:
            out.extend([cjk] if len(cjk) == 1 else [cjk[i:i + 2] for i in range(len(cjk) - 1)])
        else:
            if use_stop and lat in STOPWORDS:
                continue
            w = stem(lat) if use_stem else lat
            if w and not (use_stop and w in STOPWORDS):
                out.append(w)
    return tuple(out)


def _old_bigrams(text):
    s = dedup.normalize(text)
    if len(s) <= 1:
        return frozenset({s}) if s else frozenset()
    return frozenset(s[i:i + 2] for i in range(len(s) - 1))


def _old_jaccard(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def _samples(n=3000, seed=15):
    rng = random.Random(seed)
    alpha = (list("abcdeésßİ'’ 　,.!?-_0123456789ＡＢｃ①ﬁⅫ\u00a0\t\n") + [chr(c) for c in range(0x4e00, 0x4e00 + 40)]
             + list("あいうアイウ가나다"))
    fixed = ["", " ", "a", "中", "中文", "中文字", "记忆系统 running tests, I'm 测试的结果", "The quick brown foxes jumped",
             "第3版 v2.1 发布了！Ｈｅｌｌｏ　世界", "x'y ’tis 中a文b字c"]
    return fixed + ["".join(rng.choice(alpha) for _ in range(rng.randint(0, 40))) for _ in range(n)]


def test_tokens_equal_old_algorithm_all_configs():
    for t in _samples():
        for st in (True, False):
            for sp in (True, False):
                got = lexical.tokens(t, LexicalConfig(stem=st, stop=sp))
                assert type(got) is tuple
                assert got == _old_tokens(t, st, sp), (t, st, sp)
                assert lexical.tokens(t, LexicalConfig(stem=st, stop=sp)) == got  # 缓存命中路径


def test_token_cache_value_is_compact_string():
    lexical._tokens.cache_clear()
    lexical.tokens("记忆系统 memory tests")
    v = lexical._tokens("记忆系统 memory tests", True, True)
    assert isinstance(v, str) and " " in v


def test_bigrams_jaccard_count_equal_old():
    xs = _samples(1500, seed=16)
    gs = [dedup.bigrams(t) for t in xs]
    for t, g in zip(xs, gs):
        assert type(g) is frozenset and g == _old_bigrams(t)
        assert dedup.bigram_count(t) == len(g)
    for i in range(len(gs) - 1):
        a, b = gs[i], gs[(i * 37 + 1) % len(gs)]
        for u, v in ((a, b), (list(a), set(b)), (tuple(a) * 2, b), (a, frozenset())):
            assert dedup.jaccard(u, v) == _old_jaccard(u, v)
    assert hasattr(dedup.bigrams, "cache_info") and hasattr(dedup.bigrams, "cache_clear")


def test_index_words_and_terms_of_equal_old():
    from lingshu_ng.store import textindex
    for t in _samples(1500, seed=17) + [None]:
        old_iw = sorted({lexical.WORD_PREFIX + w for w in _old_tokens(t or "", True, True) if not lexical._is_cjk_token(w)})
        assert lexical.index_words(t) == old_iw
        g = _old_bigrams(t or "")
        old_terms = sorted(set(g) | {textindex.TAG_PREFIX + x for x in ("a", "", "标签") if x} | set(old_iw))
        assert textindex.terms_of(t, ("a", "", "标签")) == (old_terms, len(g))
