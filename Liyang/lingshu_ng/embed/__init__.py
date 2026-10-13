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

import logging
import os
import re
from collections import OrderedDict
from typing import List, Optional, Sequence, Tuple

_log = logging.getLogger(__name__)

__all__ = ["OnnxEmbedder", "from_env", "split_sentences"]

_BLAS = None  # (get, set) 或 False


def _blas_fns():
    """F3T（gen r10，纯时延）：numpy 自带 OpenBLAS 的线程数读写函数；找不到返回 False（照常多线程）。"""
    global _BLAS
    if _BLAS is not None:
        return _BLAS
    _BLAS = False
    if os.environ.get("LINGSHU_NG_BLAS1", "1").strip() == "0":
        return _BLAS
    try:
        import ctypes
        import glob
        import numpy as np
        base = os.path.dirname(np.__file__)
        for f in sorted(glob.glob(os.path.join(base, "..", "numpy.libs", "*openblas*")) +
                        glob.glob(os.path.join(base, ".libs", "*openblas*"))):
            lib = ctypes.CDLL(f)
            for g, st in (("scipy_openblas_get_num_threads64_", "scipy_openblas_set_num_threads64_"),
                          ("scipy_openblas_get_num_threads", "scipy_openblas_set_num_threads"),
                          ("openblas_get_num_threads64_", "openblas_set_num_threads64_"),
                          ("openblas_get_num_threads", "openblas_set_num_threads")):
                if hasattr(lib, g) and hasattr(lib, st):
                    _BLAS = (getattr(lib, g), getattr(lib, st))
                    return _BLAS
    except Exception:  # ctypes/平台差异不可枚举：找不到就不限线程，结果不变
        _log.debug("BLAS 线程控制符号查找失败（ctypes / 平台差异）→ 不限线程，结果不变", exc_info=True)
        _BLAS = False
    return _BLAS


