# bge-small-zh-v1.5（Xenova ONNX）本地句向量：离线原型用，CLS 池化 + L2 归一
import os, time, numpy as np, onnxruntime as ort
from tokenizers import Tokenizer
MD = os.environ.get("LS_VEC_MODEL_DIR", "/tmp/models/bge-small-zh")
class Emb:
    def __init__(self, fname="model_quantized.onnx", maxlen=512, threads=1):
        so = ort.SessionOptions(); so.intra_op_num_threads = threads; so.inter_op_num_threads = 1
        self.s = ort.InferenceSession(os.path.join(MD, fname), so, providers=["CPUExecutionProvider"])
        self.t = Tokenizer.from_file(os.path.join(MD, "tokenizer.json"))
        self.t.enable_truncation(maxlen); self.inames = [i.name for i in self.s.get_inputs()]
    def enc(self, texts, bs=16):
        out = []
        for k in range(0, len(texts), bs):
            b = self.t.encode_batch(texts[k:k+bs]); L = max(len(e.ids) for e in b)
            ids = np.zeros((len(b), L), np.int64); am = np.zeros_like(ids)
            for r, e in enumerate(b): ids[r, :len(e.ids)] = e.ids; am[r, :len(e.ids)] = 1
            feed = {"input_ids": ids, "attention_mask": am}
            if "token_type_ids" in self.inames: feed["token_type_ids"] = np.zeros_like(ids)
            h = self.s.run(None, feed)[0][:, 0]
            out.append(h / np.linalg.norm(h, axis=1, keepdims=True))
        return np.vstack(out).astype(np.float32)
if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/workspace/work/ls/rewrite/evalsuite_hmb"); import hmb_lib as H
    ch = [c["text"] for c in H.novel_chunks()]
    for fn in ("model_quantized.onnx", "model.onnx"):
        e = Emb(fn); t0 = time.perf_counter(); V = e.enc(ch[:32]); dt = time.perf_counter() - t0
        t1 = time.perf_counter(); [e.enc(["巨子塔里埋的是谁"]) for _ in range(10)]; dq = (time.perf_counter() - t1) / 10
        print(fn, "chunk ms", 1000*dt/32, "query ms", 1000*dq, V.shape)
