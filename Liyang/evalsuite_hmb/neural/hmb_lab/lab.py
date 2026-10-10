# -*- coding: utf-8 -*-
"""HMB 检索轨实验台：与 evalsuite_hmb/metrics_r1.py 同口径（同切块、同 k=10、同指标），
方法只需返回每题的块下标排名。用于快速筛方案；最终读数仍以引擎生产路径实测为准。"""
from __future__ import annotations
import json, math, os, re, statistics, sys, hashlib
from collections import Counter

HMB = os.environ.get("HMB_ROOT", "/workspace/work/hive-memory-bench")
LIB = "/workspace/work/LingShu-prime/Liyang/evalsuite_hmb"
os.environ["HMB_ROOT"] = HMB
sys.path.insert(0, LIB)
import hmb_lib as H  # noqa

CACHE = "/workspace/work/hmb_lab/cache"
os.makedirs(CACHE, exist_ok=True)
K = 10

CHUNKS = H.novel_chunks()
TEXTS = [c["text"] for c in CHUNKS]
CARDS = H.load_cards()
QMAIN = {q["qid"]: q["question"] for q in H.load_questions("main")}
QINT = {q["qid"]: (q["question"], q["base_qid"]) for q in H.load_questions("interv")}
QIDS = sorted(QMAIN)
DEV = QIDS[0::2]
TEST = QIDS[1::2]


def metrics(rank, qids=None, which="main"):
    """rank: {qid: [chunk_idx,...]}; which=main 用主轮题文；interv 用干预轮题、按 base 卡评。"""
    qids = qids or QIDS
    cidr, full, qr, pc, exc = [], [], [], [], []
    for qid in qids:
        card = CARDS[qid]
        key = qid if which == "main" else qid + "i"
        hits = rank[key][:K]
        got = {CHUNKS[i]["cid"] for i in hits}
        ev = H.card_evidence(card)
        need = {e["cid"] for e in ev}
        blob = "\n".join(TEXTS[i] for i in hits)
        nb = H.norm(blob)
        cr = len(need & got) / max(1, len(need))
        cidr.append(cr); full.append(cr == 1.0)
        qr.append(sum(1 for e in ev if H.norm(e["quote"]) and H.norm(e["quote"]) in nb) / max(1, len(ev)))
        pts = H.card_points(card)
        pc.append(sum(1 for p in pts if H.point_hit(p, blob)) / max(1, len(pts)))
        me = card.get("must_exclude") or []
        if me:
            exc.append(sum(1 for e in me if H.norm(e["quote"]) in nb) / len(me))
    f = lambda x: round(statistics.mean(x), 4)
    return {"cid": f(cidr), "full": f(full), "quote": f(qr), "point": f(pc), "excl": f(exc) if exc else None}


def report(name, rank, show=True):
    out = {"all": metrics(rank), "dev": metrics(rank, DEV), "test": metrics(rank, TEST)}
    if all(q + "i" in rank for q in QIDS):
        out["interv"] = metrics(rank, which="interv")
    if show:
        a, d, t = out["all"], out["dev"], out["test"]
        iv = out.get("interv", {})
        print(f"{name:38s} cid {a['cid']:.4f} (dev {d['cid']:.4f} / test {t['cid']:.4f}) full {a['full']:.3f} "
              f"quote {a['quote']:.4f} point {a['point']:.4f} excl {a['excl']:.4f} | interv cid {iv.get('cid', 0):.4f} quote {iv.get('quote', 0):.4f}")
    return out


def all_queries():
    q = dict(QMAIN)
    q.update({k + "": v[0] for k, v in QINT.items()})
    return q


# ---------------------------------------------------------------- lexical
_CJK = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]")


def toks_bigram_raw(s):
    return H._toks(s)


def toks_cjk(s, uni=False):
    s = _CJK.sub(" ", str(s))
    out = []
    for seg in s.split():
        if uni:
            out.extend(seg)
        out.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return out


