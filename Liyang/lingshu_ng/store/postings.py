# -*- coding: utf-8 -*-
"""postings · 倒排分块 blob（schema v5，stab-r7）

``term_blocks(term, bno, n, nk, gr)``（WITHOUT ROWID，主键 (term, bno)）：一个词元的倒排按节点整数键 nkey 升序切成块，
每块至多 :data:`BLOCK` 条；``nk`` = nkey 数组（小端 uint32，超出时 uint64），``gr`` = 对应节点的正文二元组数
（小端 uint16，超出时 uint32），``n`` = 条数（据此判定两列宽度）。v4 的 ``node_terms(term, nkey, grams)`` 每条一行，
本表一块一行——体积约省一半（stab-r6 原型 SIZE_PROTO：100k 库倒排 127 → 67 MB）、整条倒排一次读出。

不变量：
  P1 同一词元的块按 bno 升序覆盖互不相交、递增的 nkey 区间；``bno ≤`` 块内最小 nkey，下一块的 bno > 本块最大 nkey。
     因此「按 bno 顺序拼接各块」= 该词元全部 (nkey, grams) 按 nkey 升序，与 v4 ``SELECT … WHERE term=? ORDER BY nkey`` 逐行相同。
  P2 新键只追加（textindex 分配的 nkey 恒大于现存全部键）：写入只改各词元的最后一块（未满则补满、满则开新块）。
     万一追加键不大于末块最大键（不应发生），退回整条词元合并重写——结果仍满足 P1。
  P3 删除按 (词元, nkey) 定位到「bno ≤ nkey 的最大块」改写；改空即删行；改后不足 BLOCK/4 且与前一块合计不超过
     BLOCK 时并入前一块（定期合并，避免删改多的库留下大量碎块）。块的切分方式随历史而异，但 P1 下读出结果只取决于内容。

本模块只做块的编解码与读改写；何时增删、计数（term_df/feature_df）怎么改由 :mod:`lingshu_ng.store.textindex` 决定。
"""
from __future__ import annotations

import array
import json
import struct
from bisect import bisect_left
import sys
from bisect import bisect_right
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

__all__ = ["BLOCK", "BlockCache", "encode", "decode", "read", "read_arrays", "read_many", "members", "members_multi", "add", "add_node", "remove", "count", "all_postings", "check"]

#: 每块最多条数（stab-r6 原型：块 128 时单块 ≤ 768 字节，落在 WITHOUT ROWID 索引 B 树单格本地载荷上限内、无溢出页）
BLOCK = 128
_SWAP = sys.byteorder == "big"            # 块内一律小端存储（库文件跨字节序可移植）
_LAST = ("SELECT b.term, b.bno, b.n, b.nk, b.gr FROM json_each(?) j JOIN term_blocks b ON b.term = j.value AND b.bno = "
         "(SELECT bno FROM term_blocks WHERE term = j.value ORDER BY bno DESC LIMIT 1)")
_AT = ("SELECT DISTINCT b.term, b.bno, b.n, b.nk, b.gr FROM json_each(?) j JOIN term_blocks b "
       "ON b.term = json_extract(j.value, '$[0]') AND b.bno = (SELECT bno FROM term_blocks "
       "WHERE term = json_extract(j.value, '$[0]') AND bno <= json_extract(j.value, '$[1]') ORDER BY bno DESC LIMIT 1)")
_PUT = "INSERT OR REPLACE INTO term_blocks(term, bno, n, nk, gr) VALUES (?,?,?,?,?)"
#: members()：键数不超过该值时只读含这些键的块（逐键定位），否则读整条倒排
_SEEK_MAX = 48


def _arr(code: str, vals: Iterable[int]) -> bytes:
    a = array.array(code, vals)
    if _SWAP:
        a.byteswap()
    return a.tobytes()


def encode(nks: Sequence[int], grs: Sequence[int]) -> Tuple[int, bytes, bytes]:
    """(n, nk, gr)：键与二元组数各自取能容纳全部值的最窄宽度。"""
    nk = _arr("I" if not nks or max(nks) < 1 << 32 else "Q", nks)
    gr = _arr("H" if not grs or max(grs) < 1 << 16 else "I", grs)
    return len(nks), nk, gr


def _un(code: str, raw: bytes) -> array.array:
    a = array.array(code)
    a.frombytes(raw)
    if _SWAP:
        a.byteswap()
    return a


