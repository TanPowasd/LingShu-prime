# -*- coding: utf-8 -*-
"""textindex · 派生文本索引（倒排词元表 + df + 新奇特征计数）

旧实现与 ng 第一版的问题：检索靠 ``instr()``/``LIKE`` 全表预筛（O(N·探针)），候选池按命中
探针数截断；新奇度每次全库重算特征（O(N·L)，缺口 5）；模糊去重只看最近 200 条（缺口 6）。

结构：
  * ``node_index(nkey, node_id, terms, feats, grams)``：每节点一行（nkey = 整数代理键），terms = 规范化正文二元组 ∪
    ``\\x1f``+标签（标签项，供「标签 ⊂ 查询」加分的精确候选），feats = 新奇特征（仅可检索层），
    grams = 正文二元组个数（相关度上界用；不可检索层记 0）。
  * 倒排：schema v5 起为 ``term_blocks``（:mod:`lingshu_ng.store.postings`，按词元分块打包 (nkey, grams)，每块 ≤ 128 条，
    WITHOUT ROWID）；v3/v4 是逐条一行的 ``node_terms(term, nkey, grams)``。读出顺序与内容同 v4（按 nkey 升序）；
    grams 冗余自 node_index，让检索读倒排即得每个节点的精确率分母、无需逐行回表。``term_df``：词元 df（WITHOUT ROWID）；
    ``feature_df``：新奇特征在可检索层中的出现节点数。
  * 水位（arch-scale）：``index_state('hw')`` = 已处理到的最大 nodes.rowid。rowid 高于水位的行一律视为脏
    （新行是 rowid 递增追加的常态——灌库时不再逐行写 ``index_dirty``，省一棵 B 树的随机写）；落在水位以下的
    插入（REPLACE 复用 rowid、显式小 rowid）由插入触发器显式记脏。flush 处理「脏表 ∪ 水位以上」后在同一
    写事务内把水位推到 MAX(rowid)。
  * 维护（v5）：schema.TRIGGERS 的纯 SQL 触发器只负责「nodes 改 ⇒ 记脏；nodes 删 ⇒ 删 node_index 行 ⇒ 旧词元/特征进
    墓碑 ``index_tomb``」，所以任何连接的裸写都不会让索引过期。倒排块、df、新奇特征计数由本模块在 Python 侧增删：
    写路径 / flush 开头先让墓碑退出（:meth:`TextIndex._apply_tombs`，须先于新 nkey 分配），再把脏节点「算词元 →
    重写 node_index 行 → 倒排块删旧加新 → 计数按净变化增减」（:meth:`TextIndex._apply`；结果与 v4 触发器路径逐值相同）。
    任何读之前先 flush。
  * 新奇特征按需构建：新库/重建后 ``index_state('feats','0')``，此时 feats 全为 ``'[]'``、feature_df
    全 0（删除触发器无可递减，自然一致）；首次新奇度查询 :meth:`TextIndex.ensure_feats` 一次补建，
    之后随写入即时维护。检索/去重/自检的首读因此不付特征成本。

不变量：
  T1 flush 之后，node_index 与 nodes 一一对应，倒排/df/特征计数与「从 nodes 全量重算」相同
     （特征未构建时「全量重算」的特征即为空）
     （tests_ng/test_recall_perf.py::test_index_matches_rebuild）。
  T2 词元与检索评分用的是同一个 :func:`dedup.bigrams`（规范化后二元组）——倒排命中 ⇔ 评分交集非空。
"""
from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .. import dedup
from ..lexical import LEXV, index_words
from ..layers import LayerPolicy
from ..novelty import feature_set, novelty_with
from .db import Database
from . import postings
from .schema import chunks, placeholders

__all__ = ["TextIndex", "TAG_PREFIX", "terms_of"]

#: 标签词元前缀（\x1f 是空白类字符，规范化正文的二元组里不可能出现，故与正文词元不相交）
TAG_PREFIX = "\x1f"
_SEARCHABLE = frozenset(m.value for m in LayerPolicy.layers(searchable=True))


