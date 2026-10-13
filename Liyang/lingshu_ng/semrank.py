# -*- coding: utf-8 -*-
"""可选的本地语义打分件（v7，zh-v1；PREREG_ZH 修订 5）。

- 交叉编码重排：BAAI/bge-reranker-base（MIT；https://huggingface.co/BAAI/bge-reranker-base），ONNX 推理（onnxruntime + tokenizers），CPU。
- 依赖全部可选：1.24 起本模块只含纯标准库部分（模型目录与件单例、缓存、排序 / 截断逻辑）；分词与 ONNX 前向、稠密向量件、判别头在插件
  ``lingshu-ng-embed``（:mod:`lingshu_ng.plugins`）。插件未装、onnxruntime / tokenizers 不可用、或模型目录缺文件 → :func:`get_scorer`
  返回 None，调用方逐位退回无模型路径（缺插件另打一次 WARNING，提示 ``pip install lingshu-ng-embed``）。
- 模型目录：环境变量 ``LINGSHU_NG_SEM``（目录；设为 ``off`` 即关闭）；未设时退到 ``~/.cache/lingshu_ng/models``（:func:`model_root`，
  进程内打一次 WARNING 并登记 diag ``sem_model_dir_default``，写明所用目录及其是否存在）；rel-v1.18 及以前缺省是作者开发机路径；
  其下 ``<LINGSHU_NG_SEM_MODEL，缺省 bge-reranker-base>/{tokenizer.json, onnx/<file>}``，文件名由 ``LINGSHU_NG_SEM_ONNX`` 选（缺省 model_quantized.onnx）。
- 分数缓存：``LINGSHU_NG_SEM_CACHE`` 目录（缺省 <模型目录>/_score_cache），键 sha1(模型文件名, 问句, 段落)，一行一个 JSON；
  缓存命中与重算逐位相同（同一 ONNX、单线程顺序批）——缓存只为省时。
"""
from __future__ import annotations

import logging
import dataclasses
import hashlib
import json
import os
import re
import threading
from typing import Dict, List, Optional, Sequence

from . import diag, plugins

_log = logging.getLogger(__name__)

#: 未设 ``LINGSHU_NG_SEM`` 时的模型根目录（v1.19 起；此前为作者开发机路径 /workspace/work/ls/_shared/models）。
#: 导入时按 XDG_CACHE_HOME / 当前用户主目录展开（v1.20 起认 XDG_CACHE_HOME）；运行期以 :func:`model_root` 为准（每次调用重新求值）。
DEFAULT_DIR = os.path.join((os.environ.get("XDG_CACHE_HOME", "").strip()
                            if os.path.isabs(os.environ.get("XDG_CACHE_HOME", "").strip() or ".")
                            else "") or os.path.join(os.path.expanduser("~"), ".cache"), "lingshu_ng", "models")
_LOCK = threading.Lock()


def cache_home() -> str:
    """用户缓存根目录：``$XDG_CACHE_HOME``（设了且为绝对路径时，按 XDG Base Directory 规范）否则 ``~/.cache``。
    调用时求值。"""
    x = os.environ.get("XDG_CACHE_HOME", "").strip()
    if x and os.path.isabs(x):
        return x
    return os.path.join(os.path.expanduser("~"), ".cache")


def default_model_dir() -> str:
    """缺省模型根目录 ``$XDG_CACHE_HOME/lingshu_ng/models``，未设 XDG_CACHE_HOME 时 ``~/.cache/lingshu_ng/models``
    （rel-v1.20 起支持 XDG_CACHE_HOME；调用时求值）。"""
    return os.path.join(cache_home(), "lingshu_ng", "models")