def decode(n: int, nk: bytes, gr: bytes) -> Tuple[array.array, array.array]:
    """块 → (nkey 数组, grams 数组)。"""
    if not n:
        return array.array("I"), array.array("H")
    return (_un("I" if len(nk) == 4 * n else "Q", nk), _un("H" if len(gr) == 2 * n else "I", gr))


def _cur(conn: Any) -> Any:
    cur = conn.cursor()
    cur.row_factory = None
    return cur


def read(conn: Any, term: str) -> Tuple[List[int], List[int]]:
    """单个词元的整条倒排：(nkey 升序列表, 对应 grams 列表)。"""
    ks, gs = read_arrays(conn, term)
    return ks.tolist(), gs.tolist()


def read_arrays(conn: Any, term: str) -> Tuple[array.array, array.array]:
    """:func:`read` 的数组版（内容逐值相同）：各块都是窄编码时拼接字节一次解码（常态），否则逐块解码后拼接。"""
    rows = _cur(conn).execute("SELECT n, nk, gr FROM term_blocks WHERE term=? ORDER BY bno", (term,)).fetchall()
    if all(len(nk) == 4 * n and len(gr) == 2 * n for n, nk, gr in rows):
        return _un("I", b"".join([r[1] for r in rows])), _un("H", b"".join([r[2] for r in rows]))
    ks, gs = array.array("Q"), array.array("I")
    for n, nk, gr in rows:
        a, g = decode(n, nk, gr)
        ks.fromlist(a.tolist())
        gs.fromlist(g.tolist())
    return ks, gs


def read_many(conn: Any, terms: Sequence[str]) -> List[Tuple[str, int, int]]:
    """若干词元的倒排行 [(词元, nkey, grams)]，按 (词元, nkey) 升序（与 v4 ``term IN (…)`` 的主键序相同）。"""
    out: List[Tuple[str, int, int]] = []
    if not terms:
        return out
    for t, n, nk, gr in _cur(conn).execute(
            "SELECT b.term, b.n, b.nk, b.gr FROM term_blocks b WHERE b.term IN (SELECT value FROM json_each(?)) "
            "ORDER BY b.term, b.bno", (json.dumps(list(terms), ensure_ascii=False),)):
        a, g = decode(n, nk, gr)
        out.extend(zip([t] * len(a), a, g))
    return out


def members(conn: Any, term: str, keys: Sequence[int], cache: "Optional[BlockCache]" = None) -> List[int]:
    """keys 中含该词元的节点（升序）。键少时逐键定位所在块（只读这些块），否则读整条倒排求交。"""
    if not keys:
        return []
    want = set(keys)
    if len(want) <= _SEEK_MAX:
        return [k for _, k in members_multi(conn, [term], keys, cache)]
    return sorted(want.intersection(read(conn, term)[0]))


#: members_multi()：词元数 × 键数不超过该值时一条语句逐 (词元, 键) 定位块，否则逐词元处理
_SEEK_PAIRS = 4096


def members_multi(conn: Any, terms: Sequence[str], keys: Sequence[int],
                  cache: "Optional[BlockCache]" = None) -> List[Tuple[str, int]]:
    """[(词元, nkey)]：keys 中含 terms 任一项的 (词元, 节点) 对，按 (词元, nkey) 升序（每对只出现一次）。
    词元 × 键不多时**一条语句**把每个 (词元, 键) 定位到「bno ≤ 键的最大块」并去重读块（与 v4 主键逐对点查同阶），
    否则逐词元：键少则同样定位、键多则读整条倒排求交。"""
    if not terms or not keys:
        return []
    want = set(keys)
    ts = list(dict.fromkeys(terms))
    out: List[Tuple[str, int]] = []
    if len(ts) * len(want) > _SEEK_PAIRS and len(want) > _SEEK_MAX:
        for t in sorted(ts):
            out.extend((t, k) for k in sorted(want.intersection(read(conn, t)[0])))
        return out
    if len(ts) * len(want) > _SEEK_PAIRS:
        for t in sorted(ts):
            out.extend(members_multi(conn, [t], keys, cache))
        return out
    if cache is not None and not conn.in_transaction:
        return cache.members_multi(conn, ts, sorted(want))
    pairs = [(t, k) for t in ts for k in sorted(want)]
    cur = _cur(conn)
    for part in _chunks(pairs, _PAIRS_STMT):
        prm: List[Any] = []
        for t, k in part:
            prm += (t, k, struct.pack("<I" if k < 1 << 32 else "<Q", k))
        # 每行 = 一个 (词元, 键) 及其所在块；instr 在块字节里找键的小端编码 = 必要条件预筛（键在块里 ⇒ 其字节必出现），
        # 只把可能命中的块交给 Python，块内再二分精确判定
        for t, k, n, nk in cur.execute(_members_sql(len(part)), prm):
            a = _keys(n, nk)
            i = bisect_left(a, k)
            if i < n and a[i] == k:
                out.append((t, k))
    out.sort()
    return out


