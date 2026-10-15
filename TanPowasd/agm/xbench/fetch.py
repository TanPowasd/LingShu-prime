# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""取外部检索集到本地（数据不入库）。
英文：BEIR 官方压缩包（public.ukp.informatik.tu-darmstadt.de/thakur/BEIR），已是 corpus/queries/qrels 格式。
中文：C-MTEB 检索集（huggingface.co/datasets/C-MTEB/<名>、<名>-qrels，dev 拆分），parquet 转成 BEIR 格式；
      转换需要 pyarrow（只取数用，评测本身纯标准库）。
用法：python -X utf8 fetch.py <目标目录> [名字 ...]"""
import json, os, pathlib, subprocess, sys, urllib.request, zipfile

BEIR = ["scifact", "nfcorpus", "arguana", "fiqa", "scidocs", "trec-covid", "quora", "webis-touche2020", "nq", "hotpotqa"]
CMTEB = ["T2Retrieval", "DuRetrieval", "MMarcoRetrieval", "CmedqaRetrieval", "CovidRetrieval",
         "VideoRetrieval", "EcomRetrieval", "MedicalRetrieval"]
HF = "https://huggingface.co"


def get(url, dst):
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, dst)
    return dst


def beir(root, name):
    z = get(f"https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/{name}.zip", root / f"{name}.zip")
    if not (root / name / "corpus.jsonl").exists():
        zipfile.ZipFile(z).extractall(root)


def files(repo):
    with urllib.request.urlopen(f"{HF}/api/datasets/{repo}/tree/main/data") as r:
        return [x["path"] for x in json.load(r) if x["path"].endswith(".parquet")]


def cmteb(root, name):
    import pyarrow.parquet as pq
    d = root / name
    if (d / "qrels" / "dev.tsv").exists():
        return
    (d / "qrels").mkdir(parents=True, exist_ok=True)
    raw = root / "_raw" / name
    for repo in (f"C-MTEB/{name}", f"C-MTEB/{name}-qrels"):
        for p in files(repo):
            get(f"{HF}/datasets/{repo}/resolve/main/{p}", raw / repo.split("/")[1] / pathlib.Path(p).name)
    for f in sorted((raw / name).glob("*.parquet")):
        kind = "corpus" if f.name.startswith("corpus") else "queries"
        with open(d / f"{kind}.jsonl", "w", encoding="utf-8") as out:
            for row in pq.read_table(f).to_pylist():
                out.write(json.dumps({"_id": str(row["id"]), "title": "", "text": row["text"]}, ensure_ascii=False) + "\n")
    with open(d / "qrels" / "dev.tsv", "w", encoding="utf-8") as out:
        out.write("query-id\tcorpus-id\tscore\n")
        for f in sorted((raw / f"{name}-qrels").glob("*.parquet")):
            for row in pq.read_table(f).to_pylist():
                out.write(f"{row['qid']}\t{row['pid']}\t{int(row['score'])}\n")


def main():
    root = pathlib.Path(sys.argv[1]); names = sys.argv[2:] or BEIR[:6] + CMTEB
    for n in names:
        (beir if n in BEIR else cmteb)(root / ("beir" if n in BEIR else "cmteb"), n)
        print("ok", n, flush=True)


if __name__ == "__main__":
    main()
