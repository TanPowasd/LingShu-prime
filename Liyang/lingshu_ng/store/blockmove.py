# -*- coding: utf-8 -*-
"""blockmove · 单节点换键/换词元的倒排改写（stab-r11）

:func:`move` ≡ :func:`postings.remove` 后接 :func:`postings.add`（同一节点的旧键/旧词元退出、新键/新词元进入），
结果（term_blocks 原始行：块切分、bno、字节）逐行相同，但只读一次所涉块、在内存里按两者的规则模拟、
只写出内容真正变了的块。晋升（提案加标签 → 终裁去标签）每步都是这种改写：同键去标签时绝大多数词元的
末块「删后又追加回原值」，不必再写。拒绝（返回 False）时一行未写，调用方走原路径。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from . import postings
from .postings import _PUT, _SWAP, _chunks, _cur, _drop, decode, encode
from .postings import _utf8

__all__ = ["move"]

_MVQ: Dict[int, str] = {}
#: move()：df（块条数之和；v6 为 term_df）不超过该值的词元整条读块（一条语句；df 只影响读法，不影响结果）
_MV_DF = 4 * postings.BLOCK
_MV_SMALL = ("WITH d(t, df) AS (SELECT j.value, (SELECT COALESCE(SUM(n), 0) FROM term_blocks WHERE term = j.value) "
             "FROM json_each(?2) j) SELECT d.t, d.df > ?1, b.bno, b.n, b.nk, b.gr FROM d LEFT JOIN term_blocks b "
             "ON b.term = d.t AND d.df <= ?1")


#: stab-r12 末块摘要（不读块字节）：bno / n / 窄编码与否 / 末键 / 末 grams / 紧邻前一块的 n
_TAIL = ("SELECT j.value, b.bno, b.n, length(b.nk) = 4 * b.n AND length(b.gr) IN (b.n, 2 * b.n), substr(b.nk, -4), "
         "substr(b.gr, -(length(b.gr) / b.n)), (SELECT p.n FROM term_blocks p WHERE p.term = j.value AND p.bno < b.bno ORDER BY p.bno DESC "
         "LIMIT 1) FROM json_each(?) j JOIN term_blocks b ON b.term = j.value AND b.bno = "
         "(SELECT bno FROM term_blocks WHERE term = j.value ORDER BY bno DESC LIMIT 1)")
#: stab-r12 删除侧：每个词元含待删键 ?1 的块（bno ≤ ?1 的最大者，同 postings._AT）与其紧邻前一块（前一块的字节只在
#: 本块 n ≤ ?3、即删后可能并入时才取）
_RM = ("SELECT j.value, b.bno, b.n, b.nk, b.gr, p.bno, p.n, CASE WHEN b.n <= ?3 THEN p.nk END, CASE WHEN b.n <= ?3 "
       "THEN p.gr END FROM json_each(?2) j JOIN term_blocks b ON b.term = j.value AND b.bno = (SELECT bno FROM "
       "term_blocks WHERE term = j.value AND bno <= ?1 ORDER BY bno DESC LIMIT 1) LEFT JOIN term_blocks p ON "
       "p.term = j.value AND p.bno = (SELECT bno FROM term_blocks WHERE term = j.value AND bno < b.bno "
       "ORDER BY bno DESC LIMIT 1)")
#: stab-r12 追加侧：同 postings._add_one（末块有空位 ⇒ 字节尾部拼接；无块 / 末块已满 ⇒ 以 bno = ?2 开新块），
#: 但末块有空位而为宽编码时**不写**（DO UPDATE 的 WHERE 不成立）——这类词元由调用方按 postings.add 的写法补上
_ADD = ("INSERT INTO term_blocks(term, bno, n, nk, gr) SELECT j.value, COALESCE((SELECT CASE WHEN n < ?1 THEN bno "
        "ELSE ?2 END FROM term_blocks WHERE term = j.value ORDER BY bno DESC LIMIT 1), ?2), 1, ?3, ?4 FROM json_each(?5) j "
        "WHERE 1 ON CONFLICT(term, bno) DO UPDATE SET n = n + 1, nk = CAST(nk || excluded.nk AS BLOB), "
        "gr = CAST(gr || CASE WHEN length(gr) = n THEN excluded.gr ELSE ?6 END AS BLOB) "
        "WHERE length(nk) = 4 * n AND length(gr) IN (n, 2 * n)")


def _tail_ok(bno: int, n: int, narrow: Any, lk: Any, lg: Any, pn: Optional[int], k: int, kb: bytes, g: int) -> bool:
    """:func:`_same_tail` 的摘要版（判定条件逐条相同）：只凭末块摘要判定「同键删后追加回原值、块不变」。"""
    if not narrow or bytes(lk) != kb or int.from_bytes(bytes(lg), "little") != g:
        return False
    if n == 1:
        return bno == k and (pn is None or pn >= postings.BLOCK)
    return n - 1 >= postings.BLOCK // 4 or pn is None or pn + n - 1 > postings.BLOCK


def _mv_sql(n: int) -> str:
    """每个 (词元, 待删键或 NULL)：含该键的块、其紧邻前一块、末块（去重）。"""
    sql = _MVQ.get(n)
    if sql is None:
        bk = "(SELECT bno FROM term_blocks WHERE term = k.t AND bno <= k.v ORDER BY bno DESC LIMIT 1)"
        sql = _MVQ[n] = ("WITH k(t, v) AS (VALUES " + ",".join(["(?,?)"] * n) + ") SELECT DISTINCT b.term, b.bno, b.n, "
                         "b.nk, b.gr FROM k JOIN term_blocks b ON b.term = k.t AND b.bno IN (" + bk + ", (SELECT bno FROM "
                         "term_blocks WHERE term = k.t AND bno < " + bk + " ORDER BY bno DESC LIMIT 1), (SELECT bno FROM "
                         "term_blocks WHERE term = k.t ORDER BY bno DESC LIMIT 1))")
    return sql


def _narrow(b: tuple) -> bool:
    return len(b[1]) == 4 * b[0] and len(b[2]) in (b[0], 2 * b[0])


def _same_tail(bl: Dict[int, tuple], k: int, g: int) -> bool:
    """同键删后追加回原值、块不变的常态：k 是末块（窄编码）的末键且 grams 未变，删后既不删空也不并入前一块。"""
    lb = max(bl)
    n, nk, gr = bl[lb]
    if not _narrow(bl[lb]) or nk[-4:] != k.to_bytes(4, "little") or int.from_bytes(gr[-(len(gr) // n):], "little") != g:
        return False
    prev = [b for b in bl if b < lb]
    pn = bl[max(prev)][0] if prev else None
    if n == 1:
        return lb == k and (pn is None or pn >= postings.BLOCK)
    return n - 1 >= postings.BLOCK // 4 or pn is None or pn + n - 1 > postings.BLOCK


def _mv_term(bl: Dict[int, tuple], ko: Optional[int], kn: Optional[int], g: int) -> bool:
    """在一个词元的已读块（含删除键所在块、其前一块、末块）上依次模拟 :func:`remove` 与 :func:`add` 的改写
    （合并、删空、开新块规则逐条相同）。遇到宽编码或追加键不大于末键 ⇒ False（调用方退回原路径）。"""
    if ko is not None and ko == kn and bl and _same_tail(bl, ko, g):
        return True
    if ko is not None:
        below = [b for b in bl if b <= ko]
        if below:
            bk = max(below)
            if not _narrow(bl[bk]):
                return False
            new = _drop(*bl[bk], {ko})
            if new[0] == 0:
                del bl[bk]
            elif new[0] != bl[bk][0]:
                prev = [b for b in bl if b < bk]
                pb = max(prev) if prev else None
                if 0 < new[0] < postings.BLOCK // 4 and pb is not None and bl[pb][0] + new[0] <= postings.BLOCK:
                    a, h = decode(*bl[pb])
                    b, i = decode(*new)
                    bl[pb] = encode(list(a) + list(b), list(h) + list(i))
                    del bl[bk]
                else:
                    bl[bk] = new
    if kn is None:
        return True
    ent = (1, kn.to_bytes(4, "little"), g.to_bytes(1, "little"))     # g < 256（调用方已保证）
    if not bl:
        bl[kn] = ent
        return True
    lb = max(bl)
    n, nk, gr = bl[lb]
    if not _narrow(bl[lb]) or (n and kn <= int.from_bytes(nk[-4:], "little")):
        return False
    bl[lb if n < postings.BLOCK else kn] = ((n + 1, nk + ent[1], gr + g.to_bytes(len(gr) // n, "little"))
                                            if n < postings.BLOCK else ent)
    return True


def _move_r11(c: Any, old_terms: Sequence[str], ko: int, new_terms: Sequence[str], kn: int, g: int) -> bool:
    """单个节点换键/换词元（stab-r11）：等价于 ``remove({t: {ko} for t in old_terms})`` 后接
    ``add({t: [(kn, g)] for t in new_terms})``，但一条语句读出所涉块、在内存里按两者的规则模拟、只写出内容真正变了的块
    （同键改标签时绝大多数词元的末块删后又追加回原字节，不再写）。前提同 :func:`add`：kn 大于删除后这些词元的全部键。
    返回 False 表示未做任何写入、调用方应走原路径（宽编码 / 超窄编码范围（grams ≥ 2^8）/ 前提不成立）。须在写事务内调用。"""
    if _SWAP or kn >= 1 << 32 or g >= 1 << 8:
        return False
    rm, ad = set(old_terms), set(new_terms)
    terms = sorted(rm | ad)
    orig: Dict[str, Dict[int, tuple]] = {}
    cur = _cur(c)
    big: List[str] = []
    for t, isbig, bno, n, nk, gr in cur.execute(_MV_SMALL, (_MV_DF, json.dumps(terms, ensure_ascii=False))):
        if isbig:                                 # 长倒排：只定位所需三块
            big.append(t)
        elif bno is not None:                     # 短倒排（df ≤ _MV_DF）：整条读出（块集是所需块的超集，模拟结果相同）
            orig.setdefault(t, {})[bno] = (n, nk, gr)
    for part in _chunks(big, 400):
        prm: List[Any] = []
        for t in part:
            prm += (t, ko if t in rm else None)
        for t, bno, n, nk, gr in cur.execute(_mv_sql(len(part)), prm):
            orig.setdefault(t, {})[bno] = (n, nk, gr)
    dels: List[Tuple[str, int]] = []
    put: List[tuple] = []
    for t in terms:
        o = orig.get(t, {})
        bl = dict(o)
        if not _mv_term(bl, ko if t in rm else None, kn if t in ad else None, g):
            return False
        dels.extend((t, b) for b in sorted(o) if b not in bl)
        put.extend((t, b) + v for b, v in sorted(bl.items()) if o.get(b) != v)
    if dels:
        c.executemany("DELETE FROM term_blocks WHERE term=? AND bno=?", dels)
    if put:
        c.executemany(_PUT, put)
    return True


def move(c: Any, old_terms: Sequence[str], ko: int, new_terms: Sequence[str], kn: int, g: int) -> bool:
    """单个节点换键/换词元（stab-r12）：等价于 ``remove({t: {ko} for t in old_terms})`` 后接
    ``add({t: [(kn, g)] for t in new_terms})``（term_blocks 原始行逐行相同），读写都只碰所需的块：

    1. 同键（ko == kn）且新旧都有的词元：一条语句取末块摘要（不读块字节），满足 :func:`_same_tail` 的
       「删后追加回原值、块不变」者两侧都跳过（r11 :func:`_move_r11` 读整块后同样判定为不写）；
    2. 删除侧一条语句（:data:`_RM`）：每个待删词元含 ko 的块与其前一块，按 :func:`postings.remove` 的规则
       （块内删键、删空即删块、删后不足 BLOCK/4 且放得下 ⇒ 并入紧邻前一块）算出要写的行并写出；
    3. 追加侧一条语句（:data:`_ADD`，在库内拼接末块，看到的是删除后的库）：与 :func:`postings.add` 的单键写法相同
       （无块 / 末块满 ⇒ bno = kn 开新块；有空位 ⇒ 尾部追加）；唯有「末块有空位而为宽编码」不写、按受影响行数
       发现后对这些词元调用 :func:`postings.add`（解码重编，同原路径）。

    前提同 :func:`postings.add`（P2）：kn 大于删除后这些词元的全部键（textindex 的换键取其余行最大 nkey + 1）。
    返回 False 表示未做任何写入、调用方应走原路径（键 ≥ 2^32 / grams ≥ 2^8（v7；v6 为 2^16）/ 大端）。须在写事务内调用。"""
    if _SWAP or kn >= 1 << 32 or g >= 1 << 8:
        return False
    rm, ad = set(old_terms), set(new_terms)
    cur = _cur(c)
    if ko == kn and rm & ad:
        kb = ko.to_bytes(4, "little")
        same = {r[0] for r in cur.execute(_TAIL, (json.dumps(sorted(rm & ad), ensure_ascii=False),))
                if _tail_ok(*r[1:], ko, kb, g)}
        rm -= same
        ad -= same
    dels, put = _rm_rows(cur, rm, ko) if rm else ([], [])
    if dels:
        c.executemany("DELETE FROM term_blocks WHERE term=? AND bno=?", dels)
    if put:
        c.executemany(_PUT, put)
    if ad:
        _append(c, cur, sorted(ad), kn, g)
    return True


def _rm_rows(cur: Any, rm: Set[str], ko: int) -> Tuple[List[tuple], List[tuple]]:
    """删除侧：每个词元含 ko 的块按 :func:`postings.remove` 的规则改写 ⇒ (要删的 (term, bno), 要写的整行)。"""
    low = postings.BLOCK // 4
    dels: List[tuple] = []
    put: List[tuple] = []
    for t, bno, n, nk, gr, pb, pn, pk, pg in cur.execute(_RM, (ko, json.dumps(sorted(rm), ensure_ascii=False), low)):
        new = _drop(n, nk, gr, {ko})
        if new[0] == n:
            continue
        if not new[0]:
            dels.append((t, bno))
        elif new[0] < low and pb is not None and pn + new[0] <= postings.BLOCK:
            a, h = decode(pn, pk, pg)
            b, i = decode(*new)
            put.append((t, pb) + encode(list(a) + list(b), list(h) + list(i)))
            dels.append((t, bno))
        else:
            put.append((t, bno) + new)
    return dels, put


def _append(c: Any, cur: Any, ts: List[str], kn: int, g: int) -> None:
    """追加侧：一条 :data:`_ADD`；按受影响行数发现「末块有空位而为宽编码」未写的词元，对它们调用 :func:`postings.add`。"""
    if not _utf8(c):
        postings.add(c, {t: [(kn, g)] for t in ts})
        return
    before = c.total_changes
    c.execute(_ADD, (postings.BLOCK, kn, kn.to_bytes(4, "little"), g.to_bytes(1, "little"),
                     json.dumps(ts, ensure_ascii=False), g.to_bytes(2, "little")))
    if c.total_changes - before == len(ts):
        return
    kb = kn.to_bytes(4, "little")
    got = {t for t, _, n, nk, gr in cur.execute(postings._LAST, (json.dumps(ts, ensure_ascii=False),))
           if _narrow((n, nk, gr)) and bytes(nk[-4:]) == kb}
    left = [t for t in ts if t not in got]
    if left:
        postings.add(c, {t: [(kn, g)] for t in left})
