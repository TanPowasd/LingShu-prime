# -*- coding: utf-8 -*-
"""textindex · 派生文本索引（倒排词元表 + df + 新奇特征计数）

旧实现与 ng 第一版的问题：检索靠 ``instr()``/``LIKE`` 全表预筛（O(N·探针)），候选池按命中
探针数截断；新奇度每次全库重算特征（O(N·L)，缺口 5）；模糊去重只看最近 200 条（缺口 6）。

结构：
  * ``node_index(nkey, node_id, terms, feats, grams)``：每节点一行（nkey = 整数代理键），terms = 规范化正文二元组 ∪
    ``\\x1f``+标签（标签项，供「标签 ⊂ 查询」加分的精确候选），feats = 新奇特征（仅可检索层），
    grams = 正文二元组个数（相关度上界用；不可检索层记 0）。
  * ``node_terms(term, nkey, grams)``：倒排表（WITHOUT ROWID，按 term 聚簇，节点以整数代理键登记——
    比文本 id 省一半以上倒排体积，读倒排不再构造 str；grams 冗余自 node_index，随行重写同步，
    让检索读倒排即得每个节点的精确率分母、无需逐行回表）；``term_df``：词元 df（WITHOUT ROWID）；
    ``feature_df``：新奇特征在可检索层中的出现节点数。
  * 维护全部由 schema.TRIGGERS 的纯 SQL 触发器完成：nodes 增改 ⇒ ``index_dirty`` 记脏，
    nodes 删 ⇒ 级联删 node_index ⇒ 级联删倒排并递减计数。本模块只负责把脏节点「算词元 →
    重写 node_index 行」（:meth:`TextIndex.flush`；脏节点多时走集合式批量路径）。任何读之前先
    flush，所以旧代码的裸 SQL 写入同样不会让索引过期。
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
from ..layers import LayerPolicy
from ..novelty import feature_set, novelty_with
from .db import Database
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
    terms = set(grams) | {TAG_PREFIX + t for t in tags if t}
    return sorted(terms), len(grams)


class TextIndex:
    """派生文本索引的读写入口（绑定一个 Database）。"""

    def __init__(self, db: Database) -> None:
        self.db = db
        #: 最近一次去重探针的 (二元组集, df)：写入期矛盾检测复用（:mod:`lingshu_ng.conflict` C1）
        self.last_probe: Optional[Tuple[frozenset, Dict[str, int]]] = None

    # ------------------------------------------------------------ 维护
    def feats_ready(self, c: Any = None) -> bool:
        """新奇特征计数是否已构建（未构建时 node_index.feats 全为 '[]'、feature_df 全 0）。"""
        q = "SELECT 1 FROM index_state WHERE key='feats' AND value='0'"
        row = (c.execute(q).fetchone() if c is not None else self.db.one(q))
        return row is None

    def reindex_written(self, c: Any, nid: str, content: Optional[str], tags_json: Optional[str],
                        layer: Optional[str], existed: bool) -> None:
        """仓储写路径的快捷维护：刚写入的节点行已在手，直接重写其 node_index（免回读 nodes 与脏表扫描），
        随后若还有其它脏节点（旧代码裸写）再走 :meth:`flush`。须在写入的同一事务内调用。"""
        if existed:
            c.execute("DELETE FROM node_index WHERE node_id=?", (nid,))
        c.execute("INSERT INTO node_index (node_id, terms, feats, grams) VALUES (?,?,?,?)",
                  self._row(nid, content, tags_json, layer, self.feats_ready(c)))
        c.execute("DELETE FROM index_dirty WHERE node_id=?", (nid,))
        if c.execute("SELECT 1 FROM index_dirty LIMIT 1").fetchone() is not None:
            self.flush()

    #: 一次 flush 的脏节点数达到该值时走批量路径（绕开逐行触发器，见 :meth:`_bulk_flush`）
    BULK_MIN = 32
    #: 批量路径每批算词元并落 node_index 的节点数（Python 侧峰值内存与批大小成正比）
    BULK_BATCH = 4000

    def flush(self) -> int:
        """把脏节点重建进 node_index（倒排/计数与触发器路径逐值一致）。返回处理的节点数。

        写路径只记脏（触发器），派生索引在**首次读之前**统一重建：灌库时 N 次写只做一次批量构建。
        新奇特征只在已构建时随之维护；未构建时留给首次新奇度查询（:meth:`ensure_feats`）。"""
        if self.db.scalar("SELECT 1 FROM index_dirty LIMIT 1") is None:
            return 0
        with self.db.tx() as c:
            ready = self.feats_ready(c)
            ids = [r[0] for r in c.execute("SELECT node_id FROM index_dirty").fetchall()]
            if len(ids) >= self.BULK_MIN:
                self._bulk_flush(c, ids, ready)
            else:
                for part in chunks(ids):
                    ph = placeholders(len(part))
                    got = c.execute(f"SELECT id, content, tags, layer FROM nodes WHERE id IN ({ph})",
                                    part).fetchall()
                    c.execute(f"DELETE FROM node_index WHERE node_id IN ({ph})", part)
                    c.executemany("INSERT INTO node_index (node_id, terms, feats, grams) VALUES (?,?,?,?)",
                                  [self._row(*r, ready) for r in got])
            c.execute("DELETE FROM index_dirty")
        return len(ids)

    def _bulk_flush(self, c: Any, ids: List[str], ready: bool) -> None:
        """集合式批量重建（结果与逐行触发器路径相同，T1）：旧行照常经删除触发器退出计数；
        新行在 ``index_state('bulk')`` 守卫下直接带词元/特征插入 node_index（插入触发器让位），
        随后各用**一条** SQL 从新行展开倒排（全局按 (term, nkey) 排序 ⇒ B 树顺序追加）并聚合 df/特征计数。"""
        c.execute("INSERT OR REPLACE INTO index_state(key, value) VALUES ('bulk', '1')")
        base = int(c.execute("SELECT COALESCE(MAX(nkey), 0) FROM node_index").fetchone()[0]) + 1
        nxt = base
        rows: List[tuple] = []
        for part in chunks(ids):
            ph = placeholders(len(part))
            c.execute(f"DELETE FROM node_index WHERE node_id IN ({ph})", part)   # 触发器递减旧计数
            got = c.execute(f"SELECT id, content, tags, layer FROM nodes WHERE id IN ({ph})", part).fetchall()
            for r in got:
                nid, terms, feats, grams = self._row(*r, ready)
                rows.append((nxt, nid, terms, feats, grams))
                nxt += 1
            if len(rows) >= self.BULK_BATCH:
                c.executemany("INSERT INTO node_index (nkey, node_id, terms, feats, grams) VALUES (?,?,?,?,?)", rows)
                rows = []
        if rows:
            c.executemany("INSERT INTO node_index (nkey, node_id, terms, feats, grams) VALUES (?,?,?,?,?)", rows)
        c.execute("DELETE FROM index_state WHERE key='bulk'")
        if nxt == base:
            return
        c.execute("INSERT INTO node_terms(term, nkey, grams) SELECT j.value, ni.nkey, ni.grams FROM node_index ni, "
                  "json_each(ni.terms) j WHERE ni.nkey >= ? ORDER BY 1, 2", (base,))
        c.execute("INSERT INTO term_df(term, df) SELECT term, COUNT(*) FROM node_terms "
                  "WHERE nkey >= ? GROUP BY term ORDER BY term "
                  "ON CONFLICT(term) DO UPDATE SET df = df + excluded.df", (base,))
        if ready:
            self._count_feats(c, base)

    @staticmethod
    def _count_feats(c: Any, base: int) -> None:
        """把 nkey ≥ base 的行的特征计入 feature_df（集合式聚合）。"""
        c.execute("INSERT INTO feature_df(feat, df) SELECT j.value, COUNT(*) FROM node_index ni, "
                  "json_each(ni.feats) j WHERE ni.nkey >= ? AND ni.feats <> '[]' GROUP BY j.value ORDER BY 1 "
                  "ON CONFLICT(feat) DO UPDATE SET df = df + excluded.df", (base,))

    def ensure_feats(self) -> bool:
        """按需构建新奇特征计数（只有新奇度用到）：为全部可检索层行算特征、回填 node_index.feats
        （删除触发器据此递减，计数一致性与即时维护相同），再一次聚合进 feature_df。返回是否做了构建。"""
        self.flush()
        if self.feats_ready():
            return False
        with self.db.tx() as c:
            if self.feats_ready(c):
                return False
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

    @classmethod
    def _row(cls, nid: str, content: Optional[str], tags_json: Optional[str], layer: Optional[str],
             feats: bool = True) -> tuple:
        p = cls._parts(nid, content, tags_json, layer, feats)
        return (p[0], _pack(p[1]), _pack(p[2]) if p[2] else "[]", p[3])

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
        """单个词元的倒排（节点整数键 nkey 列表）。"""
        with self.db.lock:
            cur = self.db.conn.cursor()
            cur.row_factory = None
            return [r for (r,) in cur.execute("SELECT nkey FROM node_terms WHERE term=?", (term,)).fetchall()]

    def postings_g(self, term: str) -> List[Tuple[int, int]]:
        """单个词元的倒排，连同每个节点的正文二元组数：[(nkey, grams)]（检索上界用，免回表）。"""
        with self.db.lock:
            cur = self.db.conn.cursor()
            cur.row_factory = None
            return cur.execute("SELECT nkey, grams FROM node_terms WHERE term=?", (term,)).fetchall()

    def members(self, term: str, keys: Sequence[int]) -> List[int]:
        """keys 中含该词元的节点（逐键 PK 点查，单条语句，键集以 JSON 传入不受变量上限影响）。"""
        if not keys:
            return []
        with self.db.lock:
            cur = self.db.conn.cursor()
            cur.row_factory = None
            return [r for (r,) in cur.execute(
                "SELECT nkey FROM node_terms WHERE term=? AND nkey IN (SELECT value FROM json_each(?))",
                (term, json.dumps(list(keys)))).fetchall()]

    def node_ids(self, keys: Iterable[int]) -> Dict[int, str]:
        """nkey → 节点 id。"""
        out: Dict[int, str] = {}
        for part in chunks(sorted(set(keys))):
            out.update((k, nid) for k, nid in self.db.all(
                f"SELECT nkey, node_id FROM node_index WHERE nkey IN ({placeholders(len(part))})", part))
        return out

    def postings_rows(self, terms: Sequence[str]) -> List[Tuple[str, int, int]]:
        """若干词元的倒排行 [(词元, nkey, 正文二元组数)]（一条语句）。"""
        out: List[Tuple[str, int, int]] = []
        for part in chunks(list(dict.fromkeys(terms))):
            out.extend(tuple(r) for r in self.db.all(
                f"SELECT term, nkey, grams FROM node_terms WHERE term IN ({placeholders(len(part))})", part))
        return out

    def postings_any(self, terms: Sequence[str]) -> Set[str]:
        """含任一词元的节点 id 集合。"""
        keys: Set[int] = set()
        for part in chunks(list(dict.fromkeys(terms))):
            keys.update(r[0] for r in self.db.all(
                f"SELECT nkey FROM node_terms WHERE term IN ({placeholders(len(part))})", part))
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
        """前缀过滤（缺口 6）：Jaccard(A,B) ≥ t ⇒ |A∩B| ≥ need=⌈t·|A|⌉ ⇒ 在 A 中 df 最小的
        m = |A|−need+1+j 个二元组里，B 至少命中 1+j 个（其余 |A|−m 个最多全中）。取这 m 个的倒排
        计数筛选——**精确**的候选超集，与「全层逐条比对」结果相同，且不设任何时间窗口。
        ``extra`` = j（多读几个倒排换更少的正文读取）。"""
        self.flush()
        if not grams:
            return set()
        need = max(1, math.ceil(threshold * len(grams) - 1e-9))
        dfs = self.df(grams)
        self.last_probe = (grams, dfs)          # 写入期矛盾检测（conflict C1）复用，免再查一次 df
        if len(dfs) < need:
            return set()                      # 库里连 need 个二元组都凑不齐 ⇒ 不可能近重复
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
        """T1 自检：当前派生表是否等于从 nodes 全量重算的结果（特征计数未构建时，须恰为全空）。"""
        self.flush()
        ready = self.feats_ready()
        want_terms: Dict[str, int] = {}
        want_feats: Dict[str, int] = {}
        for nid, content, tags, layer in self.db.all("SELECT id, content, tags, layer FROM nodes"):
            _, terms, feats, _ = self._row(nid, content, tags, layer, ready)
            for t in json.loads(terms):
                want_terms[t] = want_terms.get(t, 0) + 1
            for f in json.loads(feats):
                want_feats[f] = want_feats.get(f, 0) + 1
        have_terms = {t: d for t, d in self.db.all("SELECT term, df FROM term_df WHERE df > 0")}
        have_feats = {f: d for f, d in self.db.all("SELECT feat, df FROM feature_df WHERE df > 0")}
        posting_n = self.db.scalar("SELECT COUNT(*) FROM node_terms", default=0)
        stale_feats = (not ready) and self.db.scalar("SELECT 1 FROM node_index WHERE feats <> '[]' LIMIT 1") is not None
        return (have_terms == want_terms and have_feats == want_feats and not stale_feats
                and posting_n == sum(want_terms.values())
                and self.total() == self.db.scalar("SELECT COUNT(*) FROM nodes", default=0))
