# -*- coding: utf-8 -*-
"""decay · 衰减 / 遗忘 / 巩固 / 情境层容量——一个确定性的维护周期

旧实现的缺陷类别：情境层 SQL 预筛 ``importance > 阈值`` 使越不重要越永生(#207)；
保护名单展开成 2N 个占位符、过 16383 条即每轮抛错(#257)；边衰减排除列表手写漏 SELF(#205)；
保护在衰减与 FIFO 上限两条遗忘路径都失效(#36)；矛盾边被当普通未验证边删掉(#115)；
结构层关系随情境端点被连带删除(#168)；归档值落在删除线上「归档即永生」(#210/#214)；
巩固只看 importance 前 1000 条(#258)、用增量前的副本判 %10(#94)；容量上限只活在
进程内存(#246)；遗忘按调用次数而非流逝时间(#176)。

不变量：
  T1 资格只由 LayerPolicy 推导；保护/no_forget/钉住（与不可遗忘层节点相连）用
     ``NOT EXISTS`` 子查询表达，SQL 变量数与名单大小无关。
  T2 一步衰减 = 边衰减 + 节点衰减，均为批量 SQL，O(N)；结果与逐行实现逐位相同
     （同为 IEEE 双精度乘法）。
  T3 删除线严格：值 < min 即删除；归档值 ≤ 删除线 ⇒ 被归档的节点在有限步内被遗忘。
  T4 被保护、带 no_forget / promotion_pending（待终裁提案，#167）、或被钉住的节点**永不**被自然遗忘或 FIFO 淘汰；
     OPPOSITE（矛盾登记）边不参与自然衰减，必须经复核处理。
  T5 时间核：:func:`elapsed_factor` 把墙钟流逝换算为等效单步因子，
     遗忘速率与调用频率无关。
"""
from __future__ import annotations

import math
import sqlite3
from typing import Dict, List, Optional, Tuple

from .layers import LayerPolicy
from .numeric import fraction, positive_int, require_finite, unit
from .store import Store
from .types import EdgeType, MemoryLayer, now

__all__ = ["Maintenance", "elapsed_factor"]


def elapsed_factor(factor: float, elapsed: float, nominal: float = 60.0) -> float:
    """T5：每 ``nominal`` 秒遗忘 ``factor`` 比例时，流逝 ``elapsed`` 秒的等效遗忘比例。"""
    f = fraction(factor, "factor")
    e = max(0.0, require_finite(elapsed, "elapsed"))
    return 1.0 - math.pow(1.0 - f, e / require_finite(nominal, "nominal"))


def safe_tags(alias: str) -> str:
    """``{alias}.tags`` 的 json_each 安全参数：非法 JSON 行按空标签处理（上游 #267：单条坏行不得让整条
    衰减 / 巩固 / 遗忘 SQL 抛 malformed JSON、毒化整层）。"""
    return f"CASE WHEN json_valid({alias}.tags) THEN {alias}.tags ELSE '[]' END"


def _guarded(alias: str) -> Tuple[str, Tuple[str, ...]]:
    """节点「不可被自然遗忘」的 SQL 条件与参数（T1/T4）。"""
    pinned_layers, lp = LayerPolicy.layers_where("p.layer", node_decays=False, edge_decays=False)
    return (f"(EXISTS (SELECT 1 FROM protections pr WHERE pr.node_id={alias}.id)"
            f" OR EXISTS (SELECT 1 FROM json_each({safe_tags(alias)}) WHERE value IN ('no_forget', 'promotion_pending'))"
            f" OR EXISTS (SELECT 1 FROM edges pe JOIN nodes p ON p.id = CASE WHEN pe.source_id={alias}.id"
            f" THEN pe.target_id ELSE pe.source_id END WHERE (pe.source_id={alias}.id OR pe.target_id={alias}.id)"
            f" AND {pinned_layers}))", lp)