#: 一条 members 语句最多带的 (词元, 键) 对（每对 3 个参数，低于旧版 SQLite 的 999 变量上限）
_PAIRS_STMT = 300
_MSQL: Dict[int, str] = {}


def _members_sql(n: int) -> str:
    sql = _MSQL.get(n)
    if sql is None:
        sql = _MSQL[n] = ("WITH k(t, v, kb) AS (VALUES " + ",".join(["(?,?,?)"] * n) + ") "
                          "SELECT k.t, k.v, b.n, b.nk FROM k JOIN term_blocks b ON b.term = k.t AND b.bno = "
                          "(SELECT bno FROM term_blocks WHERE term = k.t AND bno <= k.v ORDER BY bno DESC LIMIT 1) "
                          "WHERE instr(b.nk, k.kb) > 0")
    return sql


_INF = float("inf")
#: 块定位语句：每个 (词元, 键) 取「bno ≤ 键的最大块」（可无）及「bno > 键的最小块号」（可无）——
#: 二者确定该键所在的半开区间 [块 bno 或 −1, 下一块 bno 或 +∞)，区间内任何键的成员判定都只看这一块
_LOC: Dict[int, str] = {}


def _loc_sql(n: int) -> str:
    sql = _LOC.get(n)
    if sql is None:
        sql = _LOC[n] = ("WITH k(t, v) AS (VALUES " + ",".join(["(?,?)"] * n) + ") "
                         "SELECT k.t, k.v, b.bno, b.n, b.nk, (SELECT bno FROM term_blocks WHERE term = k.t AND bno > k.v "
                         "ORDER BY bno LIMIT 1) FROM k LEFT JOIN term_blocks b ON b.term = k.t AND b.bno = "
                         "(SELECT bno FROM term_blocks WHERE term = k.t AND bno <= k.v ORDER BY bno DESC LIMIT 1)")
    return sql


class BlockCache:
    """members_multi 的块缓存（stab-r8）：一次检索的判定精排对同一批剩余词元反复点查成千上万个 (词元, 键)，
    落在的块却只有几十到几百个（100k 中文长请求实测每题 8–255 块 / 300–7600 对）。缓存按词元记已读块的
    半开键区间 [lo, hi) 与块内键序列，区间内的键直接在内存二分判定，未覆盖的键才一条语句定位读块。

    有效性令牌 = (本连接 total_changes, PRAGMA data_version, PRAGMA schema_version)：本连接任何增删改（含触发器）、
    其他连接提交、表结构变化都会使令牌改变 → 整体清空；显式事务内（可能回滚）不读不写缓存。
    判定结果与无缓存路径逐对相同（同一不变量 P1 下的同一块）。"""

    MAX_BLOCKS = 4096

    def __init__(self) -> None:
        self.tok: Any = None
        self.iv: Dict[str, Tuple[List[float], List[float], List[Any]]] = {}
        self.nb = 0

    def clear(self) -> None:
        """清空缓存（令牌一并作废）。"""
        self.iv.clear()
        self.nb = 0
        self.tok = None

    def _check(self, conn: Any) -> None:
        tok = (conn.total_changes,) + tuple(_cur(conn).execute(
            "SELECT * FROM pragma_data_version, pragma_schema_version").fetchone())
        if tok != self.tok:
            self.iv.clear()
            self.nb = 0
            self.tok = tok

    def _put(self, t: str, lo: float, hi: float, a: Any) -> None:
        e = self.iv.get(t)
        if e is None:
            e = self.iv[t] = ([], [], [])
        i = bisect_left(e[0], lo)
        if i < len(e[0]) and e[0][i] == lo:
            return
        e[0].insert(i, lo)
        e[1].insert(i, hi)
        e[2].insert(i, a)
        self.nb += 1

    def members_multi(self, conn: Any, ts: Sequence[str], ks: Sequence[int]) -> List[Tuple[str, int]]:
        """ts 去重词元、ks 升序去重键：[(词元, nkey)] 按 (词元, nkey) 升序。"""
        self._check(conn)
        if self.nb > self.MAX_BLOCKS:
            self.iv.clear()
            self.nb = 0
        out: List[Tuple[str, int]] = []
        miss: List[Tuple[str, int]] = []
        for t in ts:
            e = self.iv.get(t)
            if e is None:
                miss.extend((t, k) for k in ks)
                continue
            los, his, arrs = e
            for k in ks:
                i = bisect_right(los, k) - 1
                if i >= 0 and k < his[i]:
                    a = arrs[i]
                    j = bisect_left(a, k)
                    if j < len(a) and a[j] == k:
                        out.append((t, k))
                else:
                    miss.append((t, k))
        if miss:
            cur = _cur(conn)
            for part in _chunks(miss, _PAIRS_STMT):
                prm: List[Any] = []
                for t, k in part:
                    prm += (t, k)
                for t, k, bno, n, nk, nx in cur.execute(_loc_sql(len(part)), prm).fetchall():
                    hi = _INF if nx is None else nx
                    if bno is None:
                        self._put(t, -1, hi, ())
                        continue
                    a = _keys(n, nk)
                    self._put(t, bno, hi, a)
                    j = bisect_left(a, k)
                    if j < n and a[j] == k:
                        out.append((t, k))
        out.sort()
        return out