def _tags(raw: Optional[str]) -> List[str]:
    try:
        v = json.loads(raw) if raw else []
    except ValueError:
        return []
    return [str(t) for t in v] if isinstance(v, list) else []


def _pack(items: Sequence[str]) -> str:
    """派生行里的紧凑 JSON 数组（无空格分隔，省约一成体积；触发器以 json_each 读取）。"""
    return json.dumps(list(items), ensure_ascii=False, separators=(",", ":"))


def terms_of(content: Optional[str], tags: Sequence[str]) -> Tuple[List[str], int]:
    """(词元表, 正文二元组个数)。"""
    grams = dedup.bigrams(content or "")
    terms = set(grams) | {TAG_PREFIX + t for t in tags if t} | set(index_words(content))
    return sorted(terms), len(grams)


class TextIndex:
    """派生文本索引的读写入口（绑定一个 Database）。"""

    def __init__(self, db: Database) -> None:
        self.db = db
        #: 最近一次去重探针的 (二元组集, df)：写入期矛盾检测复用（:mod:`lingshu_ng.conflict` C1）
        self.last_probe: Optional[Tuple[frozenset, Dict[str, int]]] = None
        #: 倒排块缓存（判定精排的成员点查用；令牌失效见 postings.BlockCache）
        self._bcache = postings.BlockCache()

    # ------------------------------------------------------------ 维护
    def ensure_lexical(self) -> bool:
        """gen-v1 L2：派生倒排的词元格式版本（index_state('lexv')）。旧库（无拉丁词干词元）打开时整体记脏，
        由首次读前的 flush 批量重建；空库直接登记版本。返回是否记了脏。"""
        with self.db.tx() as c:
            r = c.execute("SELECT value FROM index_state WHERE key='lexv'").fetchone()
            if r is not None and r[0] == LEXV:
                return False
            has = c.execute("SELECT 1 FROM node_index LIMIT 1").fetchone() is not None
            if has:
                c.execute("INSERT OR IGNORE INTO index_dirty(node_id) SELECT id FROM nodes")
            c.execute("INSERT OR REPLACE INTO index_state(key, value) VALUES ('lexv', ?)", (LEXV,))
            return has

    def feats_ready(self, c: Any = None) -> bool:
        """新奇特征计数是否已构建（未构建时 node_index.feats 全为 '[]'、feature_df 全 0）。"""
        q = "SELECT 1 FROM index_state WHERE key='feats' AND value='0'"
        row = (c.execute(q).fetchone() if c is not None else self.db.one(q))
        return row is None

    def reindex_written(self, c: Any, nid: str, content: Optional[str], tags_json: Optional[str],
                        layer: Optional[str], existed: bool) -> None:
        """仓储写路径的快捷维护：刚写入的节点行已在手，直接重写其 node_index（免回读 nodes 与脏表扫描），
        随后若还有其它脏节点（旧代码裸写）再走 :meth:`flush`。须在写入的同一事务内调用。"""
        self._apply_tombs(c)
        row = self._parts(nid, content, tags_json, layer, self.feats_ready(c))
        if not (existed and self._move_row(c, row)):
            if existed:
                self._drop_rows(c, [nid])
            cur = c.execute("INSERT INTO node_index (node_id, terms, feats, grams) VALUES (?,?,?,?)", self._packed(row))
            self._apply(c, [], [(cur.lastrowid,) + row[1:]])
        c.execute("DELETE FROM index_dirty WHERE node_id=?", (nid,))
        hw = self._hw(c)
        row = c.execute("SELECT rowid FROM nodes WHERE id=?", (nid,)).fetchone()
        if row is not None and row[0] > hw and c.execute(
                "SELECT 1 FROM nodes WHERE rowid > ? AND rowid <> ? LIMIT 1", (hw, row[0])).fetchone() is None:
            self._set_hw(c, row[0])                       # 本节点是水位以上唯一的行且已索引：水位跟进
        if self._pending(c):
            self.flush()

    @staticmethod
    def _hw(c: Any) -> int:
        """派生索引水位（无记录 = 0：全部 rowid 都在水位以上）。"""
        r = c.execute("SELECT CAST(value AS INTEGER) FROM index_state WHERE key='hw'").fetchone()
        return int(r[0]) if r and r[0] is not None else 0

    @staticmethod
    def _set_hw(c: Any, hw: int) -> None:
        c.execute("INSERT OR REPLACE INTO index_state(key, value) VALUES ('hw', ?)", (str(int(hw)),))

    def _pending(self, c: Any) -> bool:
        """是否有待处理的派生索引变更：墓碑或脏表非空，或有 rowid 高于水位的行。"""
        if c.execute("SELECT 1 FROM index_dirty LIMIT 1").fetchone() is not None:
            return True
        if c.execute("SELECT 1 FROM index_tomb LIMIT 1").fetchone() is not None:
            return True
        return c.execute("SELECT 1 FROM nodes WHERE rowid > ? LIMIT 1", (self._hw(c),)).fetchone() is not None

    #: 一次 flush 的脏节点数达到该值时走批量路径（nkey 分配与 v4 批量路径相同，见 :meth:`_bulk_flush`）
    BULK_MIN = 32
    #: 批量路径每批算词元并落 node_index / 倒排块的节点数（Python 侧峰值内存与批大小成正比）
    BULK_BATCH = 4000

    def flush(self) -> int:
        """处理墓碑并把脏节点重建进 node_index 与倒排块（与 v4 触发器路径逐值一致）。返回处理的节点数。

        写路径只记脏（触发器），派生索引在**首次读之前**统一重建：灌库时 N 次写只做一次批量构建。
        新奇特征只在已构建时随之维护；未构建时留给首次新奇度查询（:meth:`ensure_feats`）。"""
        with self.db.lock:
            if not self._pending(self.db.conn):
                return 0
        with self.db.tx() as c:
            self._apply_tombs(c)
            ready = self.feats_ready(c)
            hw = self._hw(c)
            ids = [r[0] for r in c.execute("SELECT node_id FROM index_dirty").fetchall()]
            above = c.execute("SELECT id, rowid FROM nodes WHERE rowid > ? ORDER BY rowid", (hw,)).fetchall()
            if above:
                ids = list(dict.fromkeys(ids + [r[0] for r in above]))
            if ids:
                (self._bulk_flush if len(ids) >= self.BULK_MIN else self._row_flush)(c, ids, ready)
            c.execute("DELETE FROM index_dirty")
            if above:
                self._set_hw(c, above[-1][1])
        if len(ids) >= self.BULK_MIN:
            self.db.need_lazy_indexes()                   # 灌库后的首次读：惰性二级索引一并建齐（S5）
        return len(ids)

    # ---- v5：倒排块 / df / 新奇特征计数在 Python 侧维护（v4 为 node_index 上的触发器，结果逐值相同）
    @staticmethod
    def _apply(c: Any, olds: Sequence[tuple], news: Sequence[tuple]) -> None:
        """olds = [(nkey, 词元表, 特征表)] 退出索引，news = [(nkey, 词元表, 特征表, grams)] 进入索引：
        倒排块先删后加；term_df / feature_df 按净变化增减（与 v4 触发器「旧项减一、新项加一（无行则建行）」终值相同，
        df 减到 0 的行照旧保留）。"""
        if not olds and len(news) == 1 and news[0][1]:     # 单条写入的常态：一个新节点，各一条语句
            k, terms, feats, grams = news[0]
            postings.add_node(c, terms, k, grams)
            for table, col, items in (("term_df", "term", terms), ("feature_df", "feat", feats)):
                if items:
                    c.execute(f"INSERT INTO {table}({col}, df) SELECT value, 1 FROM json_each(?) WHERE 1 "
                              f"ON CONFLICT({col}) DO UPDATE SET df = df + 1", (_pack(items),))
            return
        rm: Dict[str, Set[int]] = {}
        dt: Counter = Counter()
        df_: Counter = Counter()
        for k, terms, feats in olds:
            for t in terms:
                rm.setdefault(t, set()).add(k)
            dt.subtract(terms)
            df_.subtract(feats)
        ad: Dict[str, List[Tuple[int, int]]] = {}
        for k, terms, feats, grams in sorted(news, key=lambda r: r[0]):
            for t in terms:
                ad.setdefault(t, []).append((k, grams))
            dt.update(terms)
            df_.update(feats)
        postings.remove(c, rm)
        postings.add(c, ad)
        TextIndex._counts(c, "term_df", "term", dt)
        TextIndex._counts(c, "feature_df", "feat", df_)

    @staticmethod
    def _counts(c: Any, table: str, col: str, delta: Counter) -> None:
        up = [[t, d] for t, d in delta.items() if d > 0]
        down = [(-d, t) for t, d in delta.items() if d < 0]
        if down:
            c.executemany(f"UPDATE {table} SET df = df - ? WHERE {col} = ?", down)
        if up:                                             # 一条语句（与 v4 触发器的 json_each 增计数同形）
            c.execute(f"INSERT INTO {table}({col}, df) SELECT json_extract(value, '$[0]'), json_extract(value, '$[1]') "
                      f"FROM json_each(?) WHERE 1 ON CONFLICT({col}) DO UPDATE SET df = df + excluded.df",
                      (json.dumps(up, ensure_ascii=False),))

    @staticmethod
    def _apply_tombs(c: Any) -> int:
        """墓碑（node_index 行被删时 trg_index_tomb 留下的 (nkey, 旧词元, 旧特征)）退出倒排与计数。须先于任何新 nkey
        分配执行（nkey 可能被复用）。墓碑键若已被别的 node_index 行占用（只有裸写派生表才会），该行一并记脏重建。"""
        rows = c.execute("SELECT nkey, terms, feats FROM index_tomb").fetchall()
        if not rows:
            return 0
        TextIndex._apply(c, [(k, json.loads(t), json.loads(f)) for k, t, f in rows], [])
        keys = sorted({r[0] for r in rows})
        for part in chunks(keys):
            c.execute(f"INSERT OR IGNORE INTO index_dirty(node_id) SELECT node_id FROM node_index "
                      f"WHERE nkey IN ({placeholders(len(part))})", part)
        c.execute("DELETE FROM index_tomb")
        return len(rows)

    def _drop_rows(self, c: Any, ids: Sequence[str]) -> None:
        """删除这些节点的 node_index 行（触发器把旧词元/特征转入墓碑）并立即让其退出倒排与计数。"""
        for part in chunks(list(ids)):
            c.execute(f"DELETE FROM node_index WHERE node_id IN ({placeholders(len(part))})", part)
        self._apply_tombs(c)

    @staticmethod
    def _move_row(c: Any, row: tuple) -> bool:
        """单个已索引节点的重建走原位改写：nkey 取「删掉旧行后再插入」会分配到的键（其余行的最大 nkey + 1，
        与 SQLite 整数主键的分配规则相同），词元/特征/grams 改成新值——结果与删旧插新逐值相同。
        节点尚未索引 ⇒ False（调用方照旧插入）。row = :meth:`_parts` 的未打包行。"""
        old = c.execute("SELECT nkey, terms, feats FROM node_index WHERE node_id=?", (row[0],)).fetchone()
        if old is None:
            return False
        mx = c.execute("SELECT nkey FROM node_index WHERE nkey <> ? ORDER BY nkey DESC LIMIT 1", (old[0],)).fetchone()
        nk = (mx[0] if mx else 0) + 1
        p = TextIndex._packed(row)
        if nk == old[0] and p[1] == old[1] and p[2] == old[2] and c.execute(
                "SELECT grams FROM node_index WHERE nkey=?", (nk,)).fetchone()[0] == p[3]:
            return True                                   # 键与内容都未变：无事可做
        c.execute("UPDATE node_index SET nkey=?, terms=?, feats=?, grams=? WHERE nkey=?", (nk,) + p[1:] + (old[0],))
        ot, of = json.loads(old[1]), json.loads(old[2])
        if nk == old[0]:
            TextIndex._apply(c, [(nk, ot, of)], [(nk,) + tuple(row[1:])])
        else:
            TextIndex._apply(c, [(old[0], ot, of)], [(nk,) + tuple(row[1:])])
        return True

    def _row_flush(self, c: Any, ids: List[str], ready: bool) -> None:
        """少量脏节点：逐行删旧插新（nkey 由 SQLite 按删后最大值 + 1 依次分配，与 v4 相同）；只有一个脏节点且已索引时
        走原位改写（:meth:`_move_row`，结果相同）。"""
        if len(ids) == 1:
            got = c.execute("SELECT id, content, tags, layer FROM nodes WHERE id=?", (ids[0],)).fetchall()
            if got and self._move_row(c, self._parts(*got[0], ready)):
                return
        for part in chunks(ids):
            ph = placeholders(len(part))
            got = c.execute(f"SELECT id, content, tags, layer FROM nodes WHERE id IN ({ph})", part).fetchall()
            self._drop_rows(c, part)
            news = []
            for r in got:
                p = self._parts(*r, ready)
                cur = c.execute("INSERT INTO node_index (node_id, terms, feats, grams) VALUES (?,?,?,?)", self._packed(p))
                news.append((cur.lastrowid,) + p[1:])
            self._apply(c, [], news)

    def _bulk_flush(self, c: Any, ids: List[str], ready: bool) -> None:
        """批量重建（结果与逐行路径的 v4 批量版相同，T1）：nkey 从「删旧行之前」的最大值 + 1 起连续分配；
        旧行先整体退出，新行每 :data:`BULK_BATCH` 个一批落 node_index 并按 nkey 升序追加进倒排块。"""
        base = int(c.execute("SELECT COALESCE(MAX(nkey), 0) FROM node_index").fetchone()[0]) + 1
        nxt = base
        news: List[tuple] = []
        for part in chunks(ids):
            ph = placeholders(len(part))
            self._drop_rows(c, part)
            for r in c.execute(f"SELECT id, content, tags, layer FROM nodes WHERE id IN ({ph})", part).fetchall():
                news.append((nxt,) + self._parts(*r, ready))
                nxt += 1
            if len(news) >= self.BULK_BATCH:
                self._bulk_put(c, news)
                news = []
        if news:
            self._bulk_put(c, news)

    def _bulk_put(self, c: Any, news: List[tuple]) -> None:
        c.executemany("INSERT INTO node_index (nkey, node_id, terms, feats, grams) VALUES (?,?,?,?,?)",
                      [(r[0],) + self._packed(r[1:]) for r in news])
        self._apply(c, [], [(r[0], r[2], r[3], r[4]) for r in news])

    @staticmethod
    def _count_feats(c: Any, base: int) -> None:
        """把 nkey ≥ base 的行的特征计入 feature_df（集合式聚合）。"""
        c.execute("INSERT INTO feature_df(feat, df) SELECT j.value, COUNT(*) FROM node_index ni, "
                  "json_each(ni.feats) j WHERE ni.nkey >= ? AND ni.feats <> '[]' GROUP BY j.value ORDER BY 1 "
                  "ON CONFLICT(feat) DO UPDATE SET df = df + excluded.df", (base,))

    def ensure_feats(self) -> bool:
        """按需构建新奇特征计数（只有新奇度用到）：为全部可检索层行算特征、回填 node_index.feats
        （删除时据此递减，计数一致性与即时维护相同），再一次聚合进 feature_df。返回是否做了构建。"""
        self.flush()
        if self.feats_ready():
            return False
        with self.db.tx() as c:
            if self.feats_ready(c):
                return False
            self._apply_tombs(c)
            got = c.execute("SELECT ni.nkey, n.content FROM node_index ni JOIN nodes n ON n.id = ni.node_id "
                            f"WHERE n.layer IN ({placeholders(len(_SEARCHABLE))})", sorted(_SEARCHABLE)).fetchall()
            upd = []
            for k, content in got:
                f = feature_set(content or "")
                if f:
                    upd.append((_pack(sorted(f)), k))
            c.executemany("UPDATE node_index SET feats=? WHERE nkey=?", upd)
            c.execute("DELETE FROM feature_df")
            self._count_feats(c, 0)
            c.execute("DELETE FROM index_state WHERE key='feats'")
        return True

    @staticmethod
    def _parts(nid: str, content: Optional[str], tags_json: Optional[str], layer: Optional[str],
               feats: bool = True) -> tuple:
        """(node_id, 词元表, 特征表, grams)——未打包的派生行；``feats=False`` 时不算特征（未构建状态）。"""
        terms, n = terms_of(content, _tags(tags_json))
        if layer not in _SEARCHABLE:
            return (nid, terms, [], 0)            # 不可检索：无特征、不进上界统计
        return (nid, terms, sorted(feature_set(content or "")) if feats else [], n)

    @staticmethod
    def _packed(p: tuple) -> tuple:
        """未打包行 → node_index 列值 (node_id, terms, feats, grams)。"""
        return (p[0], _pack(p[1]), _pack(p[2]) if p[2] else "[]", p[3])

    @classmethod
    def _row(cls, nid: str, content: Optional[str], tags_json: Optional[str], layer: Optional[str],
             feats: bool = True) -> tuple:
        return cls._packed(cls._parts(nid, content, tags_json, layer, feats))

    # ------------------------------------------------------------ 读（调用方负责先 flush）
    def df(self, terms: Iterable[str]) -> Dict[str, int]:
        """词元 df（只返回 df>0 的项）。"""
        out: Dict[str, int] = {}
        for part in chunks(sorted(set(terms))):
            for t, d in self.db.all(f"SELECT term, df FROM term_df WHERE term IN ({placeholders(len(part))}) "
                                    "AND df > 0", part):
                out[t] = int(d)
        return out

    def postings(self, term: str) -> List[int]:
        """单个词元的倒排（节点整数键 nkey 升序列表）。"""
        with self.db.lock:
            return postings.read(self.db.conn, term)[0]

    def postings_g(self, term: str) -> List[Tuple[int, int]]:
        """单个词元的倒排，连同每个节点的正文二元组数：[(nkey, grams)]（检索上界用，免回表）。"""
        with self.db.lock:
            ks, gs = postings.read(self.db.conn, term)
        return list(zip(ks, gs))

    def postings_len(self, term: str, lo: int, hi: int) -> List[Tuple[int, int]]:
        """:meth:`postings_g` 只留二元组数在 [lo, hi] 内或未知（0）的行。"""
        with self.db.lock:
            ks, gs = postings.read(self.db.conn, term)
        return [(k, g) for k, g in zip(ks, gs) if g == 0 or lo <= g <= hi]

    def members(self, term: str, keys: Sequence[int]) -> List[int]:
        """keys 中含该词元的节点（升序）。"""
        if not keys:
            return []
        with self.db.lock:
            return postings.members(self.db.conn, term, keys, self._bcache)

    def members_multi(self, terms: Sequence[str], keys: Sequence[int]) -> List[Tuple[str, int]]:
        """[(词元, nkey)]：keys 中含 terms 任一项的 (词元, 节点) 对（逐词元 :meth:`members` 的并）。"""
        out: List[Tuple[str, int]] = []
        if not terms or not keys:
            return out
        with self.db.lock:
            return postings.members_multi(self.db.conn, terms, keys, self._bcache)

    def node_ids(self, keys: Iterable[int]) -> Dict[int, str]:
        """nkey → 节点 id。"""
        out: Dict[int, str] = {}
        for part in chunks(sorted(set(keys))):
            out.update((k, nid) for k, nid in self.db.all(
                f"SELECT nkey, node_id FROM node_index WHERE nkey IN ({placeholders(len(part))})", part))
        return out

    def postings_rows(self, terms: Sequence[str]) -> List[Tuple[str, int, int]]:
        """若干词元的倒排行 [(词元, nkey, 正文二元组数)]，按 (词元, nkey) 升序。"""
        out: List[Tuple[str, int, int]] = []
        for part in chunks(list(dict.fromkeys(terms))):
            with self.db.lock:
                out.extend(postings.read_many(self.db.conn, part))
        return out

    def postings_any(self, terms: Sequence[str]) -> Set[str]:
        """含任一词元的节点 id 集合。"""
        keys: Set[int] = set()
        for part in chunks(list(dict.fromkeys(terms))):
            with self.db.lock:
                keys.update(k for _, k, _ in postings.read_many(self.db.conn, part))
        return set(self.node_ids(keys).values())

    def min_grams(self) -> int:
        """可检索层节点正文二元组个数的最小正值（相关度上界用；空库返回 1）。"""
        v = self.db.scalar("SELECT MIN(grams) FROM node_index WHERE grams > 0")
        return int(v) if v else 1

    def total(self) -> int:
        """已索引节点数（idf 的 N）。"""
        return int(self.db.scalar("SELECT COUNT(*) FROM node_index", default=0))

    @staticmethod
    def idf(df: int, n: int) -> float:
        """平滑 idf：ln(1 + N/df)。"""
        return math.log(1.0 + max(1, n) / max(1, df))

    def near_duplicate_candidates(self, grams: frozenset, threshold: float, extra: int = 3) -> Set[str]:
        """近重复候选：Jaccard(A, B) ≥ t 的全部节点的**精确超集**（与「全层逐条比对」结果相同，不设时间窗口）。

        stab-r5（规模）：旧版（:meth:`_ndc_prefix`）读 A 中 df 最小的 |A|−need+1+j 个二元组的完整倒排，
        常用二元组的倒排随库规模线性变长 ⇒ 每次写入 O(N)、灌库 O(N²)。现改为「前缀 + 逐步校验 + 剪枝」：

        1. 前缀：need=⌈t·|A|⌉，r = |A|−need+1 个最稀有二元组里真近重复至少命中 1 个（鸽笼）⇒
           只读这 r 个倒排得到候选，同时用倒排行自带的 |B| 做长度过滤 t·|A| ≤ |B| ≤ |A|/t；
        2. 每个候选的精确下限 need_B = ⌈t·(|A|+|B|)/(1+t)⌉（J ≥ t ⇔ |A∩B| ≥ need_B）；
        3. 其余二元组按 df 升序逐个校验：df 不超过存活候选数时读整条倒排，否则只对存活候选做主键点查；
           每步剔除「已命中 + 剩余可命中 < need_B」的候选，存活为空即停。

        所有剪枝都是必要条件，因此结果 ⊇ 全部真近重复；调用方随后逐条核对 Jaccard 与签名，返回值与旧版逐位相同
        （tests_ng/test_perf_scale.py 对照旧算法）。t ≤ 0 或 t > 1 时沿用旧算法。``extra`` 只用于旧算法。"""
        self.flush()
        if not grams:
            return set()
        if not 0 < threshold <= 1:
            return self._ndc_prefix(grams, threshold, extra)
        a = len(grams)
        need = max(1, math.ceil(threshold * a - 1e-9))
        dfs = self.df(grams)
        self.last_probe = (grams, dfs)          # 写入期矛盾检测（conflict C1）复用，免再查一次 df
        if len(dfs) < need:
            return set()                      # 库里连 need 个二元组都凑不齐 ⇒ 不可能近重复
        order = sorted(grams, key=lambda g: (dfs.get(g, 0), g))
        r = a - need + 1
        lo = math.floor(threshold * a * (1 - 1e-9))
        hi = math.ceil(a / threshold * (1 + 1e-9))
        cnt: Dict[int, int] = {}
        nb: Dict[int, int] = {}
        for g in order[:r]:
            if dfs.get(g, 0) <= 0:
                continue
            for k, n in self.postings_len(g, lo, hi):
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
                    got = [k for k in self.postings(g) if k in cnt]
                else:
                    got = self.members(g, sorted(cnt))
                for k in got:
                    cnt[k] += 1
            done += 1
        keep = [k for k, c in cnt.items() if c >= req[k]]
        return set(self.node_ids(keep).values())

    def _ndc_prefix(self, grams: frozenset, threshold: float, extra: int = 3) -> Set[str]:
        """旧版近重复候选（rel-v1.19 及以前，前缀过滤 + 固定 j）：Jaccard(A,B) ≥ t ⇒ |A∩B| ≥ need=⌈t·|A|⌉ ⇒
        在 A 中 df 最小的 m = |A|−need+1+j 个二元组里，B 至少命中 1+j 个。保留作 t 越界时的路径与测试对照。"""
        self.flush()
        if not grams:
            return set()
        need = max(1, math.ceil(threshold * len(grams) - 1e-9))
        dfs = self.df(grams)
        self.last_probe = (grams, dfs)
        if len(dfs) < need:
            return set()
        m = min(len(grams), len(grams) - need + 1 + max(0, extra))
        rare = sorted(grams, key=lambda g: (dfs.get(g, 0), g))[:m]
        hits: Counter = Counter()
        for g in rare:
            if dfs.get(g, 0) > 0:
                hits.update(self.postings(g))     # C 层计数
        floor = m - (len(grams) - need)
        return set(self.node_ids(k for k, c in hits.items() if c >= floor).values())

    # ------------------------------------------------------------ 新奇度（缺口 5）
    def novelty(self, text: str, exclude: Optional[str] = None) -> float:
        """与 ``novelty.novelty(text, 全部可检索层正文 − exclude)`` 逐值相等，但 O(特征数)。
        特征计数按需构建：首次调用付一次 :meth:`ensure_feats`，此后随写入即时维护。"""
        self.ensure_feats()
        own: Set[str] = set()
        if exclude:
            raw = self.db.scalar("SELECT feats FROM node_index WHERE node_id=?", (exclude,))
            own = set(json.loads(raw)) if raw else set()
        has_ref = self.has_reference(exclude)
        feats = feature_set(text)
        counts = self._feature_counts(feats)
        return novelty_with(text, lambda f: counts.get(f, 0) - (1 if f in own else 0) > 0, has_ref)

    def has_reference(self, exclude: Optional[str] = None) -> bool:
        """参照集（可检索层正文特征，排除 ``exclude``）是否非空。"""
        return self.db.scalar("SELECT 1 FROM node_index WHERE feats <> '[]' AND node_id IS NOT ? LIMIT 1",
                              (exclude,)) is not None

    def _feature_counts(self, feats: Iterable[str]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for part in chunks(sorted(set(feats))):
            for f, d in self.db.all(f"SELECT feat, df FROM feature_df WHERE feat IN ({placeholders(len(part))})",
                                    part):
                out[f] = int(d)
        return out

    # ------------------------------------------------------------ 诊断
    def rebuild_equals(self) -> bool:
        """T1 自检：当前派生表是否等于从 nodes 全量重算的结果（特征计数未构建时，须恰为全空）；
        倒排块逐词元解码后与重算的 (nkey, grams) 全量相等，且块满足 P1（bno ≤ 块内最小键、各块升序不相交、≤ BLOCK 条）。"""
        self.flush()
        ready = self.feats_ready()
        want_terms: Dict[str, int] = {}
        want_feats: Dict[str, int] = {}
        want_post: Dict[str, List[Tuple[int, int]]] = {}
        keys = {nid: k for k, nid in self.db.all("SELECT nkey, node_id FROM node_index")}
        for nid, content, tags, layer in self.db.all("SELECT id, content, tags, layer FROM nodes"):
            _, terms, feats, grams = self._parts(nid, content, tags, layer, ready)
            for t in terms:
                want_terms[t] = want_terms.get(t, 0) + 1
                if nid in keys:
                    want_post.setdefault(t, []).append((keys[nid], grams))
            for f in feats:
                want_feats[f] = want_feats.get(f, 0) + 1
        have_terms = {t: d for t, d in self.db.all("SELECT term, df FROM term_df WHERE df > 0")}
        have_feats = {f: d for f, d in self.db.all("SELECT feat, df FROM feature_df WHERE df > 0")}
        with self.db.lock:
            have_post = postings.all_postings(self.db.conn)
            blocks_ok = postings.check(self.db.conn)
        stale_feats = (not ready) and self.db.scalar("SELECT 1 FROM node_index WHERE feats <> '[]' LIMIT 1") is not None
        return (have_terms == want_terms and have_feats == want_feats and not stale_feats and blocks_ok
                and have_post == {t: sorted(v) for t, v in want_post.items()}
                and self.db.scalar("SELECT COUNT(*) FROM index_tomb", default=0) == 0
                and self.total() == self.db.scalar("SELECT COUNT(*) FROM nodes", default=0))