class Maintenance:
    """维护周期执行器（无隐藏状态；参数显式传入）。"""

    def __init__(self, store: Store) -> None:
        self.store = store

    # ------------------------------------------------------------ 衰减
    def _edge_scope(self) -> tuple:
        """可衰减边的条件（只引用 edges 列 + 一张阻断端点临时表，便于单趟条件化 UPDATE）。

        阻断端点 = 层不参与边衰减（含层缺失）的节点 ∪ 受保护节点；两端都不阻断、未验证、
        非 OPPOSITE 的边可衰减——与「两端层 edge_decays 且无保护」逐条等价（外键保证端点存在）。
        """
        ok, ok_p = LayerPolicy.layers_where("layer", edge_decays=True)
        fill = (f"INSERT INTO _ng_blocked SELECT id FROM nodes WHERE layer IS NULL OR NOT ({ok}) "
                "UNION SELECT node_id FROM protections")
        cond = ("verified=0 AND relation_type != ? AND source_id NOT IN (SELECT id FROM _ng_blocked) "
                "AND target_id NOT IN (SELECT id FROM _ng_blocked)")
        return fill, ok_p, cond, (EdgeType.OPPOSITE.value,)

    def decay_edges(self, factor: float, min_confidence: float) -> Dict[str, int]:
        """未验证边置信度 ×(1-factor)，低于 min_confidence 删除（T2/T4）；单趟条件化 UPDATE + 条件 DELETE。"""
        f, m = fraction(factor), unit(min_confidence, "min_confidence")
        fill, fp, cond, cp = self._edge_scope()
        with self.store.db.tx() as c:
            c.execute("CREATE TEMP TABLE IF NOT EXISTS _ng_blocked (id TEXT PRIMARY KEY) WITHOUT ROWID")
            c.execute("DELETE FROM _ng_blocked")
            c.execute(fill, fp)
            touched = c.execute(f"UPDATE edges SET confidence = COALESCE(confidence, 0) * (1.0 - ?) WHERE {cond}",
                                (f,) + cp).rowcount
            dropped = c.execute(f"DELETE FROM edges WHERE confidence < ? AND {cond}", (m,) + cp).rowcount
        return {"edges_decayed": touched - dropped, "edges_forgotten": dropped}

    def decay_nodes(self, factor: float, min_importance: float) -> Dict[str, int]:
        """可衰减层节点 importance ×(1-factor)，低于阈值即遗忘（无预筛，T3/T4）。"""
        f, m = fraction(factor), unit(min_importance, "min_importance")
        cond, params = LayerPolicy.layers_where("n.layer", node_decays=True)
        g, gp = _guarded("n")
        scope, params = f"SELECT n.id FROM nodes n WHERE {cond} AND NOT {g}", params + gp
        with self.store.db.tx() as c:
            c.execute("CREATE TEMP TABLE IF NOT EXISTS _ng_nscope (id TEXT PRIMARY KEY)")
            c.execute("DELETE FROM _ng_nscope")
            c.execute(f"INSERT INTO _ng_nscope {scope}", params)
            # 旧库坏行（上游 #185）：NULL/NaN → 0，±inf 与越界值先钳到 [0,1] 再衰减——不得因 inf 永生
            c.execute("UPDATE nodes SET importance = MIN(MAX(COALESCE(importance, 0), 0.0), 1.0) * (1.0 - ?) "
                      "WHERE id IN (SELECT id FROM _ng_nscope)", (f,))
            gone = "SELECT id FROM nodes WHERE id IN (SELECT id FROM _ng_nscope) AND importance < ?"
            c.execute(f"DELETE FROM edges WHERE source_id IN ({gone}) OR target_id IN ({gone})", (m, m))
            n = c.execute(f"DELETE FROM nodes WHERE id IN ({gone})", (m,)).rowcount
            total = c.execute("SELECT COUNT(*) FROM _ng_nscope").fetchone()[0]
        return {"nodes_decayed": total - n, "nodes_forgotten": n}

    def step(self, factor: float = 0.02, min_confidence: float = 0.1) -> Dict[str, int]:
        """一步衰减（边 → 节点，同一阈值，与旧语义一致）。"""
        out = self.decay_edges(factor, min_confidence)
        out.update(self.decay_nodes(factor, min_confidence))
        return out

    # ------------------------------------------------------------ 主动遗忘
    def forget_advisor(self, stale_days: float = 30.0, low_value: float = 0.2,
                       archived_imp: float = 0.1) -> Dict[str, object]:
        """未被使用/低价值的情境记忆归档：importance → min(原值, archived_imp)，打 archived。"""
        stale = require_finite(stale_days, "stale_days") * 86400.0
        low, arch = unit(low_value, "low_value"), unit(archived_imp, "archived_imp")
        cond, params = LayerPolicy.layers_where("n.layer", node_decays=True)
        t = now()
        g, gp = _guarded("n")
        rows = self.store.db.all(
            f"SELECT n.id, n.importance, n.access_count, n.last_access FROM nodes n WHERE {cond} "
            f"AND NOT {g} AND NOT EXISTS "
            f"(SELECT 1 FROM json_each({safe_tags('n')}) WHERE value='archived')", params + gp)
        archived = kept = 0
        with self.store.db.tx():
            for nid, imp, acc, la in rows:
                imp = 0.0 if imp is None else float(imp)
                idle = (acc or 0) == 0 and (t - (la if la is not None else t)) > stale
                if idle or imp < low:
                    self.store.nodes.update(nid, importance=min(imp, arch))
                    self.store.nodes.add_tags(nid, ["archived"])
                    archived += 1
                else:
                    kept += 1
        return {"archived": archived, "kept": kept,
                "note": "主动遗忘：未被使用的情境记忆归档（只降不升，归档值≤删除线⇒有限步内遗忘）"}

    # ------------------------------------------------------------ 巩固
    def consolidate(self, rehearsal_threshold: float = 0.7, degrade_threshold: float = 0.2,
                    gain: float = 0.01) -> Dict[str, int]:
        """全量（无 LIMIT）巩固：高重要度演练、低重要度降权、极低标 compressible。"""
        step = unit(gain, "gain")
        hi, lo = unit(rehearsal_threshold), unit(degrade_threshold)
        cond, params = LayerPolicy.layers_where("n.layer", shared=False, searchable=True)
        stats = {"rehearsed": 0, "boosted": 0, "degraded": 0, "compressible": 0}
        g, gp = _guarded("n")
        # 上游 #263：未复核的归纳概念（pending_verification）不参与演练提权——否则维护周期每 10 轮 +gain，
        # 一条未经验证的「概念」被抬到 1.0、挤占召回前列。
        rows = self.store.db.all(f"SELECT n.id, n.importance, n.access_count, EXISTS (SELECT 1 FROM json_each("
                                 f"{safe_tags('n')}) WHERE value = 'pending_verification') FROM nodes n "
                                 f"WHERE {cond} AND NOT {g}", params + gp)
        with self.store.db.tx():
            for nid, imp, acc, pending in rows:
                imp, acc = (imp or 0.0), (acc or 0)
                if imp >= hi and pending:
                    continue
                if imp >= hi:
                    self.store.nodes.touch([nid])
                    stats["rehearsed"] += 1
                    if (acc + 1) % 10 == 0:
                        self.store.nodes.update(nid, importance=min(1.0, imp + step))
                        stats["boosted"] += 1
                elif imp < lo:
                    if acc <= 2:
                        imp = max(0.0, imp - step)
                        self.store.nodes.update(nid, importance=imp)
                        stats["degraded"] += 1
                    if imp < 0.08:
                        self.store.nodes.add_tags(nid, ["compressible"])
                        stats["compressible"] += 1
        return stats

    # ------------------------------------------------------------ 情境层容量
    def context_cap(self, default: int = 200) -> int:
        """持久化容量上限（engine_meta.context_cap；同库多实例共享，重启不丢，#246）。"""
        raw = self.store.meta.get("context_cap").get("context_cap")
        return positive_int(int(raw), "context_cap") if raw else default

    def set_context_cap(self, cap: int) -> int:
        """设置并持久化上限，随即执行一次淘汰；返回淘汰数。"""
        self.store.meta.set("context_cap", positive_int(cap, "context_cap"))
        return self.enforce_cap()

    def _fifo_page(self, n: int, offset: int) -> List[str]:
        """情境层按 FIFO 序的第 offset 起 n 个 id。FIFO 序 = **写入顺序**（rowid 单调递增），不是墙钟
        created_at——墙钟会回拨（NTP / 快照恢复 / 无 RTC 开机），调用方也可自带未来时间戳；按 created_at
        排，新写入会被自己的 FIFO 当场淘汰（上游 #259）。走部分索引 idx_nodes_ctx_seq（免全层排序）；
        索引不存在（如只读打开的旧库未迁移）时退回普通查询，结果相同。"""
        try:
            rows = self.store.db.all("SELECT id FROM nodes INDEXED BY idx_nodes_ctx_seq WHERE layer='context' "
                                     "ORDER BY rowid ASC LIMIT ? OFFSET ?", (n, offset))
        except sqlite3.OperationalError:
            rows = self.store.db.all("SELECT id FROM nodes WHERE layer=? ORDER BY rowid ASC "
                                     "LIMIT ? OFFSET ?", (MemoryLayer.CONTEXT.value, n, offset))
        return [r[0] for r in rows]

    def enforce_cap(self, cap: Optional[int] = None) -> int:
        """FIFO 淘汰最旧的可遗忘情境节点（受保护/钉住者不计入淘汰候选，T4）。"""
        limit = self.context_cap() if cap is None else positive_int(cap, "cap")
        total = self.store.nodes.count(MemoryLayer.CONTEXT)
        excess = max(0, total - limit)
        if excess == 0:
            return 0                                   # 未超限：零扫描、零事务
        g, gp = _guarded("n")
        victims: List[str] = []
        step = min(excess + 4, 400)
        for i in range(0, total, step):               # 按 FIFO 序分批取、判守卫，凑够 excess 即停
            part = self._fifo_page(step, i)
            if not part:
                break
            ok = {r[0] for r in self.store.db.all(
                f"SELECT n.id FROM nodes n WHERE n.id IN ({','.join('?' * len(part))}) AND NOT {g}",
                tuple(part) + gp)}
            victims += [x for x in part if x in ok][:excess - len(victims)]
            if len(victims) >= excess:
                break
        with self.store.db.tx():
            for nid in victims:
                self.store.nodes.delete(nid, force=True)
        return len(victims)
