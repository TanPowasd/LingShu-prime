# -*- coding: utf-8 -*-
"""可选的本地语义打分件（v7，zh-v1；PREREG_ZH 修订 5）。

- 交叉编码重排：BAAI/bge-reranker-base（MIT；https://huggingface.co/BAAI/bge-reranker-base），ONNX 推理（onnxruntime + tokenizers），CPU。
- 依赖全部可选：onnxruntime / tokenizers 未安装、或模型目录缺文件 → :func:`get_scorer` 返回 None，调用方逐位退回无模型路径。
- 模型目录：环境变量 ``LINGSHU_NG_SEM``（目录；设为 ``off`` 即关闭），缺省 ``/workspace/work/ls/_shared/models``；
  其下 ``<LINGSHU_NG_SEM_MODEL，缺省 bge-reranker-base>/{tokenizer.json, onnx/<file>}``，文件名由 ``LINGSHU_NG_SEM_ONNX`` 选（缺省 model_quantized.onnx）。
- 分数缓存：``LINGSHU_NG_SEM_CACHE`` 目录（缺省 <模型目录>/_score_cache），键 sha1(模型文件名, 问句, 段落)，一行一个 JSON；
  缓存命中与重算逐位相同（同一 ONNX、单线程顺序批）——缓存只为省时。
"""
from __future__ import annotations

import logging
import dataclasses
import hashlib
import importlib
import json
import os
import re
import threading
from typing import Dict, List, Optional, Sequence

from . import anstype, diag

_log = logging.getLogger(__name__)

DEFAULT_DIR = "/workspace/work/ls/_shared/models"
_LOCK = threading.Lock()
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
    """交叉编码器打分件（ONNX + tokenizers，CPU）：score(问句, 段落列表) → logit 列表；带磁盘缓存。"""

    def __init__(self, mdir: str, onnx_name: str, cache_dir: Optional[str], model: str = "bge-reranker-base") -> None:
        ort = importlib.import_module("onnxruntime")          # 可选依赖（不进 lingshu_ng 的硬依赖）
        Tokenizer = importlib.import_module("tokenizers").Tokenizer
        tok = Tokenizer.from_file(os.path.join(mdir, "tokenizer.json"))
        self.max_len = int(os.environ.get("LINGSHU_NG_SEM_MAXLEN", "320"))
        tok.enable_truncation(max_length=self.max_len, strategy="only_second")
        tok.enable_padding(pad_id=tok.token_to_id("<pad>") or 1, pad_token="<pad>")
        self.tok = tok
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(os.environ.get("LINGSHU_NG_SEM_THREADS", "2"))
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(os.path.join(mdir, "onnx", onnx_name), so, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.tag = f"{model}/{onnx_name}/{self.max_len}"
        self.cache_dir = cache_dir
        self.mem: Dict[str, float] = {}
        self._loaded = False

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

    # ---------------------------------------------------------------- scoring
    def score(self, q: str, passages: Sequence[str], batch: int = 16) -> List[float]:
        """返回每段的相关度 logit（越大越相关）。"""
        np = importlib.import_module("numpy")                # onnxruntime 的依赖
        with _LOCK:
            self._load()
            keys = [self.key(q, p) for p in passages]
            todo = sorted({i for i, k in enumerate(keys) if k not in self.mem}, key=lambda i: (len(passages[i]), i))  # 按长度分批，少补齐
            new = []
            for s in range(0, len(todo), batch):
                idx = todo[s:s + batch]
                enc = self.tok.encode_batch([(q, passages[i]) for i in idx])
                feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                        "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
                if "token_type_ids" in self.inputs:
                    feed["token_type_ids"] = np.zeros_like(feed["input_ids"])
                out = self.sess.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0].reshape(-1)
                for i, v in zip(idx, out.tolist()):
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


