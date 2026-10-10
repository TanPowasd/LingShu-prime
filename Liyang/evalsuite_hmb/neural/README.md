# neural 读路径实验台与原始读数

配套 `../../REPORT_neural.md`（读路径第三阶段：混合候选池 + 交叉编码重排 + 写入流多样化，均可选、默认关）。

- `engine_runs/*.json.gz`：各档走生产路径（`evalsuite_hmb/sys_worker.py` → add_perception → recall）的 HMB 184 问召回原始输出，gzip 压缩。
- `arm.sh` / `score.py`：复现脚本（脚本里的 `/workspace/work/...` 是原实验机路径，按本地检出改写 `HMB_ROOT`、`PYTHONPATH` 等即可）。
- `hmb_lab/`：离线实验台，`lab.py` 指标与 metrics_r1 同口径（含矛盾对代理 pairs_both）；`cache/` 为交叉编码打分与网格搜索的小型缓存，`*.log` 为当时运行日志。

不含模型文件。bge-m3 / bge-reranker-base 的 ONNX 目录需自行下载，经 `LINGSHU_NG_EMBED_MODEL`、`LINGSHU_NG_RERANK_MODEL` 指定。