def model_root(warn: bool = True) -> str:
    """模型根目录：设了 ``LINGSHU_NG_SEM`` 就用它（``off`` / 空串 = 关闭，同旧版）；未设 → :func:`default_model_dir`。
    退到缺省目录时（``warn=True``）进程内打一次 WARNING 并登记 diag ``sem_model_dir_default``：写明目录、是否存在、怎样改。"""
    d = os.environ.get("LINGSHU_NG_SEM")
    if d is not None:      # 设了就用（空串同旧版 = 关闭）
        return d.strip()
    d = default_model_dir()
    if warn:
        if os.path.isdir(d):
            msg = f"未设 LINGSHU_NG_SEM → 模型目录用缺省 {d}（目录存在，按其中模型件启用语义件）；设 LINGSHU_NG_SEM=<目录> 或 off 可消除本警告"
        else:
            msg = (f"未设 LINGSHU_NG_SEM → 模型目录用缺省 {d}，但该目录不存在：语义件不可用，逐位退回无模型路径；"
                   "设 LINGSHU_NG_SEM=<模型目录> 启用，或 LINGSHU_NG_SEM=off 明确关闭并消除本警告")
        diag.warn_once("sem_model_dir_default", msg)
    return d


#: 稠密件的问句检索指令前缀（BGE 检索指令；1.22 为 ``DenseEmbedder.INST``，插件类同名属性仍可用）
DENSE_INST = "为这个句子生成表示以用于检索相关文章："

#: 1.24 迁到插件 lingshu-ng-embed 的类（``semrank.DenseEmbedder`` / ``semrank.DiscHead`` 旧名经 __getattr__ 委托）
_PLUGIN_CLASSES = {"DenseEmbedder": "dense_embedder", "DiscHead": "disc_head"}


def __getattr__(name):
    cap = _PLUGIN_CLASSES.get(name)
    if cap is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return plugins.require(cap, what=f"lingshu_ng.semrank.{name}")


_SCORERS: Dict[str, Optional["CrossScorer"]] = {}
#: 件不可用的原因（键同 _SCORERS / _EMBEDDERS）：关闭 / 缺模型文件 / 依赖加载失败（stab-r1：退回可见）
_REASONS: Dict[str, str] = {}
#: 链式请求（v7.1，PREREG_ZH 修订 5b）：问的是「某状态/版本从早到晚怎样变」——答案是整条链（链首、各次变更、现值），
#: 语义打分只看单段与问句的相关度，链中段常落到阈值以下被截掉。这类请求重排保留、截断豁免（取回条数同无截断）。
CHAIN_RE = re.compile(
    r"(经历|历经)(了|过)?(哪些|哪几次|几次|什么样?的?)?(变化|变更|变动|调整|改动|修改)"
    r"|演变|变迁|沿革|历程|来龙去脉"
    r"|(历次|每一次|每次|先后|依次|逐次)的?(变化|变更|变动|调整|改动|修改)"
    r"|从(最初|最开始|一开始|起初|当初)(到|至)(现在|如今|目前|最后|最终|今天)")


class CrossScorer:
    """交叉编码器打分件：score(问句, 段落列表) → logit 列表；带磁盘缓存。

    1.24 起：缓存（内存 + 磁盘 jsonl）、分批次序、取整在本类（纯标准库）；分词与 ONNX 前向由插件 ``lingshu-ng-embed`` 的
    ``cross_backend`` 后端（:class:`lingshu_ng.plugins.CrossScorerBackend`）完成。未装插件 ⇒ 构造抛 :class:`lingshu_ng.plugins.PluginMissingError`
    （:func:`get_scorer` 捕获后返回 None，逐位退回无模型路径）。``tok`` / ``sess`` / ``max_len`` / ``inputs`` 等后端属性照旧可读。"""

    def __init__(self, mdir: str, onnx_name: str, cache_dir: Optional[str], model: str = "bge-reranker-base") -> None:
        factory = plugins.require("cross_backend", what="交叉编码打分件 semrank.CrossScorer")
        self._be = factory(mdir, onnx_name, model)
        self.tag = self._be.tag
        self.cache_dir = cache_dir
        self.mem: Dict[str, float] = {}
        self._loaded = False

    def __getattr__(self, name):
        if name.startswith("__") or name == "_be":
            raise AttributeError(name)
        try:
            be = self.__dict__["_be"]
        except KeyError:
            raise AttributeError(name) from None
        return getattr(be, name)

    # ---------------------------------------------------------------- cache
    def _cfile(self) -> Optional[str]:
        if not self.cache_dir:
            return None
        return os.path.join(self.cache_dir, hashlib.sha1(self.tag.encode()).hexdigest()[:12] + ".jsonl")

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        f = self._cfile()
        if f and os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        k, v = json.loads(line)
                        self.mem[k] = float(v)
                    except (ValueError, TypeError):
                        continue

    def key(self, q: str, p: str) -> str:
        """缓存键 sha1(模型标签, 问句, 段落)。"""
        return hashlib.sha1(json.dumps([self.tag, q, p], ensure_ascii=False).encode("utf-8")).hexdigest()

    def encode_pairs(self, q: str, ps: Sequence[str]):
        """(问句, 段落) 对分词（委托后端；超长问句截断规则同 1.22）。"""
        return self._be.encode_pairs(q, ps)

    # ---------------------------------------------------------------- scoring
    def score(self, q: str, passages: Sequence[str], batch: int = 16) -> List[float]:
        """返回每段的相关度 logit（越大越相关）。"""
        with _LOCK:
            self._load()
            keys = [self.key(q, p) for p in passages]
            todo = sorted({i for i, k in enumerate(keys) if k not in self.mem}, key=lambda i: (len(passages[i]), i))  # 按长度分批，少补齐
            new = []
            for s in range(0, len(todo), batch):
                idx = todo[s:s + batch]
                out = self._be.logits(q, [passages[i] for i in idx])   # 插件后端的前向（未取整）
                for i, v in zip(idx, out):
                    v = round(float(v), 5)
                    self.mem[keys[i]] = v
                    new.append((keys[i], v))
            f = self._cfile()
            if new and f:
                try:
                    os.makedirs(os.path.dirname(f), exist_ok=True)
                    with open(f, "a", encoding="utf-8") as fh:
                        for k, v in new:
                            fh.write(json.dumps([k, v]) + "\n")
                except OSError:
                    pass
            return [self.mem[k] for k in keys]


