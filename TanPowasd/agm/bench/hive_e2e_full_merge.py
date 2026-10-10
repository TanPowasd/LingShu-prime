"""合并 hive_e2e_full.py 的分片结果，按文件做配对比较。用法：python hive_e2e_full_merge.py 分片1.json 分片2.json … --json 输出"""
import argparse
import json
import pathlib

import agm_algos as X
from hive_e2e_full import ARMS

REFS = ("最近窗口", "近因+AGM-静态", "近因+BM25", "AGM-静态", "BM25")
METRICS = ("覆盖", "窗口外", "在线覆盖", "题卡覆盖")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--json", required=True)
    A = ap.parse_args()
    per = {}
    for p in A.parts:
        per.update(json.loads(pathlib.Path(p).read_text(encoding="utf-8")))
    files = sorted(per)
    pooled, filemean = {}, {}
    for arm in ARMS:
        pooled[arm], filemean[arm] = {}, {}
        for m in METRICS:
            rows = [per[f]["arms"][arm][m] for f in files if m in per[f]["arms"][arm]]
            n = sum(r["n"] for r in rows)
            if n:
                pooled[arm][m] = round(sum(r["均值"] * r["n"] for r in rows) / n, 4)
                filemean[arm][m] = round(sum(r["均值"] for r in rows) / len(rows), 4)
    cmp = {}
    for m in ("覆盖", "窗口外", "在线覆盖"):
        cmp[m] = {}
        for ref in REFS:
            for arm in ARMS:
                if arm == ref or (m == "窗口外" and "最近窗口" in (arm, ref)):
                    continue
                a = [per[f]["arms"][arm][m]["均值"] for f in files]
                b = [per[f]["arms"][ref][m]["均值"] for f in files]
                cmp[m][f"{arm} 对 {ref}"] = X.compare(a, b)
    out = {"说明": "e2e 全臂；统计单位＝文件（16 份）；预算 4000；r=0.5；RRF k=60 等权；参数跑前写死",
           "文件": {f: per[f]["meta"] for f in files},
           "合并均值(按轮加权)": pooled, "文件均值(等权)": filemean, "配对_按文件": cmp,
           "_n": {"文件": len(files), "查询": sum(per[f]["meta"]["查询"] for f in files)}}
    pathlib.Path(A.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"合并": pooled}, ensure_ascii=False, indent=0))


if __name__ == "__main__":
    main()
