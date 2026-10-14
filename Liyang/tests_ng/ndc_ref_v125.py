"""rel-v1.25 近重复候选实现原样（stab-r10 拆出 store/neardup.py 前的 TextIndex.near_duplicate_candidates 主体），
只作等价性对照：tests_ng/test_neardup_r10.py 与 _stab/r10 规模核对用。"""
import math
from typing import Dict


def ndc_v125(ti, grams, threshold):
    """与 rel-v1.25 逐行相同的算法（ti 为 TextIndex；调用方已 flush）。"""
    if not grams:
        return set()
    a = len(grams)
    need = max(1, math.ceil(threshold * a - 1e-9))
    dfs = ti.df(grams)
    if len(dfs) < need:
        return set()
    order = sorted(grams, key=lambda g: (dfs.get(g, 0), g))
    r = a - need + 1
    lo = math.floor(threshold * a * (1 - 1e-9))
    hi = math.ceil(a / threshold * (1 + 1e-9))
    cnt: Dict[int, int] = {}
    nb: Dict[int, int] = {}
    for g in order[:r]:
        if dfs.get(g, 0) <= 0:
            continue
        for k, n in ti.postings_len(g, lo, hi):
            cnt[k] = cnt.get(k, 0) + 1
            nb[k] = n
    t1 = threshold / (1.0 + threshold) * (1 - 1e-9)
    req = {k: (max(need, math.ceil(t1 * (a + n))) if n else need) for k, n in nb.items()}
    done = r
    for g in order[r:]:
        left = a - done
        dead = [k for k, c in cnt.items() if c + left < req[k]]
        for k in dead:
            del cnt[k]
        if not cnt:
            break
        d = dfs.get(g, 0)
        if d > 0:
            if d <= len(cnt):
                got = [k for k in ti.postings(g) if k in cnt]
            else:
                got = ti.members(g, sorted(cnt))
            for k in got:
                cnt[k] += 1
        done += 1
    keep = [k for k, c in cnt.items() if c >= req[k]]
    return set(ti.node_ids(keep).values())