_DISC: Dict[str, Optional[object]] = {}   # 值为插件的 DiscHead


def get_disc(sc):
    """判别头（进程内单例）：LINGSHU_NG_SEM_DISC（缺省 <模型目录>/disc_head.json）；头或特征图缺失 / 加载失败 → None。"""
    if sc is None or not isinstance(sc, CrossScorer):
        return None
    path = os.environ.get("LINGSHU_NG_SEM_DISC", os.path.join(model_root(),
                                                              os.environ.get("LINGSHU_NG_SEM_MODEL", "bge-reranker-base").strip(), "disc_head.json"))
    if path not in _DISC:
        try:
            make = plugins.provider("disc_head") if os.path.exists(path) else None
            if make is None and os.path.exists(path):
                plugins.warn_missing("disc_head", "判别头 ")
            _DISC[path] = make(sc, path) if make is not None else None
        except Exception:  # noqa: 头损坏 / 特征图缺失 → 退回 v7.1
            _log.warning("判别头加载失败（头损坏 / 特征图缺失）→ 退回 v7.1", exc_info=True)
            _DISC[path] = None
    return _DISC[path]


def get_scorer() -> Optional[CrossScorer]:
    """可用时返回打分件（进程内单例），否则 None（缺依赖 / 缺模型 / LINGSHU_NG_SEM=off）。"""
    return _scorer(os.environ.get("LINGSHU_NG_SEM_MODEL", "bge-reranker-base").strip(),
                   os.environ.get("LINGSHU_NG_SEM_ONNX", "model_quantized.onnx").strip())


def get_casc_scorer() -> Optional[CrossScorer]:
    """v13 级联复打件（PREREG_ZH 修订 11 C1）：BAAI/bge-reranker-v2-m3（MIT；onnx-community 量化 ONNX），
    ``LINGSHU_NG_SEM_CASC_MODEL`` / ``LINGSHU_NG_SEM_CASC_ONNX`` 可换；缺模型 / 缺依赖 → None（调用方不复打 = v11c）。"""
    return _scorer(os.environ.get("LINGSHU_NG_SEM_CASC_MODEL", "bge-reranker-v2-m3").strip(),
                   os.environ.get("LINGSHU_NG_SEM_CASC_ONNX", "model_quantized.onnx").strip())