class BM25:
    def __init__(self, docs_toks, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(t) for t in docs_toks]
        self.dl = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.dl) / len(self.dl)
        df = Counter()
        for t in self.tf:
            df.update(t.keys())
        N = len(docs_toks)
        self.idf = {w: math.log(1 + (N - n + 0.5) / (n + 0.5)) for w, n in df.items()}

    def scores(self, qtoks):
        sc = [0.0] * len(self.tf)
        for w in set(qtoks):
            idf = self.idf.get(w)
            if not idf:
                continue
            for i, t in enumerate(self.tf):
                f = t.get(w)
                if f:
                    sc[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avg))
        return sc


def argsort(sc):
    return sorted(range(len(sc)), key=lambda i: (-sc[i], i))


# ---------------------------------------------------------------- dense / rerank (onnx)
MODELS = "/workspace/models"


class Encoder:
    def __init__(self, name, pool="cls", maxlen=512, threads=2):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        d = os.path.join(MODELS, name)
        so = ort.SessionOptions(); so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(os.path.join(d, "onnx", "model_quantized.onnx"), so, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(os.path.join(d, "tokenizer.json"))
        self.tok.enable_truncation(maxlen)
        self.inputs = [i.name for i in self.sess.get_inputs()]
        self.pool = pool
        self.name = name

    def _run(self, encs):
        import numpy as np
        L = max(len(e.ids) for e in encs)
        ids = np.zeros((len(encs), L), dtype=np.int64); am = np.zeros_like(ids)
        for j, e in enumerate(encs):
            ids[j, :len(e.ids)] = e.ids; am[j, :len(e.ids)] = 1
        feed = {"input_ids": ids, "attention_mask": am}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        return self.sess.run(None, feed), am

    def encode(self, texts, prefix=""):
        import numpy as np
        out = []
        for t in texts:  # 逐条：int8 动态量化按批定尺度，逐条保证确定性
            (o, *_), am = self._run([self.tok.encode(prefix + t)])
            if self.pool == "cls":
                v = o[0, 0]
            else:
                v = (o[0] * am[0][:, None]).sum(0) / am[0].sum()
            out.append(v / (np.linalg.norm(v) + 1e-12))
        return np.stack(out)

    def cached(self, texts, prefix="", tag=""):
        import numpy as np
        h = hashlib.md5(("\x00".join(texts) + prefix + self.name + self.pool).encode()).hexdigest()[:12]
        p = os.path.join(CACHE, f"emb_{self.name}_{tag}_{h}.npy")
        if os.path.exists(p):
            return np.load(p)
        v = self.encode(texts, prefix)
        np.save(p, v)
        return v


class CrossEncoder:
    def __init__(self, name, maxlen=512, threads=2):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        d = os.path.join(MODELS, name)
        so = ort.SessionOptions(); so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(os.path.join(d, "onnx", "model_quantized.onnx"), so, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(os.path.join(d, "tokenizer.json"))
        self.tok.enable_truncation(maxlen)
        self.inputs = [i.name for i in self.sess.get_inputs()]
        self.name = name

    def score(self, q, docs):
        import numpy as np
        res = []
        for d in docs:
            e = self.tok.encode(q, d)
            ids = np.array([e.ids], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": np.ones_like(ids)}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.array([e.type_ids], dtype=np.int64)
            res.append(float(self.sess.run(None, feed)[0].reshape(-1)[0]))
        return res


def ce_cache(name):
    p = os.path.join(CACHE, f"ce_{name}.json")
    return p, (json.load(open(p)) if os.path.exists(p) else {})


# ---------------------------------------------------------------- 矛盾对两侧存活（metrics_r1 代理清单 + 压缩代价.py 口径）
def _pairs():
    sys.path.insert(0, LIB)
    import metrics_r1 as M
    return M.build_proxies(CARDS, QMAIN)


_PX = None


def pairs_both(rank, n=8):
    global _PX
    _PX = _PX or _pairs()
    def cb(a, b):
        a, b = H.norm(a), H.norm(b)
        if len(a) < n: return a in b
        return any(a[i:i + n] in b for i in range(len(a) - n + 1))
    out = {}
    for name in ("pairs_all", "pairs_hard9"):
        both = bside = 0
        for p in _PX[name]:
            blob = "\n".join(TEXTS[i] for i in rank[p["qid"]][:K])
            A, Bs = cb(p["a"], blob), cb(p["b"], blob)
            both += A and Bs; bside += Bs
        out[name] = f"{both}/{bside}/{len(_PX[name])}"
    return out
