# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""汇总 bench_cc 读数；G/CC+G 按给定 τ 事后组合（τ 只在 dev 上选）。用法：python agg_cc.py <lme json...> -- <locomo json> [--tau x]"""
import json, math, sys


def load(fs):
    per = []
    for f in fs:
        per += json.load(open(f, encoding="utf-8"))["per"]
    return per


def gate(p, tau, a="Lex"):
    return p["arms"][a + "/单"] if p["s"] >= tau else p["arms"][a]


def mean(P, f, k="r@10"):
    return sum(f(p)[k] for p in P) / len(P)


def sign(w, l):
    n = w + l
    return 1.0 if n == 0 else min(1, 2 * sum(math.comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n)


def wl(P, fa, fb, k="r@10"):
    w = sum(fa(p)[k] > fb(p)[k] for p in P); l = sum(fa(p)[k] < fb(p)[k] for p in P)
    return w, l, sign(w, l)
