# -*- coding: utf-8 -*-
"""expansion · 倒排展开 + 可证上界剪枝（检索 Q1 的执行器，MaxScore 风格）

相关度 s(d) = (k/Q)·(0.5 + 0.5·k/g_d) [+0.05 标签分]，k = 节点命中的查询二元组数，
g_d = 节点正文二元组数，Q = 查询二元组数。展开顺序 = df 升序（idf 降序）。

状态：每个已见节点只记 (已知命中数 k, 是否已知命中标签, 自身 g_d)，按这三个量分桶
（倒排行自带 g_d，见 textindex——读倒排即知每个节点的精确率分母，无需回表）。
  * 桶上界 ub(k, t, g) = ((k+R)/Q)·(0.5+0.5·min(1,(k+R)/g)) + 0.05·[t ∨ 仍有标签项未展开]，
    R = 尚未展开的正文词元数；从未见过的节点用可检索层最短节点的 g_min 代入 ub(0, False, g_min)。
  * 精排只对 ub ≥ 当前第 limit 名的桶做，两种等价方式（与 retrieval.relevance 逐值相等）：
      - 判定精排：对桶内节点逐个点查剩余词元的倒排成员（PK 点查，不读正文），得到精确 k/标签；
      - 正文精排：剩余词元很多时改读正文直接算分。
  * 精确分相同的一组节点只取 (importance 降序, id 升序) 的前 limit 个入围（SQL 内排序截断；
    组外节点在全局排序里必被组内 limit 个压住），且分数低于当前第 limit 名的组不回表。
  * 「可证完成」= 所有未精排的已见节点与未见节点的上界都 < 第 limit 名 ⇒ 结果与暴力全库精排相同。
  * 全部词元展开后 k 即真实交集数：整桶同分，直接按组入围（只回表取 id/importance）。
预算：累计倒排行数将超 ``BUDGET`` 时停止展开新节点（``approx``）；剩余词元只对已见节点做成员判定
（:meth:`Expansion.settle`），已见节点的分数因而仍精确，漏掉的只可能是未见节点。
"""
from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from .store.schema import chunks, placeholders

__all__ = ["Expansion", "TAG_BONUS"]

TAG_BONUS = 0.05
#: 正文精排一个节点的代价（以「一次倒排成员点查」为单位）；剩余词元数超过它时改读正文
CONTENT_COST = 10
#: 上界的舍入余量（> 6 位小数舍入误差的一半）
SLACK = 1e-6
Scored = Dict[str, Tuple[float, float]]
Bucket = Tuple[int, bool, int]
Member = Callable[[str, Sequence[int]], List[int]]