class DiscHead:
    """v9（PREREG_ZH 修订 7）：「是否满足需求」判别头 D——在交叉编码器同一模型的 CLS / tanh 隐状态上训练的 L2 逻辑回归或 1 隐层 MLP
    （T2Ranking 训练侧 4 级标注，y = 相关度 ≥ 2；训练脚本 bench_zh/v9/train_disc.py）。头文件 JSON 缺失 → None（调用方退回 v7.1）。
    思想来源：线性探针（Alain & Bengio 2016）、分级相关度（Xie et al. SIGIR'23 T2Ranking）。"""

    def __init__(self, sc: "CrossScorer", path: str) -> None:
        np = importlib.import_module("numpy")
        h = json.load(open(path, encoding="utf-8"))
        self.np, self.h, self.sc = np, h, sc
        self.mu, self.sd = np.array(h["mu"], np.float32), np.array(h["sd"], np.float32)
        self.W1 = np.array(h["W1"], np.float32) if h.get("W1") else None
        self.b1 = np.array(h["b1"], np.float32) if h.get("W1") else None
        self.w, self.b = np.array(h["w"], np.float32), float(h["b"])
        self.tag = sc.tag + "/disc/" + h["sha"]
        so = importlib.import_module("onnxruntime").SessionOptions()
        so.intra_op_num_threads = int(os.environ.get("LINGSHU_NG_SEM_THREADS", "2"))
        so.inter_op_num_threads = 1
        onnx_path = os.path.join(os.path.dirname(os.path.abspath(path)), h.get("onnx", "onnx/model_quantized_feat.onnx"))
        self.sess = importlib.import_module("onnxruntime").InferenceSession(onnx_path, so, providers=["CPUExecutionProvider"])
        self.cache = CrossScorer.__new__(CrossScorer)            # 复用缓存读写（键含头 sha）
        self.cache.tag, self.cache.cache_dir, self.cache.mem, self.cache._loaded = self.tag, sc.cache_dir, {}, False

    def _feat(self, outs):
        np = self.np
        parts = {"cls": outs[1], "tanh": outs[2], "logit": outs[0].reshape(-1, 1)}
        x = np.concatenate([parts[k] for k in self.h["feats"]], axis=1).astype(np.float32)
        x = (x - self.mu) / self.sd
        if self.W1 is not None:
            x = np.maximum(x @ self.W1 + self.b1, 0.0)
        return (x @ self.w + self.b).reshape(-1)

    def score(self, q: str, passages: Sequence[str], batch: int = 16) -> List[float]:
        """每段的 D logit（越大越像「满足需求」）；带磁盘缓存。"""
        np, c = self.np, self.cache
        with _LOCK:
            c._load()
            keys = [c.key(q, p) for p in passages]
            todo = sorted({i for i, k in enumerate(keys) if k not in c.mem}, key=lambda i: (len(passages[i]), i))
            new = []
            for s in range(0, len(todo), batch):
                idx = todo[s:s + batch]
                enc = self.sc.tok.encode_batch([(q, passages[i]) for i in idx])
                feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                        "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
                for i, v in zip(idx, self._feat(self.sess.run(None, feed)).tolist()):
                    c.mem[keys[i]] = round(float(v), 5)
                    new.append((keys[i], c.mem[keys[i]]))
            f = c._cfile()
            if new and f:
                try:
                    with open(f, "a", encoding="utf-8") as fh:
                        fh.writelines(json.dumps([k, v]) + "\n" for k, v in new)
                except OSError:
                    pass
            return [c.mem[k] for k in keys]


_DISC: Dict[str, Optional[DiscHead]] = {}


def get_disc(sc) -> Optional[DiscHead]:
    """判别头（进程内单例）：LINGSHU_NG_SEM_DISC（缺省 <模型目录>/disc_head.json）；头或特征图缺失 / 加载失败 → None。"""
    if sc is None or not isinstance(sc, CrossScorer):
        return None
    path = os.environ.get("LINGSHU_NG_SEM_DISC", os.path.join(os.environ.get("LINGSHU_NG_SEM", DEFAULT_DIR).strip(),
                                                              os.environ.get("LINGSHU_NG_SEM_MODEL", "bge-reranker-base").strip(), "disc_head.json"))
    if path not in _DISC:
        try:
            _DISC[path] = DiscHead(sc, path) if os.path.exists(path) else None
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
    d = os.environ.get("LINGSHU_NG_SEM", DEFAULT_DIR).strip()
    k = f"{d}|{model}|{name}"
    if k in _SCORERS:
        return _SCORERS[k]
    sc: Optional[CrossScorer] = None
    if d and d.lower() not in ("off", "0", "none"):
        mdir = os.path.join(d, model)
        if os.path.exists(os.path.join(mdir, "tokenizer.json")) and os.path.exists(os.path.join(mdir, "onnx", name)):
            try:
                cache = os.environ.get("LINGSHU_NG_SEM_CACHE", os.path.join(d, "_score_cache"))
                sc = CrossScorer(mdir, name, cache or None, model)
            except Exception as e:  # 可选依赖件（onnxruntime 原生库 / 模型文件）的失败类型不可枚举：记原因，退回无模型路径
                _log.debug("交叉编码打分件构造失败 → 退回无模型路径（原因见 semrank.unavailable_reason）", exc_info=True)
                sc = None
                _REASONS[k] = f"加载失败 {type(e).__name__}: {e}"
        else:
            _REASONS[k] = f"模型文件缺失（{mdir}/tokenizer.json 或 onnx/{name}）"
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
    d = os.environ.get("LINGSHU_NG_SEM", DEFAULT_DIR).strip()
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


