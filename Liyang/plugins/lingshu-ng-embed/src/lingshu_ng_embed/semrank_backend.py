# -*- coding: utf-8 -*-
"""lingshu_ng_embed.semrank_backend · 中文语义打分件的模型部分（插件 lingshu-ng-embed）

自 lingshu-ng 1.24 起从核心 :mod:`lingshu_ng.semrank` 拆出：

- :class:`CrossBackend`：交叉编码器（BAAI/bge-reranker-base 等，ONNX + tokenizers）的分词与前向；缓存 / 分批 / 取整留在核心
  :class:`lingshu_ng.semrank.CrossScorer`；
- :class:`DenseEmbedder`：稠密向量件（BAAI/bge-small-zh-v1.5，float16 缓存）；``encode`` 返回 numpy 矩阵，核心
  ``dense_candidates`` / ``dense_z`` 对它做 ``@`` / ``mean`` / ``std``（表达式与 1.22 相同，核心不导入 numpy）；
- :class:`DiscHead`：v9 判别头。

代码与 1.22 逐行相同（只换了所在模块），读数逐位不变（见 CHANGELOG_rel-v1.24）。numpy / onnxruntime / tokenizers 均在构造或调用时
才导入：缺依赖 ⇒ 构造抛异常，核心记原因并逐位退回无模型档（与 1.22 相同）。
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from typing import Dict, List, Optional, Sequence

from lingshu_ng import diag
from lingshu_ng.semrank import _LOCK, DENSE_INST, CrossScorer

__all__ = ["CrossBackend", "DenseEmbedder", "DiscHead"]


class CrossBackend:
    """交叉编码器推理后端（ONNX + tokenizers，CPU）。核心 :class:`lingshu_ng.semrank.CrossScorer` 持有它：缓存（磁盘 jsonl + 内存）、
    分批次序与取整在核心，本类只做分词与前向（代码自 lingshu-ng 1.22 ``semrank.CrossScorer`` 原样拆出，逐位相同）。"""

    def __init__(self, mdir: str, onnx_name: str, model: str = "bge-reranker-base") -> None:
        ort = importlib.import_module("onnxruntime")          # 可选依赖（不进 lingshu_ng 的硬依赖）
        Tokenizer = importlib.import_module("tokenizers").Tokenizer
        tok = Tokenizer.from_file(os.path.join(mdir, "tokenizer.json"))
        self.max_len = int(os.environ.get("LINGSHU_NG_SEM_MAXLEN", "320"))
        tok.enable_truncation(max_length=self.max_len, strategy="only_second")
        tok.enable_padding(pad_id=tok.token_to_id("<pad>") or 1, pad_token="<pad>")
        self.tok = tok
        self._tok_file = os.path.join(mdir, "tokenizer.json")
        self._qtok = None
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(os.environ.get("LINGSHU_NG_SEM_THREADS", "2"))
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(os.path.join(mdir, "onnx", onnx_name), so, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.tag = f"{model}/{onnx_name}/{self.max_len}"

    def encode_pairs(self, q: str, ps: Sequence[str]):
        """(问句, 段落) 对分词（only_second：只截段落）。问句本身已超过 max_len 时 tokenizers 抛 Truncation error
        （rel-v1.19 及以前 limit > 15 的超长问句在 v7.1 档因此崩溃）⇒ 仅此时把问句截到前 max_len // 2 个 token 再分词；
        其余输入与旧版逐位相同。缓存键仍用原问句。"""
        try:
            return self.tok.encode_batch([(q, p) for p in ps])
        except Exception as e:  # tokenizers 只抛通用 Exception；非截断错误原样抛出
            if "runcat" not in str(e):
                raise
        diag.warn_once("sem_query_truncated", f"问句超过交叉编码器 max_len {self.max_len} 个 token：打分时只取问句前 "
                                              f"{max(1, self.max_len // 2)} 个 token（词面召回仍用全文）")
        if self._qtok is None:
            self._qtok = importlib.import_module("tokenizers").Tokenizer.from_file(self._tok_file)
        off = self._qtok.encode(q, add_special_tokens=False).offsets
        k = max(1, self.max_len // 2)
        qq = q[:off[k - 1][1]] if len(off) > k else q
        return self.tok.encode_batch([(qq, p) for p in ps])

    def logits(self, q: str, ps: Sequence[str]) -> List[float]:
        """一批 (问句, 段落) 的相关度 logit（未取整；核心按 round(float(v), 5) 入缓存）。"""
        np = importlib.import_module("numpy")                # onnxruntime 的依赖
        enc = self.encode_pairs(q, ps)
        feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(feed["input_ids"])
        return self.sess.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0].reshape(-1).tolist()


class DiscHead:
    """v9（PREREG_ZH 修订 7）：「是否满足需求」判别头 D——在交叉编码器同一模型的 CLS / tanh 隐状态上训练的 L2 逻辑回归或 1 隐层 MLP
    （T2Ranking 训练侧 4 级标注，y = 相关度 ≥ 2；训练脚本 bench_zh/v9/train_disc.py）。头文件 JSON 缺失 → None（调用方退回 v7.1）。
    思想来源：线性探针（Alain & Bengio 2016）、分级相关度（Xie et al. SIGIR'23 T2Ranking）。"""

    def __init__(self, sc, path: str) -> None:
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
                enc = self.sc.encode_pairs(q, [passages[i] for i in idx])
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


class DenseEmbedder:
    """稠密向量件（v8，PREREG_ZH 修订 6）：BAAI/bge-small-zh-v1.5（MIT；Xenova ONNX @75c43b0），CLS 池化 + L2 归一，
    问句加 BGE 检索指令前缀。向量按 float16 存（内存与磁盘缓存同一取值 → 缓存命中与重算逐位相同）。
    思想来源：BGE-M3（Chen et al. 2024）稀疏 + 稠密混合召回——这里「稀疏」一路即本库原有词面 / 联想名单，稠密一路只补候选，
    由交叉编码器统一重排；实现为我方自研。"""

    INST = DENSE_INST

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
