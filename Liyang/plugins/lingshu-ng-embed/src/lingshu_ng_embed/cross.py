# -*- coding: utf-8 -*-
"""lingshu_ng_embed.cross · 本地 ONNX 交叉编码重排器（插件 lingshu-ng-embed；旧路径 ``lingshu_ng.embed.cross.OnnxCrossEncoder`` 委托到此）

自 lingshu-ng 1.24 起从核心 ``lingshu_ng/embed/cross.py`` 原样迁出（逻辑逐行不变）；``_key``、``from_env`` 留在核心。

``OnnxCrossEncoder(model_dir)``：BGE reranker 系 ONNX 导出（bge-reranker-base / bge-reranker-v2-m3 的
``onnx/model_quantized.onnx`` + ``tokenizer.json``），对 (查询, 原文) 成对打分，返回 logit（越大越相关）。
只在**读路径**使用：写入照旧零模型落库；重排分不进主库、可随时丢弃。

确定性：逐对推理（batch=1，与批组成无关，理由同 :mod:`lingshu_ng.embed` 的逐条编码）；
同一 (查询, 原文) 结果进 LRU 缓存（键为两者的 blake2b 摘要，原文改写即失效）。

实现 :mod:`lingshu_ng.neural` 的交叉编码提供者接口 ``score(query, texts) -> List[float]``。
``from_env()``：读 ``LINGSHU_NG_RERANK_MODEL``（模型目录）；未设置返回 None。
"""
from __future__ import annotations

import os
from collections import OrderedDict
from typing import List, Sequence

__all__ = ["OnnxCrossEncoder"]


from lingshu_ng.embed.cross import _key  # noqa: E402  纯标准库部分留在核心


class OnnxCrossEncoder:
    """本地 ONNX 交叉编码器（CPU onnxruntime）。"""

    def __init__(self, model_dir: str, fname: str = "model_quantized.onnx", maxlen: int = 512,
                 threads: int = 0, cache: int = 20000) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(os.path.join(model_dir, "onnx", fname)
                                         if os.path.exists(os.path.join(model_dir, "onnx", fname))
                                         else os.path.join(model_dir, fname), so, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        self.tok.enable_truncation(maxlen)
        self.tok.no_padding()
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.model = os.path.basename(os.path.normpath(model_dir))
        self._cache: "OrderedDict[bytes, float]" = OrderedDict()
        self._cap = int(cache)
        self.calls = 0

    def _one(self, q: str, t: str) -> float:
        np = self.np
        e = self.tok.encode(q, t)
        ids = np.asarray([e.ids], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": np.ones_like(ids)}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.asarray([e.type_ids], dtype=np.int64)
        self.calls += 1
        return float(self.sess.run(None, feed)[0].reshape(-1)[0])

    def score(self, query: str, texts: Sequence[str]) -> List[float]:
        """[(查询, 原文_i) 的相关 logit]，与 texts 同序。"""
        out: List[float] = []
        for t in texts:
            k = _key(query, t)
            v = self._cache.get(k)
            if v is None:
                v = self._one(query, t)
                self._cache[k] = v
                if len(self._cache) > self._cap:
                    self._cache.popitem(last=False)
            else:
                self._cache.move_to_end(k)
            out.append(v)
        return out
