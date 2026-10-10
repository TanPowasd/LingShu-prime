# -*- coding: utf-8 -*-
"""lingshu_ng.embed · 可选的本地句向量提供者（不属于记忆引擎核心；核心零外部依赖，见 tests_ng/test_quality.py）

``OnnxEmbedder(model_dir)``：BGE 系中文句向量（如 bge-small-zh-v1.5 / bge-base-zh-v1.5 的 ONNX 导出，
``model_quantized.onnx`` + ``tokenizer.json``），CPU onnxruntime 推理，CLS 池化 + L2 归一；
默认逐条编码（batch=1）：int8 动态量化模型的激活量化尺度按整批计算，批组成不同（后台线程取批随时序变化）
会让同一文本得到不同向量、召回不可复现（iter4 实测两次 HMB 运行 174/184 题前 10 名不同）；逐条编码与批组成无关。
实现 :mod:`lingshu_ng.semindex` 的「自带索引」提供者接口 ``add(ids, texts)`` / ``search(query, limit)``，
也提供旧接口约定的 ``encode(text)``。依赖 numpy、onnxruntime、tokenizers（缺任何一个时构造即抛 ImportError）。

``from_env()``：读环境变量 ``LINGSHU_NG_EMBED_MODEL``（模型目录）构造；未设置返回 None。
``LINGSHU_NG_SENT_INDEX=1/0``：句级证据向量开关（默认关；只在有交叉编码重排时参与融合）。
"""
from __future__ import annotations

import os
import re
from collections import OrderedDict
from typing import List, Optional, Sequence, Tuple

__all__ = ["OnnxEmbedder", "from_env", "split_sentences"]

_SENT_END = re.compile(r"(?<=[。！？!?；…\n])")


def split_sentences(text: str, min_len: int = 24) -> List[str]:
    """句级证据单元：按中文句末标点/换行切句，短于 min_len 的并入后一句（末尾残句并回前一句）。纯标准库。"""
    parts = [p for p in _SENT_END.split(text or "") if p.strip()]
    out: List[str] = []
    cur = ""
    for p in parts:
        if len(cur) < min_len:
            cur += p
        else:
            out.append(cur)
            cur = p
    if cur:
        if out and len(cur) < min_len:
            out[-1] += cur
        else:
            out.append(cur)
    return [o.strip() for o in out if o.strip()]


class OnnxEmbedder:
    """本地 ONNX 句向量 + 内存矩阵索引（float32，n×d；增量追加、按 id 覆盖）。"""

    def __init__(self, model_dir: str, fname: str = "model_quantized.onnx", maxlen: int = 512,
                 threads: int = 1, batch: int = 1, sentences: bool = False) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        path = os.path.join(model_dir, fname)
        if not os.path.exists(path) and os.path.exists(os.path.join(model_dir, "onnx", fname)):
            path = os.path.join(model_dir, "onnx", fname)   # HuggingFace 原样目录（onnx/ 子目录）
        self.sess = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        self.tok.enable_truncation(maxlen)
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.batch = batch
        self.ids: List[str] = []
        self.pos = {}
        self.mat = None
        self.model = os.path.basename(os.path.normpath(model_dir))
        #: 句级证据向量（可选）：每个节点的句子各编一条，查询时取「最贴题那一句」的余弦
        self.sentences = bool(sentences)
        self.smat = None
        self.sown: List[Optional[str]] = []
        self.srows = {}
        self._qcache: "OrderedDict[str, object]" = OrderedDict()

    def qvec(self, query: str):
        """查询向量（小 LRU：一次召回里 search / score_ids / sent_scores 共用同一次编码）。"""
        v = self._qcache.get(query)
        if v is None:
            v = self.encode_batch([query])[0]
            self._qcache[query] = v
            if len(self._qcache) > 64:
                self._qcache.popitem(last=False)
        else:
            self._qcache.move_to_end(query)
        return v

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
        if self.sentences:
            self._add_sentences(ids, texts)

    def _add_sentences(self, ids: Sequence[str], texts: Sequence[str]) -> None:
        np = self.np
        units, owners = [], []
        for nid, t in zip(ids, texts):
            for r in self.srows.pop(nid, []):          # 覆盖：旧句作废
                self.sown[r] = None
            for u in split_sentences(t):
                units.append(u)
                owners.append(nid)
        if not units:
            return
        v = self.encode_batch(units)
        base = len(self.sown)
        for k, nid in enumerate(owners):
            self.srows.setdefault(nid, []).append(base + k)
        self.sown.extend(owners)
        self.smat = v if self.smat is None else np.vstack([self.smat, v])

    def search(self, query: str, limit: int) -> List[Tuple[str, float]]:
        """余弦前 limit 名。"""
        np = self.np
        if self.mat is None or not len(self.ids):
            return []
        s = self.mat @ self.qvec(query)
        k = min(int(limit), len(self.ids))
        top = np.argpartition(-s, k - 1)[:k]
        top = top[np.lexsort((top, -s[top]))]
        return [(self.ids[i], float(s[i])) for i in top]


    def score_ids(self, query: str, ids: Sequence[str]) -> dict:
        """{id: 余弦}，只含已编码的 id。"""
        if self.mat is None:
            return {}
        q = self.qvec(query)
        return {nid: float(self.mat[self.pos[nid]] @ q) for nid in ids if nid in self.pos}


    def sent_scores(self, query: str, ids: Sequence[str]) -> dict:
        """{id: 该节点各句与查询余弦的最大值}；未开句级索引或无句时返回 {}。"""
        if self.smat is None:
            return {}
        q = self.qvec(query)
        out = {}
        for nid in ids:
            rows = self.srows.get(nid)
            if rows:
                out[nid] = float((self.smat[rows] @ q).max())
        return out


def from_env() -> Optional[OnnxEmbedder]:
    """``LINGSHU_NG_EMBED_MODEL`` 指向模型目录时构造提供者；未设置返回 None。"""
    d = os.environ.get("LINGSHU_NG_EMBED_MODEL", "").strip()
    if not d:
        return None
    # 句级证据向量默认关：生产实测（HMB 184 问）must_exclude −0.040、要点 +0.017，但 cid −0.004、原句 −0.011，
    # 属取舍而非净增益（见 REPORT_neural.md）；需要更少干扰材料时显式开
    sent = os.environ.get("LINGSHU_NG_SENT_INDEX", "0").strip().lower()
    return OnnxEmbedder(d, sentences=sent in ("1", "true", "yes", "on"))
