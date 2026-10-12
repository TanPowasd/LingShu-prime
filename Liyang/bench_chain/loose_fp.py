# -*- coding: utf-8 -*-
"""宽松抽取误登记（精度）评测：在**没有版本事件标注**的中文非合成语料上数宽松登记条数（越少越好，近似误登记）。
  语料 1：HMB 主线小说 178 块（novel_chunks）；dev＝序号偶数块，held＝奇数块。
  语料 2：HMB e2e 真实对话史（hmb/e2e/corpus/*.md，16 个文件），每文件取前 CAP 字；dev＝文件名 md5 首位为偶数，held＝奇数。
  python loose_fp.py dev [show]      只看 dev 半边（可逐条打印）
  python loose_fp.py held            冻结后只读一次总数（不打印逐条）
可设 FP_ROOT=<另一份代码根> 读别的版本（如 v7 快照）。"""
import glob, hashlib, json, os, sys
ROOT = os.environ.get("FP_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import importlib  # noqa: E402
E = importlib.import_module("lingshu_ng.chain.extract")
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))
import extract_cache as XC  # noqa: E402
E.extract = XC.wrap(E)
assert os.path.dirname(os.path.dirname(E.__file__)).startswith(ROOT.rstrip("/")), E.__file__
sys.path.insert(1, "/workspace/work/ls/wt-titans/bench_titans")
from common import novel_chunks  # noqa: E402
CAP = 200000


def e2e_docs():
    for p in sorted(glob.glob("/workspace/work/ls/hmb/e2e/corpus/*.md")):
        n = os.path.basename(p)
        half = "dev" if int(hashlib.md5(n.encode()).hexdigest()[0], 16) % 2 == 0 else "held"
        yield half, n, open(p, encoding="utf-8").read()[:CAP]


def run(half, show=False):
    res = {"novel": {"n_chunks": 0, "loose": 0, "strict": 0}, "e2e": {"n_files": 0, "chars": 0, "loose": 0, "strict": 0}}
    rows = []
    for i, c in enumerate(novel_chunks()):
        if (i % 2 == 0) != (half == "dev"):
            continue
        res["novel"]["n_chunks"] += 1
        for e in E.extract(c["text"]):
            if e.op == "mention":
                continue
            k = "loose" if e.extra.get("loose") else "strict"
            res["novel"][k] += 1; rows.append(("novel", i, k, e.op, e.entity, e.attr, e.value, e.quote[:80]))
    for h, n, t in e2e_docs():
        if h != half:
            continue
        res["e2e"]["n_files"] += 1; res["e2e"]["chars"] += len(t)
        for para in t.split("\n"):
            for e in E.extract(para):
                if e.op == "mention":
                    continue
                k = "loose" if e.extra.get("loose") else "strict"
                res["e2e"][k] += 1; rows.append(("e2e", n[:8], k, e.op, e.entity, e.attr, e.value, e.quote[:80]))
    print(json.dumps(res, ensure_ascii=False))
    if show:
        for r in rows:
            print(r)
    return res, rows


if __name__ == "__main__":
    half = sys.argv[1]
    run(half, show=(half == "dev" and len(sys.argv) > 2))