class _Blas1:
    """MaxSim 的小矩阵乘在单线程 BLAS 下执行。OpenBLAS 多线程只按输出行列切分、不改每个元素的累加次序，
    故结果逐位相同（tests_ng/test_tokvec_pre.py 核对）；但机器繁忙时唤醒工作线程的等待可达数十毫秒（r10 实测 0.4–56 ms → 0.4 ms）。"""
    _n = None

    def __enter__(self):
        f = _blas_fns()
        if f:
            try:
                self._n = int(f[0]())
                if self._n != 1:
                    f[1](1)
            except Exception:
                _log.debug("BLAS 线程数读写失败 → 不限线程，结果不变", exc_info=True)
                self._n = None
        return self

    def __exit__(self, *a):
        f = _blas_fns()
        if f and self._n and self._n != 1:
            f[1](self._n)
        return False


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
        self.fname = fname
        #: 句级证据向量（可选）：每个节点的句子各编一条，查询时取「最贴题那一句」的余弦
        self.sentences = bool(sentences)
        self.smat = None
        self.sown: List[Optional[str]] = []
        self.srows = {}
        self._qcache: "OrderedDict[str, object]" = OrderedDict()
        #: F3L（gen r10）：写入时顺带保存逐词向量（同一次前向，逐位等于 token_vecs 现算），供 MaxSim 精排查表；
        #: 按字节预算 LRU（``LINGSHU_NG_EMBED_TOKVEC_MB``，缺省 256；0 = 关，退回查询时现算）
        self._tokc: "OrderedDict[str, object]" = OrderedDict()
        self._tokbytes = 0
        try:
            self.tok_budget = max(0, int(float(os.environ.get("LINGSHU_NG_EMBED_TOKVEC_MB", "256")) * 1048576))
        except ValueError:
            self.tok_budget = 256 * 1048576

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

    def _cache(self):
        """可选磁盘向量缓存（gen-v3 r7）：``LINGSHU_NG_EMBED_CACHE`` = 目录 ⇒ sqlite 表，键 = sha1(模型目录名, 文件名, 文本)。
        只在逐条编码（batch = 1）时启用：此时向量与批组成无关，命中与重算逐位相同；只省重复编码。"""
        if getattr(self, "_cdb", False) is not False:
            return self._cdb
        self._cdb = None
        d = os.environ.get("LINGSHU_NG_EMBED_CACHE", "").strip()
        if d and self.batch == 1:
            import sqlite3
            os.makedirs(d, exist_ok=True)
            c = sqlite3.connect(os.path.join(d, "vec.db"), timeout=60, check_same_thread=False)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("CREATE TABLE IF NOT EXISTS v (k TEXT PRIMARY KEY, b BLOB)")
            self._cdb = c
        return self._cdb

    def encode_batch(self, texts: Sequence[str]):
        """[n, d] float32，L2 归一；设了缓存时先查缓存，只编码未命中的文本。"""
        c = self._cache()
        if c is None or not texts:
            return self._encode_raw(texts)
        import hashlib
        np = self.np
        keys = [hashlib.sha1(f"{self.model}\0{self.fname}\0{t}".encode("utf-8")).hexdigest() for t in texts]
        got = {}
        for i in range(0, len(keys), 500):
            part = keys[i:i + 500]
            for k, b in c.execute(f"SELECT k, b FROM v WHERE k IN ({','.join('?' * len(part))})", part):
                got[k] = np.frombuffer(b, np.float32)
        miss = [i for i, k in enumerate(keys) if k not in got]
        if miss:
            v = self._encode_raw([texts[i] for i in miss])
            for i, row in zip(miss, v):
                got[keys[i]] = row
            c.executemany("INSERT OR IGNORE INTO v VALUES (?, ?)", [(keys[i], got[keys[i]].tobytes()) for i in miss])
            c.commit()
        return np.vstack([got[k] for k in keys]).astype(np.float32)

    def _encode_raw(self, texts: Sequence[str]):
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
            full = self.sess.run(None, feed)[0]
            if len(idx) == 1 and getattr(self, "tok_budget", 0):   # F3L：逐条编码时与 token_vecs 的前向逐位相同
                self._tok_put(texts[idx[0]], self._tok_of(full[0]))
            h = full[:, 0]
            h = h / np.maximum(np.linalg.norm(h, axis=1, keepdims=True), 1e-12)
            for r, i in enumerate(idx):
                out[i] = h[r]
        return np.vstack(out).astype(np.float32) if out else np.zeros((0, 1), np.float32)

    def _tok_of(self, h):
        """last_hidden_state [t, d] → 逐词向量（去 [CLS]/[SEP]，逐词 L2 归一，float32）。"""
        np = self.np
        h = h[1:-1] if h.shape[0] > 2 else h[:1]
        return (h / np.maximum(np.linalg.norm(h, axis=1, keepdims=True), 1e-12)).astype(np.float32)

    def _tok_put(self, text: str, v) -> None:
        """按字节预算的 LRU（F3L）。预算 0 时不存。"""
        if not getattr(self, "tok_budget", 0):
            return
        old = self._tokc.pop(text, None)
        if old is not None:
            self._tokbytes -= old.nbytes
        self._tokc[text] = v
        self._tokbytes += v.nbytes
        while self._tokbytes > self.tok_budget and len(self._tokc) > 1:
            _, x = self._tokc.popitem(last=False)
            self._tokbytes -= x.nbytes

    def token_vecs(self, text: str):
        """逐词向量 [t, d] float32（last_hidden_state 去 [CLS]/[SEP]，逐词 L2 归一；逐条编码）。
        供 densefuse F3a 晚交互 MaxSim（gen r8，思想来源 ColBERT, Khattab & Zaharia 2020）。
        gen r10 F3L：先查写入时顺带保存的逐词向量（同一次前向的输出，逐位相同），未命中才现算并放入同一 LRU。"""
        np = self.np
        v = self.__dict__.setdefault("_tokc", OrderedDict()).get(text)
        if v is not None:
            self._tokc.move_to_end(text)
            return v
        e = self.tok.encode(text)
        ids = np.array([e.ids], np.int64)
        feed = {"input_ids": ids, "attention_mask": np.ones_like(ids)}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        v = self._tok_of(self.sess.run(None, feed)[0][0])
        if getattr(self, "tok_budget", 0):
            self._tok_put(text, v)
        return v

    def prefetch_query(self, dense: Sequence[str], toks: Sequence[str] = ()) -> None:
        """F3P：预先编码稠密路查询句向量（填 qvec LRU，search 直接命中）与 MaxSim 查询逐词向量（进 F3L 的 LRU）。"""
        for t in dense:
            self.qvec(t)
        for t in toks:
            self.token_vecs(t)

    def maxsim(self, query: str, texts: Sequence[str]) -> List[float]:
        """MaxSim(q, d) = 查询各词对文档各词最大余弦的均值。"""
        q = self.token_vecs(query)
        ds = [self.token_vecs(t) for t in texts]
        with _Blas1():
            return [float((q @ d.T).max(axis=1).astype(self.np.float64).mean()) for d in ds]

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
        # 逐行独立求点积（逐元素乘 + 行内求和；与矩阵行序、BLAS 分块无关），同分按 id 断开：
        # 行序随后台编码线程的取批时序而变，矩阵乘与按行号断开都会让同一份库的名次在运行间漂移（gen r8 确定性修复）。
        q = self.qvec(query)
        s = (self.mat * q).sum(axis=1, dtype=np.float64)
        k = min(int(limit), len(self.ids))
        ids = self.ids
        top = sorted(np.argpartition(-s, k - 1)[:k].tolist() if k < len(ids) else range(len(ids)),
                     key=lambda i: (-s[i], ids[i]))
        # argpartition 的边界同分可能截掉 id 更小者：把与第 k 名同分的全部行纳入再截断
        if k < len(ids):
            kth = s[top[-1]]
            got = set(top)
            extra = [i for i in np.flatnonzero(s == kth).tolist() if i not in got]
            if extra:
                top = sorted(top + extra, key=lambda i: (-s[i], ids[i]))[:k]
        return [(ids[i], float(s[i])) for i in top]


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