def _scorer(model: str, name: str) -> Optional[CrossScorer]:
    d = model_root()
    k = f"{d}|{model}|{name}"
    if k in _SCORERS:
        return _SCORERS[k]
    sc: Optional[CrossScorer] = None
    if d and d.lower() not in ("off", "0", "none"):
        mdir = os.path.join(d, model)
        have = plugins.provider("cross_backend") is not None
        if not have:   # 1.24：模型部分在插件 lingshu-ng-embed；缺插件 ⇒ 一次 WARNING，逐位退回无模型路径
            plugins.warn_missing("cross_backend", "中文语义打分件（交叉编码 / 稠密 / 判别头）")
        if os.path.exists(os.path.join(mdir, "tokenizer.json")) and os.path.exists(os.path.join(mdir, "onnx", name)):
            if not have:
                _REASONS[k] = plugins.hint("cross_backend")
            else:
                try:
                    cache = os.environ.get("LINGSHU_NG_SEM_CACHE", os.path.join(d, "_score_cache"))
                    sc = CrossScorer(mdir, name, cache or None, model)
                except Exception as e:  # 可选依赖件（onnxruntime 原生库 / 模型文件）的失败类型不可枚举：记原因，退回无模型路径
                    _log.debug("交叉编码打分件构造失败 → 退回无模型路径（原因见 semrank.unavailable_reason）", exc_info=True)
                    sc = None
                    _REASONS[k] = f"加载失败 {type(e).__name__}: {e}"
        else:
            _REASONS[k] = (f"模型文件缺失（{mdir}/tokenizer.json 或 onnx/{name}）；把模型放到该处，"
                            "或设 LINGSHU_NG_SEM=<含该模型的根目录>，不用语义件可设 LINGSHU_NG_SEM=off")
    else:
        _REASONS[k] = "已关闭（LINGSHU_NG_SEM=off）"
    _SCORERS[k] = sc
    return sc


def v4_fallback(cfg):
    """sem_v4fb 退回（lingshu_ng.assoc 调用）：返回 tp_head、sem_n 置 0 的配置（= 逐位 v4）；
    进程内只打一次 WARNING，并登记进 diag.fallbacks()。"""
    warn_v4fb()
    return dataclasses.replace(cfg, tp_head=0, sem_n=0)


def warn_v4fb() -> None:
    """登记 sem_v4fb 退回：进程内只打一次 WARNING。"""
    diag.warn_once("sem_v4fb", "交叉编码打分件不可用（" + str(unavailable_reason("scorer"))
                   + "）→ 中文长请求关闭 TP 与语义重排，逐位退回 v4 词面档")


def unavailable_reason(kind: str = "scorer") -> Optional[str]:
    """``kind`` ∈ {scorer, casc, dense}：对应件当前不可用的原因；可用或尚未探测 → None。"""
    d = model_root()
    if kind == "dense":
        model = os.environ.get("LINGSHU_NG_DENSE_MODEL", "bge-small-zh-v1.5").strip()
        name = os.environ.get("LINGSHU_NG_DENSE_ONNX", "model.onnx").strip()
        off = os.environ.get("LINGSHU_NG_DENSE", "").strip().lower() in ("off", "0", "none")
        return _REASONS.get(f"{d}|{model}|{name}|{off}")
    if kind == "casc":
        model = os.environ.get("LINGSHU_NG_SEM_CASC_MODEL", "bge-reranker-v2-m3").strip()
        name = os.environ.get("LINGSHU_NG_SEM_CASC_ONNX", "model_quantized.onnx").strip()
    else:
        model = os.environ.get("LINGSHU_NG_SEM_MODEL", "bge-reranker-base").strip()
        name = os.environ.get("LINGSHU_NG_SEM_ONNX", "model_quantized.onnx").strip()
    return _REASONS.get(f"{d}|{model}|{name}")


_EMBEDDERS: Dict[str, Optional[object]] = {}   # 值为插件的 DenseEmbedder