def _keys(n: int, nk: bytes) -> Any:
    """块的 nkey 序列（小端机上零拷贝 memoryview，否则解码）。"""
    if _SWAP or len(nk) != 4 * n:
        return _un("I" if len(nk) == 4 * n else "Q", nk)
    return memoryview(nk).cast("I")


def count(conn: Any) -> int:
    """倒排总条数。"""
    return int(_cur(conn).execute("SELECT COALESCE(SUM(n), 0) FROM term_blocks").fetchone()[0])


def all_postings(conn: Any) -> Dict[str, List[Tuple[int, int]]]:
    """全部倒排 {词元: [(nkey, grams)]}（诊断/测试用）。"""
    out: Dict[str, List[Tuple[int, int]]] = {}
    for t, n, nk, gr in _cur(conn).execute("SELECT term, n, nk, gr FROM term_blocks ORDER BY term, bno"):
        a, g = decode(n, nk, gr)
        out.setdefault(t, []).extend(zip(a, g))
    return out


def _chunks(seq: Sequence, size: int) -> Iterable[Sequence]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _rewrite_term(c: Any, term: str, extra: Sequence[Tuple[int, int]]) -> List[tuple]:
    """P2 退路：整条词元与新条目合并（同键以新值为准）后按 BLOCK 重新切块。返回待写行（已删旧行）。"""
    ks, gs = read(c, term)
    m = dict(zip(ks, gs))
    m.update(extra)
    c.execute("DELETE FROM term_blocks WHERE term=?", (term,))
    ents = sorted(m.items())
    return [(term, ch[0][0]) + _pack_ents(ch) for ch in _chunks(ents, BLOCK)]


def _pack_ents(ents: Sequence[Tuple[int, int]]) -> Tuple[int, bytes, bytes]:
    return encode([k for k, _ in ents], [g for _, g in ents])


def add(c: Any, by_term: Dict[str, List[Tuple[int, int]]]) -> None:
    """P2：把 {词元: [(nkey, grams)]（nkey 升序）} 追加进各词元末块。须在写事务内调用。
    常态（末块为窄编码、新值放得下）直接在块字节尾部拼接新条目的小端编码，不解码整块。"""
    if not by_term:
        return
    terms = list(by_term)
    last: Dict[str, tuple] = {}
    cur = _cur(c)
    for i in range(0, len(terms), 20000):
        for t, bno, n, nk, gr in cur.execute(_LAST, (json.dumps(terms[i:i + 20000], ensure_ascii=False),)):
            last[t] = (bno, n, nk, gr)
    upd: List[tuple] = []
    ins: List[tuple] = []
    for t in terms:
        ents = by_term[t]
        lb = last.get(t)
        if lb is not None:
            bno, n, nk, gr = lb
            narrow = len(nk) == 4 * n and len(gr) == 2 * n
            if n and ents[0][0] <= (int.from_bytes(nk[-4:], "little") if narrow else decode(n, nk, gr)[0][-1]):
                ins.extend(_rewrite_term(c, t, ents))
                continue
            room = BLOCK - n
            if room > 0:
                take, ents = ents[:room], ents[room:]
                if narrow and take[-1][0] < 1 << 32 and max(g for _, g in take) < 1 << 16 and not _SWAP:
                    upd.append((n + len(take), nk + _arr("I", [k for k, _ in take]),
                                gr + _arr("H", [g for _, g in take]), t, bno))
                else:
                    a, g = decode(n, nk, gr)
                    upd.append(encode(list(a) + [k for k, _ in take], list(g) + [x for _, x in take]) + (t, bno))
        for i in range(0, len(ents), BLOCK):
            ch = ents[i:i + BLOCK]
            ins.append((t, ch[0][0]) + _pack_ents(ch))
    if upd:
        c.executemany("UPDATE term_blocks SET n=?, nk=?, gr=? WHERE term=? AND bno=?", upd)
    if ins:
        c.executemany(_PUT, ins)


