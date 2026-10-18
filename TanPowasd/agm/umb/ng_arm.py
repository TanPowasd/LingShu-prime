# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""外部对照臂 ng：Liyang1145/lingshu-ng（MIT）的零模型默认召回，只读调用、不复制其代码。

接入方式（白箱，显式条件）：
  · 仓外克隆路径由 $UMB_NG 给出（含 lingshu_ng/ 包的目录）；只在 run_umb.py 的单集子进程里插到 sys.path 首位，
    未设 / 路径不含包 ⇒ SystemExit（不静默跳过）。克隆 HEAD 记入缓存 meta（git rev-parse，读不到记"存疑"）。
  · 零模型：构造前清掉 ng 的可选通路环境变量（LINGSHU_NG_EMBED_MODEL / RERANK_MODEL / NEURAL / CHAIN / LEXICAL / ASSOC），
    并设 LINGSHU_NG_SEM=off（明确关语义件）；构造后断言 engine.semantic is None、retriever.neural is None、chain is None。
    lexical / assoc 配置 = ng 默认（不传 lexical 参数）。
  · 每个会话 / 文档集新建 MemoryEngine(":memory:")，按给定写入序逐条 perceive(text)：importance=0.5、confidence=0.5、
    tags 不传（单元 id 不放 tags：ng 把标签写进倒排作「标签 ⊂ 查询」加分项（store/textindex.py TAG_PREFIX），
    放进去会改变 ng 的打分），去重开（skip_dedup=False，ng 默认 M5）。映射改由 perceive 返回的 node_id 精确维护。
  · 时钟：用 ng 公开的测试注入口 lingshu_ng.types.set_clock 钉在 CLOCK（2026-01-01T00:00:00Z）。
    于是全部单元的 created_at/last_access 相同、召回时 recency 恒为 1（墙钟下秒级差会进 6 位小数组合分，结果不可复现；
    召回会 touch last_access，钉钟也消除了题与题之间经 recency 的相互影响）。access_count 仍累加（ng 组合分不读它）。
  · 映射：perceive 返回 node_id；action=merged ⇒ 该单元并入已有节点，node→[单元序号...] 一对多（记 merged 数、涉及节点数）。
    召回结果展开为该节点全部单元（按写入序），同一单元不重复；ng 返回不足 n 时以未出现单元按写入序补尾（同 run_umb okapi_rank 口径）。
    每题记 nh（ng 实返节点数）与 amb（前 10 名中一对多节点数）。
  · 题与题顺序执行，引擎在题间共享（ng 默认召回会写 flywheel/access 计数，组合分不读）。
  · 消融变体（VARIANTS，臂名 ngv_<名>，只记忆集）：构造后经 ng 公开接口改配置——词级通路 MemoryEngine.set_lexical(**覆盖)
    （compat 层同名 set_lexical_config 即委托此方法），中文联想 retriever.assoc = dataclasses.replace(…)（assoc.py 文件头登记的
    配置入口）；不改 ng 代码。生效配置 repr 记入缓存 meta。"""
import os, subprocess, sys

CLOCK = 1767225600.0
_OFF = ("LINGSHU_NG_EMBED_MODEL", "LINGSHU_NG_RERANK_MODEL", "LINGSHU_NG_RERANK_TOPN", "LINGSHU_NG_NEURAL",
        "LINGSHU_NG_CHAIN", "LINGSHU_NG_LEXICAL", "LINGSHU_NG_ASSOC")
_loaded = {}
#: 消融变体：名 → (词级覆盖, 联想覆盖)。默认值见 lingshu_ng/lexical.py LexicalConfig、assoc.py AssocConfig（ng 2521f7f）。
VARIANTS = {
    "ctx0": ({"ctx_beta": 0.0}, {}),                       # 关英文写入序上下文聚合（默认 β .8、span 3、decay .6）
    "fill10": ({"ctx_fill": 10}, {}),                      # ng 自带可选项：前 10 名零分邻居也纳入聚合（描述性，非默认）
    "co0": ({"co_w": 0.0}, {}),                            # 关 C1 词元共现扩散（默认 .3）
    "hd0": ({"hd_n": 0}, {}),                              # 关 H2 头部精排（默认前 10 名 cov 精排）
    "div0": ({"diversify": False}, {}),                    # 关 R2 长块相邻写入惩罚（词级通路）
    "lexbase": ({"ctx_beta": 0.0, "co_w": 0.0, "hd_n": 0, "diversify": False}, {}),   # 以上四项全关：裸 BM25+SDM
    "anc0": ({}, {"anchor_span": 0}),                      # 关中文 AX1 锚定局部展开（span 0 ⇒ 无邻居）
    "lc0": ({}, {"lc_beta": 0.0}),                         # 关中文 LC 长预算邻接补全（limit > lc_head=15 才启用；hive k=50）
    "ax0": ({}, {"enabled": False}),                       # 中文联想整体关（AX1/LC/TP/HD）
    "both0": ({"ctx_beta": 0.0}, {"anchor_span": 0}),      # 英文上下文聚合 + 中文锚定展开同时关
}


def setup():
    """→ ng 元信息 dict（路径不入库，只记 HEAD 与生效配置）。"""
    if _loaded:
        return _loaded
    root = os.environ.get("UMB_NG")
    if not root or not os.path.isfile(os.path.join(root, "lingshu_ng", "engine.py")):
        raise SystemExit("存疑：未设 UMB_NG 或其下无 lingshu_ng/engine.py（指向 lingshu-ng 克隆根目录）")
    for k in _OFF:
        os.environ.pop(k, None)
    os.environ["LINGSHU_NG_SEM"] = "off"
    sys.path.insert(0, root)
    import lingshu_ng.types as NT
    from lingshu_ng.engine import MemoryEngine
    NT.set_clock(lambda: CLOCK)
    try:
        head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30).stdout.strip() or "存疑"
        dirty = subprocess.run(["git", "-C", root, "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        head, dirty = f"存疑：{type(e).__name__}", ""
    e = MemoryEngine(":memory:")
    _check(e)
    _loaded.update({"ME": MemoryEngine, "head": head, "tracked_dirty": bool(dirty), "clock": CLOCK,
                    "lexical": repr(e.lexical), "assoc": repr(e.retriever.assoc), "dedup_threshold": e.dedup_threshold})
    e.close()
    return _loaded


def apply_variant(e, variant):
    """→ (生效词级配置, 生效联想配置)；未知变体 ⇒ KeyError（不静默回退默认）。"""
    import dataclasses
    lex, ax = VARIANTS[variant]
    lc = e.set_lexical(None, **lex) if lex else e.retriever.lexical
    if ax:
        e.retriever.assoc = dataclasses.replace(e.retriever.assoc, **ax)
    for k, v in lex.items():
        assert getattr(e.retriever.lexical, k) == v, (variant, k)
    for k, v in ax.items():
        assert getattr(e.retriever.assoc, k) == v, (variant, k)
    return lc, e.retriever.assoc


def _check(e):
    assert e.semantic is None and e.retriever.neural is None and e.chain is None, "ng 可选通路未关（零模型前提不成立）"


class NgIndex:
    def __init__(self, texts, order=None, variant=None):
        """texts：单元正文（下标 = 单元序号）；order：写入序（默认 0..n-1）；variant：VARIANTS 键（None = ng 默认）。"""
        M = setup()
        self.n = len(texts)
        self.e = M["ME"](":memory:")
        _check(self.e)
        if variant is not None:
            apply_variant(self.e, variant)
        self.of = {}                     # node_id → [单元序号]
        self.stats = {"units": self.n, "merged": 0, "rejected": 0}
        for i in (range(self.n) if order is None else order):
            try:
                r = self.e.perceive(texts[i])
            except (TypeError, ValueError):   # ng inputs：非 str / 孤立代理码位 ⇒ 拒收，该单元永不被召回（计数入 rejected）
                self.stats["rejected"] += 1; continue
            self.of.setdefault(r.node_id, []).append(i)
            if r.action == "merged":
                self.stats["merged"] += 1
        for v in self.of.values():
            v.sort()
        self.stats["nodes"] = len(self.of)
        self.stats["multi_nodes"] = sum(len(v) > 1 for v in self.of.values())

    def rank(self, q, limit, pad=True):
        """→ (单元序号排序, nh, amb)。"""
        hits = self.e.recall(q, limit=limit)["hits"] if (q or "").strip() else []
        out, seen, amb = [], set(), 0
        for k, (node, _) in enumerate(hits):
            us = self.of.get(node.id)
            if us is None:                # 非 perceive 写入的节点（ng 不应产生）：显式记账，不静默
                self.stats["foreign_hits"] = self.stats.get("foreign_hits", 0) + 1; continue
            if len(us) > 1 and k < 10:
                amb += 1
            for u in us:
                if u not in seen:
                    seen.add(u); out.append(u)
        nh = len(hits)
        if pad:
            out += [i for i in range(self.n) if i not in seen]
        return out, nh, amb

    def close(self):
        self.e.close()
