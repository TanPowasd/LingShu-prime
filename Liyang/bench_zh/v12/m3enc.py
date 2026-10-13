# zh-v12 S2：BGE-M3（gpahal/bge-m3-onnx-int8 @2b34e84，MIT）稠密 / 稀疏 / ColBERT 三分（BGE-M3 论文 Chen et al. 2024 的打分式；自研实现）
import json, os, sys, time, numpy as np, onnxruntime as ort
from tokenizers import Tokenizer
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = "/workspace/work/ls/_shared/models/bge-m3-int8"
D = os.path.join(HERE, "runs", "t2r2", "v12"); P = json.load(open(os.path.join(D, "pairs.json")))
so = ort.SessionOptions(); so.intra_op_num_threads = 2; so.inter_op_num_threads = 1
S = ort.InferenceSession(os.path.join(MD, "model_quantized.onnx"), so, providers=["CPUExecutionProvider"])
tok = Tokenizer.from_file(os.path.join(MD, "tokenizer.json")); tok.enable_truncation(max_length=int(os.environ.get("M3_MAXLEN", "384"))); tok.enable_padding(pad_id=1, pad_token="<pad>")
SPEC = {0, 1, 2, 3}
def enc(texts):
    r = []
    for s in range(0, len(texts), 8):
        es = tok.encode_batch(texts[s:s + 8]); ids = np.array([e.ids for e in es]); am = np.array([e.attention_mask for e in es])
        dv, sv, cv = S.run(None, {"input_ids": ids, "attention_mask": am})
        for b in range(len(es)):
            n = int(am[b].sum()); w = {}
            for t, x in zip(ids[b][:n], sv[b][:n, 0]):
                if int(t) not in SPEC and x > w.get(int(t), 0): w[int(t)] = float(x)
            r.append((dv[b], w, cv[b][: n - 1]))
    return r
op = os.path.join(D, "sc_m3.json"); out = json.load(open(op)) if os.path.exists(op) else {}
t0 = time.time()
for k, (q, v) in enumerate(P.items()):
    if q in out: continue
    it = [x for x in v["items"] if x["lab"] in "EM"]
    (qd, qw, qc), *ps = enc([v["q"]] + [x["t"] for x in it])
    out[q] = {str(x["i"]): [round(float(qd @ pd), 5), round(sum(a * pw.get(t, 0) for t, a in qw.items()), 5), round(float((qc @ pc.T).max(1).mean()), 5)] for x, (pd, pw, pc) in zip(it, ps)}
    if k % 10 == 9: json.dump(out, open(op + ".tmp", "w")); os.replace(op + ".tmp", op); print(k + 1, round(time.time() - t0), flush=True)
json.dump(out, open(op + ".tmp", "w")); os.replace(op + ".tmp", op); print("DONE", len(out), round(time.time() - t0), flush=True)
