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

import hashlib
import importlib
import json
import os
import re
import threading
from typing import Dict, List, Optional, Sequence

DEFAULT_DIR = "/workspace/work/ls/_shared/models"
_LOCK = threading.Lock()
_SCORERS: Dict[str, Optional["CrossScorer"]] = {}
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


def get_scorer() -> Optional[CrossScorer]:
    """可用时返回打分件（进程内单例），否则 None（缺依赖 / 缺模型 / LINGSHU_NG_SEM=off）。"""
    d = os.environ.get("LINGSHU_NG_SEM", DEFAULT_DIR).strip()
    name = os.environ.get("LINGSHU_NG_SEM_ONNX", "model_quantized.onnx").strip()
    model = os.environ.get("LINGSHU_NG_SEM_MODEL", "bge-reranker-base").strip()
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
            except Exception:  # noqa: 依赖缺失或模型损坏 → 退回无模型路径
                sc = None
    _SCORERS[k] = sc
    return sc


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
    return rerank(sc, q, order, text, cfg)


def chain_intent(q: str) -> bool:
    """问句是否在要一条状态/版本链（历次变更、从最初到现在、演变/沿革等；纯词面，零模型）。"""
    return bool(q) and CHAIN_RE.search(q) is not None


def rerank(sc, q: str, order: List[str], text: Dict[str, str], cfg) -> List[str]:
    """长请求：前 sem_n 名按 logit − sem_lam·原名次重排；logit < sem_tau 或 < 本题最高 − sem_rel 者不返回（至少留 sem_min 条），
    sem_n 名之后也不再返回（自适应截断：上下文不必填满预算）。sem_tail = 1，或 sem_chain = 1 且问句是链式请求
    （:func:`chain_intent`）时只重排不截断。
    依据（r1dev）：词面特征分不开「证据段」与「相关但不满足需求」段（逐题 AUC ≈ .5），交叉编码器能部分分开（≈ .6）。"""
    head = [c for c in order[:cfg.sem_n] if c in text]
    if not head:
        return order
    lg = dict(zip(head, sc.score(q, [text[c] for c in head])))
    pos = {c: k for k, c in enumerate(head)}
    v = {c: lg[c] - cfg.sem_lam * pos[c] for c in head}
    ranked = sorted(head, key=lambda c: (-v[c], pos[c]))
    if cfg.sem_tail or (getattr(cfg, "sem_chain", 0) and chain_intent(q)):
        return ranked + order[cfg.sem_n:]
    top = max(lg.values())
    keep = [c for c in ranked if lg[c] >= cfg.sem_tau and lg[c] >= top - cfg.sem_rel]
    if len(keep) < cfg.sem_min:
        keep = ranked[:cfg.sem_min]
    return keep


def short_cut(sc, q: str, order: List[str], text: Dict[str, str], tau: float, mn: int) -> List[str]:
    """短请求：原序不动，logit < tau 的去掉（前 mn 名总保留）。"""
    lg = sc.score(q, [text.get(c, "") for c in order])
    keep = [c for c, v in zip(order, lg) if v >= tau]
    if len(keep) < mn:
        ks = set(keep)
        keep = [c for k, c in enumerate(order) if c in ks or k < mn]
    return keep