class Expansion:
    """单次查询的展开状态机（只读库）。``member(term, nkeys)`` = 倒排成员点查。"""

    def __init__(self, db, q_len: int, g_min: int, use: Set[str], limit: int,
                 content_score: Callable[[str, str, Optional[bool]], float], rest_content: int, rest_tags: int,
                 member: Optional[Member] = None) -> None:
        self.db, self.Q, self.g_min, self.use, self.limit = db, q_len, max(1, g_min), use, max(0, limit)
        self.content_score = content_score          # (content, tags_json, 已知是否命中标签|None) -> 相关度
        self.member = member
        self.R, self.rest_tags = rest_content, rest_tags
        self.done: Set[int] = set()                 # 已精排的节点键 nkey（含层不符/未入围而被丢弃的）
        self.scored: Scored = {}                    # 节点 id → (相关度, importance)
        self.bk: Dict[Bucket, Set[int]] = {}        # 未精排的已见节点：(k, 是否命中标签, g) → nkey 集
        self.approx = False
        self._version = 0
        self._cache: Tuple[int, List[Tuple[float, Bucket, List[int]]]] = (-1, [])
        self._kth: Tuple[int, float] = (-1, 0.0)
        self._sv = 0                                # scored 的版本（kth 缓存键）

    # ------------------------------------------------------------ 上界
    def _bound(self, m: int, g: int, tagged: bool) -> float:
        """上界再加 :data:`SLACK`：分数四舍五入到 6 位可能比未舍入的上界高半个末位，同分必须仍算「够得着」。"""
        content = 0.0 if self.Q == 0 or m == 0 or g <= 0 else (m / self.Q) * (0.5 + 0.5 * min(1.0, m / g))
        b = min(1.0, content + (TAG_BONUS if tagged or self.rest_tags > 0 else 0.0))
        return b + SLACK if b > 0 else 0.0

    def ub(self, k: int, tagged: bool, g: int) -> float:
        """桶上界（见模块文档）。"""
        return self._bound(k + self.R, g, tagged)

    def ub_unseen(self) -> float:
        """从未见过的节点的上界（g 取全库最小值）。"""
        return self._bound(self.R, self.g_min, False)

    def kth(self) -> float:
        """当前第 limit 名的分数（不足 limit 名时为 0：任何正分都可能入选）。"""
        if self.limit == 0:
            return 2.0
        if len(self.scored) < self.limit:
            return 0.0
        if self._kth[0] != self._sv:
            self._kth = (self._sv, sorted((v[0] for v in self.scored.values()), reverse=True)[self.limit - 1])
        return self._kth[1]

    def eligible(self) -> List[Tuple[float, Bucket, List[int]]]:
        """未精排的桶，上界降序（门槛由调用方逐桶比对；状态未变时复用上次结果）。"""
        if self._cache[0] == self._version:
            return self._cache[1]
        out = [(self.ub(*key), key, ids) for key, ids in self.bk.items() if ids]
        res = sorted([(u, key, list(ids)) for u, key, ids in out if u > 0], key=lambda x: (-x[0], min(x[2])))
        self._cache = (self._version, res)
        return res

    def pending(self) -> int:
        """上界 ≥ 当前门槛、尚未精排的节点数。"""
        kth = self.kth()
        return sum(len(ids) for u, _, ids in self.eligible() if u >= kth)

    def unseen_cleared(self) -> bool:
        """从未见过的节点已不可能入选。"""
        u = self.ub_unseen()
        return u <= 0 or (len(self.scored) >= self.limit and u < self.kth())

    # ------------------------------------------------------------ 展开
    def _move(self, keys: Set[int], tag: bool) -> Set[int]:
        """把 keys 中已分桶的节点迁入 (k+1,t,g)（正文词元）或 (k,True,g)（标签项）；返回未分桶的余下键。"""
        moved: Dict[Bucket, Set[int]] = {}
        for (c, t, g), members in self.bk.items():
            if not keys:
                break
            if not members:
                continue
            mv = members & keys
            if mv:
                members -= mv
                keys -= mv
                moved.setdefault((c, True, g) if tag else (c + 1, t, g), set()).update(mv)
        for key, mv in moved.items():
            self.bk.setdefault(key, set()).update(mv)
        return keys

    def expand(self, rows: Sequence[Tuple[int, int]], tag: bool) -> None:
        """并入一个词元的倒排 [(nkey, g)]（同一词元的倒排内节点不重复）。

        按桶做集合运算（C 层完成）；倒排中从未见过的节点按 g 分组进 (1,False,g) / (0,True,g)。"""
        self._version += 1
        gmap = dict(rows)
        fresh = self._move(gmap.keys() - self.done, tag)
        k0, t0 = (0, True) if tag else (1, False)
        for nk in fresh:
            key = (k0, t0, gmap[nk])
            b = self.bk.get(key)
            if b is None:
                self.bk[key] = {nk}
            else:
                b.add(nk)
        if tag:
            self.rest_tags -= 1
        else:
            self.R -= 1

    def seen(self) -> Set[int]:
        """未精排的已见节点（各桶并集）。"""
        out: Set[int] = set()
        for members in self.bk.values():
            out |= members
        return out

    def settle(self, rest: Sequence[Tuple[int, str, bool]]) -> None:
        """预算触顶后：剩余词元只对**已见未精排**节点做成员判定（PK 点查），使其 k/标签变精确，
        随后可走按组入围。被舍弃的只有一个已展开词元都不含的未见节点（近似的唯一来源）。"""
        self._version += 1
        seen = sorted(self.seen())
        for _, term, tag in rest:
            self._move(set(self._members(term, seen)), tag)
            if tag:
                self.rest_tags -= 1
            else:
                self.R -= 1

    def _members(self, term: str, keys: Sequence[int]) -> List[int]:
        if self.member is not None:
            return self.member(term, keys)
        hits: List[int] = []
        for part in chunks(list(keys)):
            hits += [r[0] for r in self.db.all(
                f"SELECT nkey FROM node_terms WHERE term=? AND nkey IN ({placeholders(len(part))})", [term, *part])]
        return hits

    def _members_multi(self, terms: Sequence[str], keys: Sequence[int]) -> List[Tuple[str, int]]:
        """[(词元, nkey)]：keys 中含 terms 任一项的 (词元, 节点) 对——等价于逐词元 :meth:`_members` 的并
        （倒排主键 (term, nkey) 逐对点查，单条语句，键集以 JSON 传入不受变量上限影响）。"""
        if not terms or not keys:
            return []
        if self.member is not None and not hasattr(self.db, "conn"):
            return [(t, h) for t in terms for h in self.member(t, keys)]
        with self.db.lock:
            cur = self.db.conn.cursor()
            cur.row_factory = None
            return cur.execute(
                "SELECT term, nkey FROM node_terms WHERE term IN (SELECT value FROM json_each(?)) "
                "AND nkey IN (SELECT value FROM json_each(?))",
                (json.dumps(list(terms), ensure_ascii=False), json.dumps(list(keys)))).fetchall()

    # ------------------------------------------------------------ 精排
    def drain(self, cap: int, rest: Sequence[Tuple[int, str, bool]] = ()) -> bool:
        """按上界降序精排合格桶（每桶后刷新门槛）。全部词元已定（R=0 且无标签项）时整桶同分、
        不计代价；否则判定/正文精排的代价累计不超过 ``cap``（点查次数）。返回是否已无合格桶。"""
        exact = self.R == 0 and self.rest_tags == 0
        seek = len(rest) <= CONTENT_COST
        spent = 0
        for u, key, ids in list(self.eligible()):
            if u < self.kth():
                return True
            if exact:
                self._admit(self._score(key[0], key[1], key[2]), ids)
                self._mark_done(key, ids)
                continue
            cost = len(ids) * (len(rest) if seek else CONTENT_COST)
            if spent + cost > cap:
                return False
            spent += cost
            if seek:
                self._score_members(key, ids, rest)
            else:
                self._score_contents(key, ids)
        return True

    def _score(self, k: int, tagged: bool, g: int) -> float:
        """精确 (k, 标签, g) 下的相关度——与正文精排逐值相等（k = 真实交集数）。"""
        s = (k / self.Q) * (0.5 + 0.5 * k / g) if self.Q and k and g else 0.0
        return round(min(1.0, s + TAG_BONUS) if tagged else s, 6)

    def _score_members(self, key: Bucket, ids: Sequence[int], rest: Sequence[Tuple[int, str, bool]]) -> None:
        """判定精排：逐个剩余词元点查桶内节点的倒排成员，得精确 (k, 标签)，按同分组入围。"""
        k, tagged, g = key
        cnt = dict.fromkeys(ids, k)
        tg: Set[int] = set(ids) if tagged else set()
        is_tag = {term: tag for _, term, tag in rest}
        for term, h in self._members_multi(list(is_tag), ids):   # 计数与词元顺序无关：一条语句点查全部剩余词元
            if is_tag[term]:
                tg.add(h)
            else:
                cnt[h] += 1
        groups: Dict[Tuple[int, bool], List[int]] = {}
        for nk, c in cnt.items():
            groups.setdefault((c, nk in tg), []).append(nk)
        for (c, t), nks in sorted(groups.items(), reverse=True):
            self._admit(self._score(c, t, g), nks)
        self._mark_done(key, ids)

    def _admit(self, s: float, nks: Sequence[int]) -> None:
        """同分组入围：低于当前第 limit 名不回表；否则取组内 (importance 降序, id 升序) 前 limit 个。"""
        if s <= 0 or not nks or self.limit == 0:
            return
        if len(self.scored) >= self.limit and s < self.kth():
            return
        lay = sorted(self.use)
        with self.db.lock:
            cur = self.db.conn.cursor()
            cur.row_factory = None
            rows = cur.execute(
                "SELECT n.id, n.importance FROM node_index i JOIN nodes n ON n.id = i.node_id "
                "WHERE i.nkey IN (SELECT value FROM json_each(?)) "
                f"AND +n.layer IN ({placeholders(len(lay))}) "
                "ORDER BY COALESCE(n.importance, 0) DESC, n.id LIMIT ?",
                (json.dumps(list(nks)), *lay, self.limit)).fetchall()
        for nid, imp in rows:
            self.scored[nid] = (s, imp or 0.0)
        if rows:
            self._sv += 1

    def _score_contents(self, key: Bucket, ids: Sequence[int]) -> None:
        tagged = key[1]
        for part in chunks(list(ids)):
            for nid, content, tags_json, imp, layer in self.db.all(
                    f"SELECT n.id, n.content, n.tags, n.importance, n.layer FROM node_index i JOIN nodes n "
                    f"ON n.id = i.node_id WHERE i.nkey IN ({placeholders(len(part))})", part):
                if layer in self.use:
                    known = tagged if self.rest_tags == 0 else None
                    s = self.content_score(content or "", tags_json or "", known)
                    if s > 0:
                        self.scored[nid] = (s, imp or 0.0)
                        self._sv += 1
        self._mark_done(key, ids)

    def _mark_done(self, key: Bucket, ids: Sequence[int]) -> None:
        b = self.bk.get(key)
        if b is not None:
            b.difference_update(ids)
            if not b:
                del self.bk[key]
        self.done.update(ids)
        self._version += 1

    def top(self) -> List[Tuple[str, float]]:
        """相关度降序、同分 importance 降序、再按 id。"""
        items = sorted(self.scored.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
        return [(nid, v[0]) for nid, v in items[:self.limit]]


def tags_of(tags_json: str) -> List[str]:
    """标签 JSON → 列表（非法 JSON 视为无标签）。"""
    try:
        v = json.loads(tags_json) if tags_json else []
    except ValueError:
        return []
    return [str(t) for t in v] if isinstance(v, list) else []
