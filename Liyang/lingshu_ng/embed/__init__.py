# -*- coding: utf-8 -*-
"""lingshu_ng.embed · 可选的本地句向量提供者（不属于记忆引擎核心；核心零外部依赖，见 tests_ng/test_quality.py）

``OnnxEmbedder(model_dir)``：BGE 系中文句向量（如 bge-small-zh-v1.5 / bge-base-zh-v1.5 的 ONNX 导出，
``model_quantized.onnx`` + ``tokenizer.json``），CPU onnxruntime 推理，CLS 池化 + L2 归一；
默认逐条编码（batch=1）：int8 动态量化模型的激活量化尺度按整批计算，批组成不同（后台线程取批随时序变化）
会让同一文本得到不同向量、召回不可复现（iter4 实测两次 HMB 运行 174/184 题前 10 名不同）；逐条编码与批组成无关。
实现 :mod:`lingshu_ng.semindex` 的「自带索引」提供者接口 ``add(ids, texts)`` / ``search(query, limit)``，
也提供旧接口约定的 ``encode(text)``。依赖 numpy、onnxruntime、tokenizers（缺任何一个时构造即抛 ImportError）。

``from_env()``：读环境变量 ``LINGSHU_NG_EMBED_MODEL``（模型目录）构造；未设置返回 None。
"""
from __future__ import annotations

import os
from typing import List, Optional, Sequence, Tuple

__all__ = ["OnnxEmbedder", "from_env"]


class OnnxEmbedder:
    """本地 ONNX 句向量 + 内存矩阵索引（float32，n×d；增量追加、按 id 覆盖）。"""

    def __init__(self, model_dir: str, fname: str = "model_quantized.onnx", maxlen: int = 512,
                 threads: int = 1, batch: int = 1) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(os.path.join(model_dir, fname), so, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        self.tok.enable_truncation(maxlen)
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.batch = batch
        self.ids: List[str] = []
        self.pos = {}
        self.mat = None
        self.model = os.path.basename(os.path.normpath(model_dir))

    def encode_batch(self, texts: Sequence[str]):
        """[n, d] float32，L2 归一（按长度排序分批，减少填充）。"""
        np = self.np
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = [None] * len(texts)
        for k in range(0, len(order), self.batch):
            idx = order[k:k + self.batch]
            enc = self.tok.encode_batch([texts[i] for i in idx])
            width = max(len(e.ids) for e in enc)
            ids = np.zeros((len(enc), width), np.int64)
            am = np.zeros_like(ids)
            for r, e in enumerate(enc):
                ids[r, :len(e.ids)] = e.ids
                am[r, :len(e.ids)] = 1
            feed = {"input_ids": ids, "attention_mask": am}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            h = self.sess.run(None, feed)[0][:, 0]
            h = h / np.maximum(np.linalg.norm(h, axis=1, keepdims=True), 1e-12)
            for r, i in enumerate(idx):
                out[i] = h[r]
        return np.vstack(out).astype(np.float32) if out else np.zeros((0, 1), np.float32)

    def encode(self, text: str) -> List[float]:
        """单条句向量（旧接口 provider.encode）。"""
        return self.encode_batch([text])[0].tolist()

    def add(self, ids: Sequence[str], texts: Sequence[str]) -> None:
        """编码并追加（已有 id 覆盖）。"""
        if not ids:
            return
        np = self.np
        v = self.encode_batch(list(texts))
        new = []
        for nid, row in zip(ids, v):
            if nid in self.pos:
                self.mat[self.pos[nid]] = row
            else:
                self.pos[nid] = len(self.ids) + len(new)
                new.append((nid, row))
        if new:
            block = np.vstack([r for _, r in new])
            self.mat = block if self.mat is None else np.vstack([self.mat, block])
            self.ids.extend(n for n, _ in new)

    def search(self, query: str, limit: int) -> List[Tuple[str, float]]:
        """余弦前 limit 名。"""
        np = self.np
        if self.mat is None or not len(self.ids):
            return []
        s = self.mat @ self.encode_batch([query])[0]
        k = min(int(limit), len(self.ids))
        top = np.argpartition(-s, k - 1)[:k]
        top = top[np.lexsort((top, -s[top]))]
        return [(self.ids[i], float(s[i])) for i in top]


def from_env() -> Optional[OnnxEmbedder]:
    """``LINGSHU_NG_EMBED_MODEL`` 指向模型目录时构造提供者；未设置返回 None。"""
    d = os.environ.get("LINGSHU_NG_EMBED_MODEL", "").strip()
    return OnnxEmbedder(d) if d else None