def get_embedder():
    """稠密件可用时返回（进程内单例），否则 None（缺依赖 / 缺模型 / LINGSHU_NG_SEM 或 LINGSHU_NG_DENSE = off）→ 调用方不补稠密候选（= v7.1）。"""
    d = model_root()
    model = os.environ.get("LINGSHU_NG_DENSE_MODEL", "bge-small-zh-v1.5").strip()
    name = os.environ.get("LINGSHU_NG_DENSE_ONNX", "model.onnx").strip()
    off = os.environ.get("LINGSHU_NG_DENSE", "").strip().lower() in ("off", "0", "none")
    k = f"{d}|{model}|{name}|{off}"
    if k in _EMBEDDERS:
        return _EMBEDDERS[k]
    em = None
    if not off and d and d.lower() not in ("off", "0", "none"):
        mdir = os.path.join(d, model)
        make = plugins.provider("dense_embedder")
        if make is None:   # 1.24：稠密件在插件 lingshu-ng-embed
            plugins.warn_missing("dense_embedder", "中文语义打分件（交叉编码 / 稠密 / 判别头）")
        if os.path.exists(os.path.join(mdir, "tokenizer.json")) and os.path.exists(os.path.join(mdir, "onnx", name)):
            if make is None:
                _REASONS[k] = plugins.hint("dense_embedder")
            else:
                try:
                    em = make(mdir, name, os.environ.get("LINGSHU_NG_SEM_CACHE", os.path.join(d, "_score_cache")) or None, model)
                except Exception as e:  # 同 _scorer：可选依赖件失败类型不可枚举；记原因，调用方不补稠密候选（= v7.1）
                    _log.debug("稠密件构造失败 → 不补稠密候选 = v7.1（原因见 semrank.unavailable_reason）", exc_info=True)
                    em = None
                    _REASONS[k] = f"加载失败 {type(e).__name__}: {e}"
        else:
            _REASONS[k] = (f"模型文件缺失（{mdir}/tokenizer.json 或 onnx/{name}）；把模型放到该处，"
                            "或设 LINGSHU_NG_SEM=<含该模型的根目录>，不用语义件可设 LINGSHU_NG_SEM=off")
    else:
        _REASONS[k] = "已关闭（LINGSHU_NG_SEM 或 LINGSHU_NG_DENSE = off）"
    _EMBEDDERS[k] = em
    return em


def prefetch_dense(assoc, cfg) -> int:
    """v13 纯延迟修复（PREREG_ZH 修订 11.1）：把全库可检索块的稠密向量预先算进缓存（与 :func:`dense_candidates` 首次触发时
    同一 SQL、同一过滤、同一排序、同一批次 → 向量逐位相同、名次不变），使首个触发补入的查询不再现编全库。
    件不可用 / 补入关 / 库超 sem_dense_max → 0（不做事）。返回预算的块数。"""
    em = get_embedder()
    if em is None or getattr(cfg, "sem_dense", 0) <= 0 or get_scorer() is None:
        return 0
    rows = assoc.store.db.all("SELECT n.id, n.content FROM node_index i JOIN nodes n ON n.id = i.node_id WHERE i.grams > 0")
    if not rows or len(rows) > cfg.sem_dense_max:
        return 0
    ok = assoc.retrievable([r[0] for r in rows])
    rows = sorted({(nid, c or "") for nid, c in rows if nid in ok})
    if rows:
        em.encode([c for _, c in rows])
    return len(rows)


def dense_candidates(assoc, q: str, ctx, cfg, exclude_ids) -> Dict[str, tuple]:
    """全库可检索块按稠密余弦取前 sem_dense 个（不在 exclude_ids 中者），返回 {id: (余弦, 正文)}；
    件不可用或库超过 sem_dense_max 块 → {}。"""
    em = get_embedder()
    if em is None or cfg.sem_dense <= 0:
        if em is None and cfg.sem_dense > 0:
            diag.warn_once("sem_dense", "稠密件不可用（" + str(unavailable_reason("dense")) + "）→ 中文长请求不做稠密补入，逐位退回 v7.1 档")
        return {}
    rows = assoc.store.db.all("SELECT n.id, n.content FROM node_index i JOIN nodes n ON n.id = i.node_id WHERE i.grams > 0")
    if not rows or len(rows) > cfg.sem_dense_max:
        return {}
    ok = assoc.retrievable([r[0] for r in rows]) - ctx.exclude
    rows = sorted({(nid, c or "") for nid, c in rows if nid in ok})
    if not rows:
        return {}
    M = em.encode([c for _, c in rows])
    qv = em.encode([DENSE_INST + q])[0]
    cos = M @ qv            # 件返回的数组对象自带运算（插件为 numpy float32）；核心不导入 numpy，表达式与 1.22 相同
    order = sorted(range(len(rows)), key=lambda i: (-float(cos[i]), rows[i][0]))
    out: Dict[str, tuple] = {}
    for i in order:
        if len(out) >= cfg.sem_dense:
            break
        if rows[i][0] not in exclude_ids:
            out[rows[i][0]] = (float(cos[i]), rows[i][1])
    return out


