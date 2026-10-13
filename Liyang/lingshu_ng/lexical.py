# -*- coding: utf-8 -*-
"""lexical · 按语言分词的词面检索（gen-v1；零 LLM、只读）

ng 原词面检索（:mod:`lingshu_ng.retrieval` Q1/Q2 + :mod:`lingshu_ng.rerank` R1）对一切文字都取规范化字二元组，
相关度 = 覆盖率 × (0.5 + 0.5·精确率)。中文上它是合适的（HMB 检索轨与 BM25 持平），但在英文长对话上有两处结构缺陷
（LongMemEval_S 会话 recall_any@5 0.604 vs 整轮 BM25+SDM 0.951；诊断 prime-test/out/item4_diag_lme.json）：
  1. 英文也按字二元组算——"th""he""in" 这类跨词二元组几乎每轮都有，区分度极低；
  2. 覆盖率没有长度归一：长助手轮覆盖的二元组多，挤掉了短而精确的用户轮。

本模块给「以拉丁文字为主」的查询换一条词面通路（中文查询仍走原通路，逐位不变）：
  L1 分词：NFKC + casefold；拉丁/数字串按词切分，去英文停用词，做轻量词干（复数、-ing/-ed/-ly、尾 e）；
     中日韩串取字二元组（单字串取单字）。:func:`tokens`。
  L2 索引：拉丁词干以 ``WORD_PREFIX`` + 词干写进同一张派生倒排（store.textindex，写时维护，df 精确）；
     中日韩二元组与原索引词元相同（规范化二元组的子集），不重复登记。
  L3 打分：BM25（k1、b；dl/avgdl 以正文字符数计，avgdl 读库内统计并缓存）
     + SDM 邻近项（相邻查询词的有序紧邻 #1 与无序窗口 #uwN，各按 BM25 饱和函数计）
     + 可选段落项（正文切成定长词窗，取最佳窗的 BM25，缓解「长轮里只有一处相关」被长度归一压低）
     + 可选上下文聚合（写入序相邻节点的分数按 β 叠加：同一会话前后轮彼此作证）。
     相关度 = 分数 / 池内最高分（∈[0,1]，与原相关度同量纲，Q4 组合分权重不变）。
  L4 候选：查询词元按 df 升序（idf 降序）展开倒排，累计行数超 ``budget`` 停止展开；
     以「已命中词元 idf 和」取前 ``cand_max`` 名精排。候选不超过 cand_max 且未超预算时与暴力全库精排
     (:func:`brute_force_v2`) 逐名次相同。

配置 :class:`LexicalConfig`：引擎构造参数 / ``MemoryEngine.set_lexical`` / 环境变量 ``LINGSHU_NG_LEXICAL``（JSON 覆盖）。
``enabled=False`` 即完全回到旧通路。
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from sys import intern as _intern
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = ["LexicalConfig", "WORD_PREFIX", "STOPWORDS", "stem", "tokens", "query_terms", "index_words",
           "is_latin_query", "mixed_route", "cjk_ratio", "Scorer", "config_from_env", "LEXV",
           "seed_diffusion", "rrf_fuse", "diffuse_fuse", "cluster_diversify", "split_label"]

#: 拉丁词干词元前缀（\x1e 为控制字符，规范化正文二元组与标签项（\x1f）里都不可能出现）
WORD_PREFIX = "\x1e"
#: 派生索引里词元格式的版本（变更分词规则时加一，旧库在打开时整体记脏重建）
LEXV = "1"

STOPWORDS = frozenset("""
a about above after again against all am an and any are aren't as at be because been before being below between
both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each few for from
further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his
how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor
not of off on once only or other ought our ours ourselves out over own same shan't she she'd she'll she's should
shouldn't so some such than that that's the their theirs them themselves then there there's these they they'd
they'll they're they've this those through to too under until up very was wasn't we we'd we'll we're we've were
weren't what what's when when's where where's which while who who's whom why why's with won't would wouldn't you
you'd you'll you're you've your yours yourself yourselves also just will shall may might must s t d ll m re ve
""".split())

_CJK = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af"
_RUN_PAT = rf"([{_CJK}]+)|([^\W_{_CJK}]+(?:'[^\W_{_CJK}]+)*)"


@lru_cache(maxsize=1)
def _run_re() -> "re.Pattern":
    """stab-r5：分词主正则懒编译（编译约 4 ms，只在首次分词时付出；模式与旧 ``_RUN`` 逐字相同）。"""
    return re.compile(_RUN_PAT)


_VOWEL = re.compile(r"[aeiouy]")
#: H1 说话人标签：字母开头、≤ 32 字符、后接冒号与空白
_LABEL = re.compile(r"^\s*([^\W\d_][\w.'\- ]{0,31}?):\s+")
_FAR = -10 ** 6


def split_label(content: str) -> Tuple[str, str]:
    """H1：正文开头的说话人标签 → (标签, 余下正文)；无标签（或标签超过 3 词）⇒ ("", 原文)。"""
    m = _LABEL.match(content)
    if not m or len(m.group(1).split()) > 3:
        return "", content
    return m.group(1), content[m.end():]


@dataclass(frozen=True)
class LexicalConfig:
    """词面通路配置（默认值即 gen-v1 交付默认；b / ctx_* 由 dev 扫参选定，见 bench_gen/REPORT_GEN_v1.md，
    其余取文献常用值：BM25 k1=1.2、SDM 0.85/0.10/0.05、无序窗口 8）。"""
    enabled: bool = True
    #: 查询中日韩字符占（中日韩字符 + 拉丁字母）的比例 ≥ 此值 ⇒ 走旧通路
    route_cjk: float = 0.3
    #: 混合查询的库感知路由（gen-v1 v2；< 0 = 关）：查询同时含中日韩与拉丁字母词元、中日韩占比 ≥ route_cjk 时，
    #: 若**库**的中日韩词元份额（Σdf(中日韩二元组) / Σdf(中日韩二元组 + 拉丁字母词)）≤ route_corpus，
    #: 且查询至少一个拉丁字母词元在库中出现 ⇒ 仍走词级通路（中文句式 + 英文内容词去查以英文为主的库）。
    #: 以中文为主的库份额 ≈ 0.95–1.0，结果与 v1 逐位相同；纯英文库 ≈ 0。gen-v1 v2 默认 0.5（dev 选定，见
    #: bench_gen/PREREG.md 修订 4）；-1 = 关（v1 行为）。
    route_corpus: float = 0.5
    stem: bool = True
    stop: bool = True
    k1: float = 1.2
    b: float = 0.5
    #: SDM 权重：词项 / 有序紧邻 / 无序窗口
    w_t: float = 0.85
    w_o: float = 0.10
    w_u: float = 0.05
    window: int = 8
    #: 段落项：词窗长度（0 = 关）与权重 γ（相关分 = (1−γ)·整节点 + γ·最佳词窗）
    passage: int = 0
    gamma: float = 0.0
    #: 上下文聚合：写入序相邻（|Δrowid| ≤ ctx_span）节点分数的最大值 × β 叠加（0 = 关）
    ctx_beta: float = 0.8
    ctx_span: int = 3
    #: 距离 d 的邻居权重 = β·ctx_decay^(d−1)
    ctx_decay: float = 0.6
    #: 方向系数：来自先写入邻居（rowid 更小）/ 后写入邻居的贡献再乘以 ctx_prev / ctx_next
    ctx_prev: float = 1.0
    ctx_next: float = 1.0
    #: 上下文补位：前 ctx_fill 名的写入序邻居即使本身零分也纳入（分数 = β·decay^(d−1)·来源分；0 = 关）
    ctx_fill: int = 0
    #: 伪相关反馈（RM3 式）：取首轮前 prf_docs 名的正文，按 Σ(tf/|d|)·idf 选 prf_terms 个新词元，
    #: 以 prf_weight·(词分/最高词分) 为查询权重对首轮非零分节点重排（0 = 关）
    prf_docs: int = 0
    prf_terms: int = 10
    prf_weight: float = 0.3
    #: 种子扩散第二路（gen-v3 D1；dif_w = 0 关）：BM25+SDM 原始分前 dif_seeds 名为种子（按分数归一成个性化向量 p），
    #: 在写入序邻接图（|Δrowid| ≤ dif_span，边权 dif_decay^(d−1)，行归一）上做 dif_steps 步个性化 PageRank 迭代
    #: a ← α·p + (1−α)·M·a（α = dif_alpha），含零词面分的邻轮；所得激活名次与主排序（词级 + 上下文聚合）做
    #: 加权 RRF：f = 1/(rrf_k + r_主) + dif_w/(rrf_k + r_扩散)，相关度 = f / max f。
    dif_w: float = 0.0
    dif_seeds: int = 20
    dif_span: int = 2
    dif_decay: float = 0.6
    dif_steps: int = 2
    dif_alpha: float = 0.5
    rrf_k: float = 60.0
    #: 写入序簇多样化（gen-v3 D2；div_win = 0 关）：按最终分从高到低贪心，节点分数乘 div_pen^c，
    #: c = 已入选（分更高）节点中与它 |Δrowid| ≤ div_win 的个数；只重排前 div_top 名之内的节点。
    div_win: int = 0
    div_pen: float = 0.7
    div_top: int = 60
    #: gen-v3 r3 C1 词元共现扩散（co_w = 0 关；:mod:`lingshu_ng.cooc`）：主排序前 co_seeds 名为种子，各取 idf 最高的
    #: co_terms 个词元（2 ≤ df ≤ co_dfmax·N；co_qexcl 排除查询词元），沿倒排扩散一步得第二路名次，与主排序 RRF（k = co_k）；
    #: co_gate > 0 ⇒ 门控：只有共现名次 ≤ co_gate 且主名次 > 10（或无主分）的节点加第二路项。
    #: gen-v3 冻结值（r3 dev 选定，PREREG_GEN_v3 修订 2/3）：w .3、S 5、T 10、dfmax .03、排除查询词元、k 10；
    #: r4 候选 v3.1（d8a7030：w .25、co_head 6）在 H-CM4 上 J1 不过（对 v3 r@10 −.0034，CI 上界 < 0）⇒ 默认值保持 v3。
    co_w: float = 0.3
    co_seeds: int = 5
    co_terms: int = 10
    co_dfmax: float = 0.03
    co_qexcl: bool = True
    co_k: float = 10.0
    co_gate: int = 0
    #: r4（PREREG_GEN_v3 修订 4/5）：E1 头部保护前 co_head 名（默认关；v3.1 候选为 6）；E2a 第 1/第 6 名分比 ≥ co_conf 不启用（默认关）；E2b 计数/时间类问句不启用
    #: （co_qtype：0 关、1 宽版计数/时间/顺序、2 窄版计数/汇总）
    co_head: int = 0
    co_conf: float = 0.0
    co_qtype: int = 0
    #: gen-v3 r3 C2 种子层 + 邻轮补位（nb_s0 = 0 关）：主排序前 nb_s0 名之后插入前 nb_m 名的写入序后继轮（nb_prev 再加前驱）
    nb_s0: int = 0
    nb_m: int = 2
    nb_prev: bool = False
    #: gen-v3 r6 H1 说话人前缀（PREREG_GEN_v3 修订 7；0 关）：正文以「标签: 」开头（字母开头、≤ 32 字符、≤ 3 词）时，
    #: 1 = 标签不计长度、不与正文构成 SDM 词对（仍可作词项命中）；2 = 标签词元整体剥离
    spk: int = 0
    #: gen-v3 r6 H2 头部精排（hd_n = 0 关）：最终排序前 hd_n 名内按 rel/max + hd_own·own + hd_cov·cov + hd_prox·prox 重排，
    #: 原分数按新次序重新分配（第 hd_n+1 名以后不变）。own = 自身 BM25+SDM 原始分 / 前 N 名最大；cov = 命中查询词 qtf·idf 占比；
    #: prox = 命中不同查询词数 m ≥ 2 时 m / 最短覆盖词窗长，否则 0。
    #: gen-v3.2 交付值（r6 dev 选定、H-CM6 判定通过，PREREG_GEN_v3 修订 7b）：hd_at 1、hd_n 10、hd_cov 1（own / prox 关）；
    #: hd_n = 0 一行回到 v3（LINGSHU_NG_LEXICAL='{"hd_n":0}'）。
    hd_n: int = 10
    hd_own: float = 0.0
    hd_cov: float = 1.0
    hd_prox: float = 0.0
    #: H2 放置（修订 7a）：0 = 词级通路内（Q4 组合分之前；第 1 次迭代）；1 = 召回最终名次上（Q4 组合分与 R2 多样化之后，
    #: 前 hd_n 名集合严格不变）
    hd_at: int = 1
    #: gen-v3 r7 F1/F2 稠密–稀疏融合（PREREG_GEN_v3 修订 8/8b；sf = 0 ⇒ 语义第二路仍按 semindex.PATTERN 交错）：只在英文词级通路且
    #: 注入了语义提供者时生效（:mod:`lingshu_ng.densefuse`）。f = 1/(sf_k + r_词面) + sf_w/(sf_k + r_稠密)；稠密取前 sf_n 名；
    #: sf_adj > 0 ⇒ 稠密候选把 sf_adj × 自身稠密项传给写入序 ±1 邻轮。rel 默认 = r7 冻结配置（无语义模型时不生效，逐位同 v3.2）。
    sf: int = 1
    sf_w: float = 2.0
    sf_k: float = 10.0
    sf_n: int = 60
    sf_adj: float = 0.0
    #: gen-v3 r8/r9 F3（PREREG_GEN_v3 修订 9b 冻结、修订 10 H-CM9 判定）：sf_mx > 0 ⇒ 融合后前 sf_mxn 名按 bge 逐词向量 MaxSim 名次
    #: 再加 RRF 项 sf_mx/(sf_k + r_mx) 精排（ColBERT 式晚交互）；sf_qp = 1 ⇒ 稠密路查询加 BGE 检索指令前缀；
    #: 2 ⇒ 只对问句形式加（F3b'）；3 ⇒ 原句与加前缀两路稠密名次各半权重（F3b''）。无语义模型时不生效。
    #: rel 默认 = 修订 9b 冻结 F3（gen-r9 H-CM9 判定通过）：问句路由前缀 + MaxSim 精排前 20。
    sf_mx: float = 1.0
    sf_mxn: int = 20
    sf_qp: int = 2
    #: gen-v3 r10 F4 说话人意图先验（PREREG_GEN_v3 修订 11/11b；默认关）：sp > 0 ⇒ 融合（及 F3a）后的前 sp_n 名里，
    #: 与查询指向（助手/用户，:func:`lingshu_ng.speaker.query_intent`）一致的轮再加 sp/(sf_k + 一致者名次)；
    #: 轮的说话人 = 角色前缀，否则伪说话人推断，sp_win > 0 时再按写入序 ±sp_win 邻轮交替结构平滑。
    sp: float = 0.5   # gen-r10 H-CM10 判定后设为缺省（只在 sf ≠ 0 且注入语义模型时生效；sp = 0 逐位退回 rel-v1.8）
    sp_n: int = 40    # gen-r13 F4w（PREREG_GEN_v3 修订 14，H-CM11 判定）：20 → 40；只影响前 40 名内的重排（r@25/all@25），r@5/r@10 不变
    sp_win: int = 2
    #: 候选精排上限与倒排展开行数预算
    cand_max: int = 3000
    budget: int = 200000
    #: 召回第二阶段是否保留 R2 长块多样化（相邻写入惩罚）
    diversify: bool = True

    def with_overrides(self, **kw) -> "LexicalConfig":
        """返回覆盖了已知字段的新配置（未知键忽略）。"""
        known = {k: v for k, v in kw.items() if k in self.__dataclass_fields__}
        return replace(self, **known)

    def as_dict(self) -> Dict:
        """配置的字典形式（诊断/落盘）。"""
        return asdict(self)


def config_from_env(base: Optional[LexicalConfig] = None) -> LexicalConfig:
    """``LINGSHU_NG_LEXICAL``（JSON 对象）覆盖默认配置；解析失败忽略（退回默认）。"""
    base = base or LexicalConfig()
    raw = os.environ.get("LINGSHU_NG_LEXICAL", "").strip()
    if not raw:
        return base
    try:
        kw = json.loads(raw)
    except ValueError:
        return base
    return base.with_overrides(**kw) if isinstance(kw, dict) else base


# ---------------------------------------------------------------- L1 分词
def stem(w: str) -> str:
    """轻量英文词干（所有格/撇号、S-stemmer、-ing/-ed、-ation/-ness、-ly、尾 e；非 ASCII 词与 ≤3 字的词原样返回）。
    目标是让 run/running/runs、love/loved/loving、city/cities 归并，而不追求 Porter 的完整性。"""
    if "'" in w:
        w = w[:-2] if w.endswith("'s") else w.replace("'", "")
    if len(w) <= 3 or not w.isascii() or not w.isalpha():
        return w
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        w = w[:-1]
    for suf in ("ing", "ed"):
        if w.endswith(suf) and len(w) - len(suf) >= 3 and _VOWEL.search(w[:-len(suf)]):
            w = w[:-len(suf)]
            if w.endswith("i") and suf == "ed":
                w = w[:-1] + "y"
            elif len(w) >= 4 and w[-1] == w[-2] and w[-1] not in "lsz":
                w = w[:-1]
            break
    for suf in ("ation", "ness"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            w = w[:-len(suf)]
            break
    if w.endswith("ly") and len(w) > 5:
        w = w[:-2]
    if w.endswith("e") and len(w) >= 4:
        w = w[:-1]
    return w


# stab-r6：上限恢复 16384（4096 时 100k 召回 p95 ABBA 211→245 ms，8192 仍 237，见 CHANGELOG_rel-v1.22）
@lru_cache(maxsize=16384)
def _tokens(text: str, use_stem: bool, use_stop: bool) -> Tuple[str, ...]:
    t = unicodedata.normalize("NFKC", text).casefold().replace("\u2019", "'")
    out: List[str] = []
    for m in _run_re().finditer(t):
        cjk, lat = m.group(1), m.group(2)
        if cjk:
            if len(cjk) == 1:
                out.append(_intern(cjk))
            else:
                out.extend(_intern(cjk[i:i + 2]) for i in range(len(cjk) - 1))
        else:
            if use_stop and lat in STOPWORDS:
                continue
            w = stem(lat) if use_stem else lat
            if w and not (use_stop and w in STOPWORDS):
                out.append(_intern(w))
    # stab-r5：词元驻留（sys.intern）——缓存里上万条词元序列共用同一批词元字符串对象（值不变，只省内存）
    return tuple(out)


def tokens(text: Optional[str], cfg: Optional[LexicalConfig] = None) -> Tuple[str, ...]:
    """L1：正文/查询 → 词元序列（保序，含重复）。"""
    if not text:
        return ()
    c = cfg or _DEFAULT
    return _tokens(str(text), c.stem, c.stop)


_CJK_CH = re.compile(rf"[{_CJK}]")


def _is_cjk_token(t: str) -> bool:
    return bool(t) and _CJK_CH.match(t) is not None


def index_words(text: Optional[str]) -> List[str]:
    """L2：要写进派生倒排的拉丁词干词元（带 WORD_PREFIX；按默认分词规则，去重）。
    倒排只用于候选展开——打分时按查询所用配置重新分词，故改 stem/stop 配置不需要重建索引
    （关闭词干/停用词时候选可能略少，属近似，见 Scorer.rank 的说明）。"""
    return sorted({WORD_PREFIX + t for t in tokens(text, _DEFAULT) if not _is_cjk_token(t)})


def index_term(tok: str) -> str:
    """查询词元 → 倒排词元（中日韩二元组即原索引词元；拉丁词干加前缀）。"""
    return tok if _is_cjk_token(tok) else WORD_PREFIX + tok


def cjk_ratio(q: str) -> float:
    """中日韩字符 /（中日韩字符 + 其他字母）；无字母时为 1.0（按中文处理，走旧通路）。"""
    cj = len(_CJK_CH.findall(q))
    la = sum(1 for ch in q if ch.isalpha() and not _CJK_CH.match(ch))
    return cj / (cj + la) if cj + la else 1.0


def is_latin_query(q: str, cfg: LexicalConfig) -> bool:
    """路由：以拉丁文字为主（且有可用词元）的查询走新通路。"""
    return cfg.enabled and cjk_ratio(q) < cfg.route_cjk and bool(tokens(q, cfg))


def mixed_route(q: str, cfg: LexicalConfig, df_of, corpus_cjk_share) -> bool:
    """库感知路由（只在 is_latin_query 为假时调用）。df_of(词元集合) → {倒排词元: df}（只含 df>0）；
    corpus_cjk_share() → 库的中日韩词元份额（惰性求值：纯中文/纯英文查询不读）。"""
    if cfg.route_corpus < 0 or not cfg.enabled:
        return False
    toks = set(tokens(q, cfg))
    if not any(_is_cjk_token(t) for t in toks):
        return False
    la = {WORD_PREFIX + t for t in toks if not _is_cjk_token(t) and not t.isdigit()}
    if not la:
        return False
    if corpus_cjk_share() > cfg.route_corpus:
        return False
    return bool(df_of(la))


def query_terms(q: str, cfg: LexicalConfig) -> Tuple[List[str], Dict[str, int]]:
    """(查询词元序列, 词元 → 查询内频次)。"""
    seq = list(tokens(q, cfg))
    qtf: Dict[str, int] = {}
    for t in seq:
        qtf[t] = qtf.get(t, 0) + 1
    return seq, qtf


_DEFAULT = LexicalConfig()


# ---------------------------------------------------------------- L3 打分
class Scorer:
    """单次查询的打分器：持有 idf、avgdl 与查询结构，对给定正文给出原始分（未归一）。"""

    def __init__(self, q: str, cfg: LexicalConfig, df: Dict[str, int], n_docs: float, avgdl: float,
                 extra: Optional[Dict[str, float]] = None) -> None:
        self.cfg = cfg
        self.seq, qtf = query_terms(q, cfg)
        self.qtf: Dict[str, float] = {t: float(v) for t, v in qtf.items()}
        for t, w in (extra or {}).items():          # 伪相关反馈扩展词（权重 < 1，不参与 SDM 词对）
            if t not in self.qtf:
                self.qtf[t] = w
        self.n = n = max(1.0, float(n_docs))
        self.idf: Dict[str, float] = {}
        for t in self.qtf:
            d = df.get(index_term(t), 0)
            if d > 0:
                self.idf[t] = math.log(1.0 + (n - d + 0.5) / (d + 0.5))
        # SDM：相邻查询词对（两端都在库里出现过）
        self.pairs: List[Tuple[str, str, float]] = []
        seen = set()
        for a, b in zip(self.seq, self.seq[1:]):
            if a in self.idf and b in self.idf and a != b and (a, b) not in seen:
                seen.add((a, b))
                self.pairs.append((a, b, 0.5 * (self.idf[a] + self.idf[b])))
        self.avgdl = max(1.0, float(avgdl))

    def _sat(self, tf: float, norm: float) -> float:
        k1 = self.cfg.k1
        return tf * (k1 + 1.0) / (tf + norm)

    def _positions(self, content: str) -> Tuple[Tuple[str, ...], Dict[str, List[int]], int]:
        """(词元序列, 查询词元 → 位置, 长度)。H1 开启且正文有说话人标签时：spk 1 = 标签词元放到远处的负位置
        （仍计词项、不与正文成对）、长度不计标签；spk 2 = 标签整体剥离。"""
        c = self.cfg
        pos: Dict[str, List[int]] = {}
        if c.spk:
            lab, rest = split_label(content)
            if lab:
                toks = tokens(rest, c)
                for i, t in enumerate(toks):
                    if t in self.idf:
                        pos.setdefault(t, []).append(i)
                if c.spk == 1:
                    for i, t in enumerate(tokens(lab, c)):
                        if t in self.idf:
                            pos.setdefault(t, []).append(_FAR - 1000 * i)
                return toks, pos, len(rest)
        toks = tokens(content, c)
        for i, t in enumerate(toks):
            if t in self.idf:
                pos.setdefault(t, []).append(i)
        return toks, pos, len(content)

    def score(self, content: str) -> float:
        """L3：BM25 + SDM（+ 段落项）原始分；无任何查询词元命中 ⇒ 0。"""
        c = self.cfg
        if not content or not self.idf:
            return 0.0
        toks, pos, dl = self._positions(content)
        if not pos:
            return 0.0
        norm = c.k1 * (1.0 - c.b + c.b * dl / self.avgdl)
        s_t = sum(self.qtf[t] * self.idf[t] * self._sat(len(p), norm) for t, p in pos.items())
        s_o = s_u = 0.0
        if self.pairs and (c.w_o or c.w_u):
            for a, b, idf in self.pairs:
                pa, pb = pos.get(a), pos.get(b)
                if not pa or not pb:
                    continue
                sb = set(pb)
                o = sum(1 for i in pa if i + 1 in sb)
                u = _window_count(pa, pb, c.window)
                if o:
                    s_o += idf * self._sat(o, norm)
                if u:
                    s_u += idf * self._sat(u, norm)
        s = c.w_t * s_t + c.w_o * s_o + c.w_u * s_u
        if c.passage > 0 and c.gamma > 0:
            s = (1.0 - c.gamma) * s + c.gamma * self._best_window(toks, pos)
        return s

    def _best_window(self, toks: Sequence[str], pos: Dict[str, List[int]]) -> float:
        """段落项：长度 P、步长 P/2 的词窗里 BM25 词项分的最大值（窗长固定 ⇒ 不做长度归一，norm = k1）。"""
        P = self.cfg.passage
        if len(toks) <= P:
            return self.cfg.w_t * sum(self.qtf[t] * self.idf[t] * self._sat(len(p), self.cfg.k1) for t, p in pos.items())
        best = 0.0
        step = max(1, P // 2)
        hits = sorted((i, t) for t, p in pos.items() for i in p)
        for start in range(0, len(toks) - P // 2, step):
            cnt: Dict[str, int] = {}
            for i, t in hits:
                if start <= i < start + P:
                    cnt[t] = cnt.get(t, 0) + 1
            if cnt:
                v = sum(self.qtf[t] * self.idf[t] * self._sat(f, self.cfg.k1) for t, f in cnt.items())
                best = max(best, v)
        return self.cfg.w_t * best


def prf_terms(scorer: "Scorer", docs: Sequence[str], df_of, cfg: LexicalConfig) -> Dict[str, float]:
    """伪相关反馈扩展词：docs 为首轮前若干名正文；df_of(词元集) → {倒排词元: df}。返回 {词元: 查询权重}。"""
    if not docs or cfg.prf_terms <= 0 or cfg.prf_weight <= 0:
        return {}
    acc: Dict[str, float] = {}
    for d in docs:
        toks = tokens(d, cfg)
        if not toks:
            continue
        cnt: Dict[str, int] = {}
        for t in toks:
            if t not in scorer.qtf:
                cnt[t] = cnt.get(t, 0) + 1
        for t, f in cnt.items():
            acc[t] = acc.get(t, 0.0) + f / len(toks)
    if not acc:
        return {}
    df = df_of({index_term(t) for t in acc})
    n = scorer.n
    sc = {t: v * math.log(1.0 + (n - df[index_term(t)] + 0.5) / (df[index_term(t)] + 0.5))
          for t, v in acc.items() if df.get(index_term(t), 0) > 1}
    top = sorted(sc.items(), key=lambda x: (-x[1], x[0]))[:cfg.prf_terms]
    if not top:
        return {}
    mx = top[0][1]
    return {t: cfg.prf_weight * v / mx for t, v in top if v > 0}


def _window_count(pa: Sequence[int], pb: Sequence[int], w: int) -> int:
    """无序窗口：a 的出现中，前后 w−1 个词元内有 b 的个数（双指针，O(|pa|+|pb|)）。"""
    j, n, cnt = 0, len(pb), 0
    for i in pa:
        while j < n and pb[j] < i - (w - 1):
            j += 1
        if j < n and pb[j] <= i + (w - 1):
            cnt += 1
    return cnt


def context_aggregate(raw: Dict[str, float], seq: Dict[str, Optional[int]], beta: float, span: int,
                      decay: float = 1.0, prev: float = 1.0, nxt: float = 1.0) -> Dict[str, float]:
    """上下文聚合：s'(n) = s(n) + β·max{ dir(m)·decay^(d−1)·s(m) : d = |rowid(m) − rowid(n)|, 0 < d ≤ span }
    （只在已打分集合内；dir = prev（m 先写入）或 nxt（m 后写入））。"""
    if beta <= 0 or not raw:
        return raw
    by_row = {seq[nid]: v for nid, v in raw.items() if seq.get(nid) is not None}
    out: Dict[str, float] = {}
    for nid, v in raw.items():
        k = seq.get(nid)
        best = 0.0
        if k is not None:
            for d in range(1, span + 1):
                w = decay ** (d - 1)
                best = max(best, prev * w * by_row.get(k - d, 0.0), nxt * w * by_row.get(k + d, 0.0))
        out[nid] = v + beta * best
    return out


def seed_diffusion(seeds: Dict[int, float], eligible: Iterable[int], span: int, decay: float, steps: int,
                   alpha: float) -> Dict[int, float]:
    """gen-v3 D1：写入序邻接图上的个性化 PageRank（只用 rowid，纯函数）。

    seeds：{rowid: 非负分}；eligible：可参与扩散的 rowid 全集（种子须在其中）。
    边：|Δrowid| = d ≤ span 的两节点之间权 decay^(d−1)，按出边权和行归一。
    迭代 a₀ = p（种子分归一到和为 1），a ← α·p + (1−α)·Mᵀa，共 steps 步；返回 {rowid: 激活}（只含 > 0）。"""
    tot = sum(v for v in seeds.values() if v > 0)
    if tot <= 0 or steps < 0:
        return {}
    el = set(eligible)
    p = {k: v / tot for k, v in seeds.items() if v > 0 and k in el}
    if not p:
        return {}

    def nbrs(k: int) -> List[Tuple[int, float]]:
        """k 的可参与邻居及边权。"""
        out = []
        for d in range(1, span + 1):
            w = decay ** (d - 1)
            for m in (k - d, k + d):
                if m in el:
                    out.append((m, w))
        return out

    cache: Dict[int, List[Tuple[int, float]]] = {}
    a = dict(p)
    for _ in range(steps):
        nxt: Dict[int, float] = {k: alpha * v for k, v in p.items()}
        for k, v in a.items():
            nb = cache.get(k)
            if nb is None:
                nb = cache[k] = nbrs(k)
            z = sum(w for _, w in nb)
            if z <= 0:
                nxt[k] = nxt.get(k, 0.0) + (1.0 - alpha) * v      # 孤立点：质量留在原处
                continue
            for m, w in nb:
                nxt[m] = nxt.get(m, 0.0) + (1.0 - alpha) * v * w / z
        a = nxt
    return {k: v for k, v in a.items() if v > 0}


def diffuse_fuse(raw0: Dict[str, float], agg: Dict[str, float], seqno: Dict[str, Optional[int]], fetch,
                 cfg: LexicalConfig) -> Dict[str, float]:
    """gen-v3 D1：BM25+SDM 原始分 raw0 前 dif_seeds 名为种子 → :func:`seed_diffusion` 作第二路，与主排序 agg 做加权 RRF。
    fetch(未打分 rowid 列表) → {rowid: 节点 id}（只含可检索节点）。返回 {id: 融合分}（未归一）。"""
    top = sorted(raw0, key=lambda n: (-raw0[n], n))[:max(1, cfg.dif_seeds)]
    seeds = {seqno[n]: raw0[n] for n in top if seqno.get(n) is not None}
    if not seeds:
        return agg
    reach = max(0, cfg.dif_steps) * max(0, cfg.dif_span)
    want = set()
    for k in seeds:
        want.update(range(k - reach, k + reach + 1))
    row2id = {v: n for n, v in seqno.items() if v is not None}
    row2id.update(fetch(sorted(want - set(row2id))))
    act = seed_diffusion(seeds, [k for k in want if k in row2id], cfg.dif_span, cfg.dif_decay, cfg.dif_steps, cfg.dif_alpha)
    prim = [n for n, v in sorted(agg.items(), key=lambda x: (-x[1], x[0])) if v > 0]
    sec = [row2id[k] for k, _ in sorted(act.items(), key=lambda x: (-x[1], x[0]))]
    return rrf_fuse(prim, sec, cfg.dif_w, cfg.rrf_k)


def rrf_fuse(primary: Sequence[str], second: Sequence[str], w: float, k: float) -> Dict[str, float]:
    """加权 RRF：f(n) = 1/(k + r₁(n)) + w/(k + r₂(n))（名次从 1 起，不在某一路则该项为 0）。"""
    f: Dict[str, float] = {}
    for r, n in enumerate(primary, 1):
        f[n] = f.get(n, 0.0) + 1.0 / (k + r)
    if w > 0:
        for r, n in enumerate(second, 1):
            f[n] = f.get(n, 0.0) + w / (k + r)
    return f


def cluster_diversify(scores: Dict[str, float], seq: Dict[str, Optional[int]], win: int, pen: float,
                      top: int) -> Dict[str, float]:
    """gen-v3 D2：写入序簇多样化。按分数降序（同分按 id）贪心：第 i 个节点的分乘 pen^c，c = 此前已处理节点中
    写入序距离 ≤ win 的个数；处理后按新分重排。只动前 top 名（其余原样）；win ≤ 0 或 pen ≥ 1 原样返回。
    贪心是单遍的（被降分的节点不再与后来者重新比较），故结果与输入顺序无关、确定。"""
    if win <= 0 or pen >= 1.0 or not scores:
        return scores
    order = sorted(scores, key=lambda n: (-scores[n], n))
    head, out = order[:max(0, top)], dict(scores)
    picked: List[int] = []
    for n in head:
        k = seq.get(n)
        if k is None:
            continue
        c = sum(1 for m in picked if abs(m - k) <= win)
        if c:
            out[n] = scores[n] * pen ** c
        picked.append(k)
    return out