_ENC: Dict[int, bool] = {}


def _utf8(c: Any) -> bool:
    """库编码是否 UTF-8（``CAST(a || b AS BLOB)`` 对任意字节逐字节拼接只在 UTF-8 库成立；UTF-16 库走 Python 路径）。"""
    v = _ENC.get(id(c))
    if v is None:
        v = _ENC[id(c)] = str(c.execute("PRAGMA encoding").fetchone()[0]).upper() == "UTF-8"
    return v


def add_node(c: Any, terms: List[str], k: int, g: int) -> None:
    """一个节点（nkey k、grams g）进入这些词元的倒排（单条写入的常态，等价于 ``add({t: [(k, g)]})``）。"""
    if not terms:
        return
    if k < 1 << 32 and g < 1 << 16 and not _SWAP and _utf8(c):
        _add_one(c, terms, k, g)
    else:
        add(c, {t: [(k, g)] for t in terms})


def _add_one(c: Any, terms: List[str], k: int, g: int) -> None:
    """一个节点（同一 nkey/grams）进入多个词元的倒排：**一条语句**完成（单条写入的常态）。末块未满且为窄编码
    ⇒ 字节尾部拼接（ON CONFLICT 原位更新）；否则（无块 / 末块已满 / 宽编码）以 bno = nkey 开新块。
    前提（P2）：k 大于这些词元现存的全部键——textindex 分配的新 nkey 恒为最大值，墓碑已先行清除。"""
    c.execute("INSERT INTO term_blocks(term, bno, n, nk, gr) SELECT j.value, COALESCE((SELECT CASE WHEN n < ? "
              "AND length(nk) = 4 * n AND length(gr) = 2 * n THEN bno ELSE ? END FROM term_blocks WHERE term = j.value "
              "ORDER BY bno DESC LIMIT 1), ?), 1, ?, ? FROM json_each(?) j WHERE 1 "
              "ON CONFLICT(term, bno) DO UPDATE SET n = n + 1, nk = CAST(nk || excluded.nk AS BLOB), "
              "gr = CAST(gr || excluded.gr AS BLOB)",
              (BLOCK, k, k, k.to_bytes(4, "little"), g.to_bytes(2, "little"), json.dumps(terms, ensure_ascii=False)))


_PREV: Dict[int, str] = {}


def _prev_sql(n: int) -> str:
    sql = _PREV.get(n)
    if sql is None:
        sql = _PREV[n] = ("WITH k(t, v) AS (VALUES " + ",".join(["(?,?)"] * n) + ") SELECT k.t, k.v, b.bno, b.n, b.nk, b.gr "
                          "FROM k JOIN term_blocks b ON b.term = k.t AND b.bno = (SELECT bno FROM term_blocks "
                          "WHERE term = k.t AND bno < k.v ORDER BY bno DESC LIMIT 1)")
    return sql