def semantic(assoc, q: str, order: List[str], ctx, cfg, short: bool = False) -> List[str]:
    """SR（v7）入口（由 lingshu_ng.assoc 调用）：取正文后，长请求 → :func:`rerank`，短请求 → :func:`short_cut`。
    打分件不可用（缺依赖 / 缺模型 / LINGSHU_NG_SEM=off）→ 原样返回（逐位退回无模型路径）。"""
    sc = get_scorer()
    if sc is None or not order:
        return order
    head = order if short else order[:cfg.sem_n]
    text = {c: ctx.rows[c][0] for c in head if c in ctx.rows}
    miss = [c for c in head if c not in text]
    for i in range(0, len(miss), 500):
        part = miss[i:i + 500]
        for nid, c in assoc.store.db.all(f"SELECT id, content FROM nodes WHERE id IN ({','.join('?' * len(part))})", part):
            text[nid] = c or ""
    if short:
        return short_cut(sc, q, order, text, cfg.sem_short_tau, cfg.sem_short_min)
    if getattr(cfg, "sem_dense", 0) > 0 and not chain_intent(q) and getattr(cfg, "sem_dense_m", 0) > 0:
        # v10（PREREG_ZH 修订 8b）：自适应稠密补入——词面头部 logit ≥ τ 者少于 sem_dense_m 条时才补（词面召回不足才走语义）
        def _lazy():
            ex = dense_candidates(assoc, q, ctx, cfg, set(head))
            for c, (_, t) in ex.items():
                text[c] = t
            return list(ex)
        return rerank(sc, q, order, text, cfg, lazy_extra=_lazy)
    if getattr(cfg, "sem_dense", 0) > 0 and not chain_intent(q):
        extra = dense_candidates(assoc, q, ctx, cfg, set(head))
        if extra:
            for c, (_, t) in extra.items():
                text[c] = t
            return rerank(sc, q, order, text, cfg, extra=list(extra))
    return rerank(sc, q, order, text, cfg)


def dense_z(q: str, passages: Sequence[str]):
    """问句与各段的稠密余弦（bge-small-zh-v1.5，同 dense_candidates 的件与查询指令），题内标准化为 z 分；件不可用 → None。"""
    em = get_embedder()
    if em is None or not passages:
        return None
    cos = em.encode(list(passages)) @ em.encode([DENSE_INST + q])[0]   # 件返回数组的运算（同 1.22，核心不导入 numpy）
    return [float(x) for x in (cos - cos.mean()) / (cos.std() + 1e-6)]


def chain_intent(q: str) -> bool:
    """问句是否在要一条状态/版本链（历次变更、从最初到现在、演变/沿革等；纯词面，零模型）。"""
    return bool(q) and CHAIN_RE.search(q) is not None


