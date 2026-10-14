"""rel-v1.25 postings.remove 原样（stab-r10 改为按位置切字节 + 前一块批量读之前），只作等价性对照。"""
import json
from typing import Dict, List, Tuple

from lingshu_ng.store.postings import BLOCK, _AT, _PUT, _chunks, _cur, decode, encode


def remove_v125(c, by_term):
    """P3：删除 {词元: {nkey}}。返回实际删掉的条数（调用方可据此核对）。须在写事务内调用。"""
    if not by_term:
        return 0
    pairs = [[t, k] for t in sorted(by_term) for k in sorted(by_term[t])]
    blocks: Dict[Tuple[str, int], tuple] = {}
    cur = _cur(c)
    for part in _chunks(pairs, 20000):
        for t, bno, n, nk, gr in cur.execute(_AT, (json.dumps(part, ensure_ascii=False),)):
            blocks[(t, bno)] = (n, nk, gr)
    removed = 0
    put: Dict[Tuple[str, int], Tuple[List[int], List[int]]] = {}
    for (t, bno) in sorted(blocks):
        n, nk, gr = blocks[(t, bno)]
        a, g = decode(n, nk, gr)
        drop = by_term[t]
        ks = [k for k in a if k not in drop]
        removed += n - len(ks)
        if len(ks) == n:
            continue
        gs = [x for k, x in zip(a, g) if k not in drop]
        put[(t, bno)] = (ks, gs)
    dels: List[Tuple[str, int]] = []
    for (t, bno) in sorted(put):
        ks, gs = put[(t, bno)]
        if not ks:
            dels.append((t, bno))
            continue
        if len(ks) < BLOCK // 4:
            prev = None                           # 紧邻的前一块（库里 bno < 本块的最大者；若本批改过则取改后内容）
            r = cur.execute("SELECT bno, n, nk, gr FROM term_blocks WHERE term=? AND bno<? ORDER BY bno DESC LIMIT 1",
                            (t, bno)).fetchone()
            if r is not None:
                if (t, r[0]) in put:
                    if put[(t, r[0])][0]:
                        prev = (r[0], put[(t, r[0])])
                else:
                    a, g = decode(r[1], r[2], r[3])
                    prev = (r[0], (list(a), list(g)))
            if prev is not None and len(prev[1][0]) + len(ks) <= BLOCK:
                pb, (pk, pg) = prev
                put[(t, pb)] = (pk + ks, pg + gs)
                put[(t, bno)] = ([], [])
                dels.append((t, bno))
    c.executemany("DELETE FROM term_blocks WHERE term=? AND bno=?", dels)
    c.executemany(_PUT, [(t, b) + encode(ks, gs) for (t, b), (ks, gs) in sorted(put.items()) if ks])
    return removed