def _drop(n: int, nk: bytes, gr: bytes, drop: Set[int]) -> Tuple[int, bytes, bytes]:
    """块删去 drop 中的键 → 新块 (n, nk, gr)，与「解码 → 过滤 → :func:`encode`」逐字节相同。窄编码块（常态）删后仍窄，
    直接按键位置切字节（键在块内升序，二分定位）；宽编码块解码重编（删后可能变窄）。"""
    if len(nk) == 4 * n and len(gr) == 2 * n and not _SWAP:
        a = memoryview(nk).cast("I")
        if len(drop) <= 16:
            pos = []
            for k in drop:
                i = bisect_left(a, k)
                if i < n and a[i] == k:
                    pos.append(i)
        else:                                     # 批量删除（大量墓碑）：逐条扫块，免 |drop| × 块数次二分
            pos = [i for i, k in enumerate(a) if k in drop]
        if not pos:
            return n, nk, gr
        pos.sort()
        bk, bg, last = [], [], 0
        for i in pos:
            bk.append(nk[4 * last:4 * i])
            bg.append(gr[2 * last:2 * i])
            last = i + 1
        bk.append(nk[4 * last:])
        bg.append(gr[2 * last:])
        return n - len(pos), b"".join(bk), b"".join(bg)
    a, g = decode(n, nk, gr)
    keep = [i for i, k in enumerate(a) if k not in drop]
    if len(keep) == n:
        return n, nk, gr
    return encode([a[i] for i in keep], [g[i] for i in keep])


def remove(c: Any, by_term: Dict[str, Set[int]]) -> int:
    """P3：删除 {词元: {nkey}}。返回实际删掉的条数（调用方可据此核对）。须在写事务内调用。
    stab-r10：块内删除按位置切字节（:func:`_drop`），「改后过小的块并入前一块」所需的前一块一条语句批量读出——
    读的都是本次改写前的库状态（与 v1.25 逐块查询相同），合并判定与写出的行逐值同 v1.25。"""
    if not by_term:
        return 0
    pairs = [[t, k] for t in sorted(by_term) for k in sorted(by_term[t])]
    blocks: Dict[Tuple[str, int], tuple] = {}
    cur = _cur(c)
    for part in _chunks(pairs, 20000):
        for t, bno, n, nk, gr in cur.execute(_AT, (json.dumps(part, ensure_ascii=False),)):
            blocks[(t, bno)] = (n, nk, gr)
    removed = 0
    put: Dict[Tuple[str, int], Tuple[int, bytes, bytes]] = {}
    for key in sorted(blocks):
        n, nk, gr = blocks[key]
        new = _drop(n, nk, gr, by_term[key[0]])
        removed += n - new[0]
        if new[0] != n:
            put[key] = new
    small = [key for key in sorted(put) if 0 < put[key][0] < BLOCK // 4]
    prevs: Dict[Tuple[str, int], tuple] = {}
    for part in _chunks(small, 400):
        for t, v, bno, n, nk, gr in cur.execute(_prev_sql(len(part)), [x for key in part for x in key]):
            prevs[(t, v)] = (bno, n, nk, gr)
    dels: List[Tuple[str, int]] = []
    for (t, bno) in sorted(put):
        n = put[(t, bno)][0]
        if not n:
            dels.append((t, bno))
            continue
        if n < BLOCK // 4:
            prev = None                           # 紧邻的前一块（库里 bno < 本块的最大者；若本批改过则取改后内容）
            r = prevs.get((t, bno))
            if r is not None:
                if (t, r[0]) in put:
                    if put[(t, r[0])][0]:
                        prev = (r[0], put[(t, r[0])])
                else:
                    prev = (r[0], r[1:])
            if prev is not None and prev[1][0] + n <= BLOCK:
                pb, (pn, pk, pg) = prev
                a, g = decode(pn, pk, pg)
                b, h = decode(*put[(t, bno)])
                put[(t, pb)] = encode(list(a) + list(b), list(g) + list(h))
                put[(t, bno)] = (0, b"", b"")
                dels.append((t, bno))
    c.executemany("DELETE FROM term_blocks WHERE term=? AND bno=?", dels)
    c.executemany(_PUT, [(t, b) + v for (t, b), v in sorted(put.items()) if v[0]])
    return removed


def check(conn: Any) -> bool:
    """P1 自检：每块 1 ≤ n ≤ BLOCK、块内键严格升序且 ≥ bno、同一词元相邻块区间递增不相交。"""
    prev_t, prev_max = None, -1
    for t, bno, n, nk, gr in _cur(conn).execute("SELECT term, bno, n, nk, gr FROM term_blocks ORDER BY term, bno"):
        a, g = decode(n, nk, gr)
        if not 1 <= n <= BLOCK or len(a) != n or len(g) != n or a[0] < bno:
            return False
        if any(a[i] >= a[i + 1] for i in range(n - 1)):
            return False
        if t == prev_t and bno <= prev_max:
            return False
        prev_t, prev_max = t, a[-1]
    return True