def rerank(sc, q: str, order: List[str], text: Dict[str, str], cfg, extra: Sequence[str] = (), lazy_extra=None) -> List[str]:
    """长请求：前 sem_n 名按 logit − sem_lam·原名次重排；logit < sem_tau 或 < 本题最高 − sem_rel 者不返回（至少留 sem_min 条），
    sem_n 名之后也不再返回（自适应截断：上下文不必填满预算）。sem_tail = 1，或 sem_chain = 1 且问句是链式请求
    （:func:`chain_intent`）时只重排不截断。
    依据（r1dev）：词面特征分不开「证据段」与「相关但不满足需求」段（逐题 AUC ≈ .5），交叉编码器能部分分开（≈ .6）。"""
    head = [c for c in order[:cfg.sem_n] if c in text]
    hs = set(head)
    head += [c for c in extra if c not in hs and c in text]   # v8：稠密补入的候选（排在词面头部之后，同打分、同阈值）
    filled, dense = False, set()   # v11（修订 9）：自适应补入是否被触发 / 补入段
    if not head and lazy_extra is not None:   # 词面头部为空：直接取稠密候选
        head = [c for c in lazy_extra() if c in text]; lazy_extra = None; filled, dense = True, set(head)
    if not head:
        return order
    lg = dict(zip(head, sc.score(q, [text[c] for c in head])))
    if lazy_extra is not None and sum(v >= cfg.sem_tau for v in lg.values()) < cfg.sem_dense_m:
        hs = set(head); ex = [c for c in lazy_extra() if c not in hs and c in text]; filled = True
        if ex:
            lg.update(zip(ex, sc.score(q, [text[c] for c in ex]))); head += ex; dense = set(ex)
    pos = {c: k for k, c in enumerate(head)}
    if os.environ.get("LINGSHU_NG_SEM_DUMP"):   # 离线原型用（bench_zh/v9）：问句、头部正文、logit（含 α·D 之前）
        with open(os.environ["LINGSHU_NG_SEM_DUMP"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"q": q, "t": [text[c] for c in head], "lg": [lg[c] for c in head], "chain": chain_intent(q)}, ensure_ascii=False) + "\n")
    al = getattr(cfg, "sem_disc", 0.0)
    dh = get_disc(sc) if al and not chain_intent(q) else None
    if dh is not None:   # v9：排序 / 截断分 = logit + α·D（PREREG_ZH 修订 7）；链式请求、头缺失 → v7.1
        lg = {c: lg[c] + al * d for c, d in zip(head, dh.score(q, [text[c] for c in head]))}
    be = getattr(cfg, "sem_ans", 0.0)
    if be and not chain_intent(q):   # v9：+ β·答案类型相容分（anstype，修订 7b；零模型；权重缺失 → 0 = v7.1）
        from . import anstype       # stab-r5：懒加载（β = 0 的交付缺省从不载入）
        lg = {c: lg[c] + be * a for c, a in zip(head, anstype.score(q, [text[c] for c in head]))}
    v = {c: lg[c] - cfg.sem_lam * pos[c] for c in head}
    fw = getattr(cfg, "sem_fuse", 0.0)
    if fw and not chain_intent(q):   # v10：排序分 + w·稠密余弦题内 z 分（学 BGE-M3 稠密+稀疏+重排加权融合，自研）；截断仍只看 logit；稠密件缺失 → v7.1
        z = dense_z(q, [text[c] for c in head])
        if z is not None:
            v = {c: v[c] + fw * zz for c, zz in zip(head, z)}
    ranked = sorted(head, key=lambda c: (-v[c], pos[c]))
    if cfg.sem_tail or (getattr(cfg, "sem_chain", 0) and chain_intent(q)):
        hs = set(head)
        return ranked + [c for c in order[cfg.sem_n:] if c not in hs]
    top = max(lg.values())
    td = getattr(cfg, "sem_dense_tau", -99.0)
    keep = [c for c in ranked if lg[c] >= cfg.sem_tau and lg[c] >= top - cfg.sem_rel and (c not in dense or lg[c] >= td)]
    if len(keep) < cfg.sem_min:
        keep = ranked[:cfg.sem_min]
    k = getattr(cfg, "sem_dense_cap", 0)
    if filled and k > 0:   # v11：补入被触发时取段 ≤ k·sem_min（控「补入大量相关但不满足段」）
        keep = keep[:k * cfg.sem_min]
    kc = getattr(cfg, "sem_casc", 0)
    if kc > 0 and len(keep) > 1:   # v13（修订 11 C1）：截断后前 kc 段由更强的交叉编码器复打、只在这 kc 段内重排（取段集合不变）
        s2 = get_casc_scorer()
        if s2 is None:
            diag.warn_once("sem_casc", "复打件不可用（" + str(unavailable_reason("casc")) + "）→ 不复打，逐位退回 v11c 档")
        if s2 is not None:
            hk = keep[:kc]
            l2 = s2.score(q, [text[c] for c in hk])
            keep = [hk[i] for i in sorted(range(len(hk)), key=lambda i: (-l2[i], i))] + keep[kc:]
    return keep


def short_cut(sc, q: str, order: List[str], text: Dict[str, str], tau: float, mn: int) -> List[str]:
    """短请求：原序不动，logit < tau 的去掉（前 mn 名总保留）。"""
    lg = sc.score(q, [text.get(c, "") for c in order])
    keep = [c for c, v in zip(order, lg) if v >= tau]
    if len(keep) < mn:
        ks = set(keep)
        keep = [c for k, c in enumerate(order) if c in ks or k < mn]
    return keep