class DenseEmbedder:
    """稠密向量件（v8，PREREG_ZH 修订 6）：BAAI/bge-small-zh-v1.5（MIT；Xenova ONNX @75c43b0），CLS 池化 + L2 归一，
    问句加 BGE 检索指令前缀。向量按 float16 存（内存与磁盘缓存同一取值 → 缓存命中与重算逐位相同）。
    思想来源：BGE-M3（Chen et al. 2024）稀疏 + 稠密混合召回——这里「稀疏」一路即本库原有词面 / 联想名单，稠密一路只补候选，
    由交叉编码器统一重排；实现为我方自研。"""

    INST = "为这个句子生成表示以用于检索相关文章："

    def __init__(self, mdir: str, onnx_name: str, cache_dir: Optional[str], model: str) -> None:
        ort = importlib.import_module("onnxruntime")
        Tokenizer = importlib.import_module("tokenizers").Tokenizer
        tok = Tokenizer.from_file(os.path.join(mdir, "tokenizer.json"))
        tok.enable_truncation(max_length=int(os.environ.get("LINGSHU_NG_DENSE_MAXLEN", "256")))
        tok.enable_padding(pad_id=0, pad_token="[PAD]")
        self.tok = tok
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(os.environ.get("LINGSHU_NG_SEM_THREADS", "2"))
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(os.path.join(mdir, "onnx", onnx_name), so, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.tag = f"{model}/{onnx_name}/dense"
        self.cache_dir = cache_dir
        self.mem: Dict[str, bytes] = {}
        self._loaded = False

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
                        self.mem[k] = bytes.fromhex(v)
                    except (ValueError, TypeError):
                        continue

    def encode(self, texts: Sequence[str], batch: int = 16):
        """返回 (len(texts), d) float32 矩阵（L2 归一后经 float16 取整）。"""
        np = importlib.import_module("numpy")
        with _LOCK:
            self._load()
            keys = [hashlib.sha1(json.dumps([self.tag, t], ensure_ascii=False).encode("utf-8")).hexdigest() for t in texts]
            todo = sorted({i for i, k in enumerate(keys) if k not in self.mem}, key=lambda i: (len(texts[i]), i))
            new = []
            for s in range(0, len(todo), batch):
                idx = todo[s:s + batch]
                enc = self.tok.encode_batch([texts[i] for i in idx])
                ids = np.array([e.ids for e in enc], dtype=np.int64)
                feed = {"input_ids": ids, "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
                        "token_type_ids": np.zeros_like(ids)}
                h = self.sess.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0][:, 0]
                h = (h / np.maximum(np.linalg.norm(h, axis=1, keepdims=True), 1e-12)).astype(np.float16)
                for i, row in zip(idx, h):
                    b = row.tobytes()
                    self.mem[keys[i]] = b
                    new.append((keys[i], b.hex()))
            f = self._cfile()
            if new and f:
                try:
                    os.makedirs(os.path.dirname(f), exist_ok=True)
                    with open(f, "a", encoding="utf-8") as fh:
                        for k, v in new:
                            fh.write(json.dumps([k, v]) + "\n")
                except OSError:
                    pass
            return np.stack([np.frombuffer(self.mem[k], dtype=np.float16) for k in keys]).astype(np.float32) if keys else np.zeros((0, 1), np.float32)


_EMBEDDERS: Dict[str, Optional[DenseEmbedder]] = {}


def get_embedder() -> Optional[DenseEmbedder]:
    """稠密件可用时返回（进程内单例），否则 None（缺依赖 / 缺模型 / LINGSHU_NG_SEM 或 LINGSHU_NG_DENSE = off）→ 调用方不补稠密候选（= v7.1）。"""
    d = os.environ.get("LINGSHU_NG_SEM", DEFAULT_DIR).strip()
    model = os.environ.get("LINGSHU_NG_DENSE_MODEL", "bge-small-zh-v1.5").strip()
    name = os.environ.get("LINGSHU_NG_DENSE_ONNX", "model.onnx").strip()
    off = os.environ.get("LINGSHU_NG_DENSE", "").strip().lower() in ("off", "0", "none")
    k = f"{d}|{model}|{name}|{off}"
    if k in _EMBEDDERS:
        return _EMBEDDERS[k]
    em: Optional[DenseEmbedder] = None
    if not off and d and d.lower() not in ("off", "0", "none"):
        mdir = os.path.join(d, model)
        if os.path.exists(os.path.join(mdir, "tokenizer.json")) and os.path.exists(os.path.join(mdir, "onnx", name)):
            try:
                em = DenseEmbedder(mdir, name, os.environ.get("LINGSHU_NG_SEM_CACHE", os.path.join(d, "_score_cache")) or None, model)
            except Exception as e:  # 同 _scorer：可选依赖件失败类型不可枚举；记原因，调用方不补稠密候选（= v7.1）
                _log.debug("稠密件构造失败 → 不补稠密候选 = v7.1（原因见 semrank.unavailable_reason）", exc_info=True)
                em = None
                _REASONS[k] = f"加载失败 {type(e).__name__}: {e}"
        else:
            _REASONS[k] = f"模型文件缺失（{mdir}/tokenizer.json 或 onnx/{name}）"
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
    np = importlib.import_module("numpy")
    rows = assoc.store.db.all("SELECT n.id, n.content FROM node_index i JOIN nodes n ON n.id = i.node_id WHERE i.grams > 0")
    if not rows or len(rows) > cfg.sem_dense_max:
        return {}
    ok = assoc.retrievable([r[0] for r in rows]) - ctx.exclude
    rows = sorted({(nid, c or "") for nid, c in rows if nid in ok})
    if not rows:
        return {}
    M = em.encode([c for _, c in rows])
    qv = em.encode([DenseEmbedder.INST + q])[0]
    cos = M @ qv
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
    np = importlib.import_module("numpy")
    cos = em.encode(list(passages)) @ em.encode([DenseEmbedder.INST + q])[0]
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
