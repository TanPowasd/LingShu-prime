# 说明书 · 自己重跑考卷 B（真实聊天记录 · C 型续接预测）

> 目标：任何人用这份说明书，在一台干净机器上把"底子分（无插件）"与"朴素 BM25 参照臂"在考卷 B 上重跑一遍，并得到同口径的三张单子。
> 依据：`SPEC_接线规范_v0.1.md`。本说明书已在干净 venv 中实测（见文末"实测记录"）。

## 0. 你需要

- Linux / macOS，Python ≥ 3.10（只用标准库；pytest 仅用于自检）
- git
- 一个 Cline API key（生成器与判官都走 `https://api.cline.bot/api/v1/chat/completions`，模型 `cline-pass/deepseek-v4.1-flash`）
- 预算参考：两臂 × 3 种子 × 89 卡全量 ≈ 生成 534 次 + 判官约 1,650 次（含每批 48 锚 × 双判官）；token 实数见 `LEDGER.md`

## 1. 取代码与考卷

```bash
git clone <本仓库地址> pes && cd pes
git clone https://github.com/<hive-memory-bench 仓库> hmb
git -C hmb checkout 72130ac          # 本站读数所用版本；换版本请在报告中写明
```

考卷 B 只读这两处，**不要改**：
- `hmb/e2e/questions/题卡_C型_续接预测_v0.1.json`（89 卡；含答案键，勿用于训练）
- `hmb/e2e/corpus/*.md`（16 份真实对话）

## 2. 干净 venv

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pytest                   # 仅自检用；harness 本身零依赖
export CLINE_API_KEY=...             # 只放环境变量，别写进文件；harness 不会打印它，也不会传给插件沙箱
```

## 3. 自检（不联网）

```bash
export PES_HMB=$PWD/hmb             # 考卷位置（也可每条命令加 --hmb ./hmb）
python -m pytest -q tests            # 期望：23 passed（找不到考卷时依赖考卷的用例显示 skipped）
```

## 4. 冒烟（约 1–2 分钟，几十次调用）

```bash
python -m harness.run --hmb ./hmb --plugin null --seeds 1 --limit 2 --out runs/smoke_null
python -m harness.run --hmb ./hmb --plugin bm25 --seeds 1 --limit 2 --out runs/smoke_bm25
python -m harness.compare --base runs/smoke_null --plug runs/smoke_bm25 --out reports/smoke
```

期望：每个 `runs/*/` 下出现 `config.json / recording.jsonl / timeline.md / q/ / judge/ / summary.json`；
`summary.json → per_seed → gate.pass = true`（判官上岗考通过）；
compare 输出结论为 🚧（因为冒烟只有 1 个种子，规范要求 ≥3——这是对的）以及 `citations_all_pass: true`。

## 5. 全量（两臂 × 3 种子 × 89 卡）

```bash
python -m harness.run --hmb ./hmb --plugin null --seeds 1,2,3 --out runs/B_null
python -m harness.run --hmb ./hmb --plugin bm25 --seeds 1,2,3 --out runs/B_bm25
python -m harness.compare --base runs/B_null --plug runs/B_bm25 --out reports/B_bm25_vs_null
```

- **断点续跑**：中途断了，原命令加 `--resume` 即可（逐题结果已落盘：`q/<qid>.recall.json`、`q/<qid>.s<seed>.gen.json`、`judge/s<seed>.json`；录像追加、时间轴单调）。
- **并发**：`--concurrency 3`（默认）；同机多个运行器共享 `/tmp/pes-llm-slots` 并发闸（`PES_LLM_SLOTS`，默认 8）与匀速闸（`PES_LLM_INTERVAL`，默认 1.5 秒/次，跨进程）。网关按时间窗限流（先 429、后断连），harness 会全局冷却并指数退避。
- 想放后台：`nohup python -m harness.run ... > logs/x.log 2>&1 &`。

## 6. 看结果

| 文件 | 内容 |
|:--|:--|
| `reports/…/能力分.md` | 结论（✅/❌/😐/🚧）、净提升（整数题）与 95% 区间、逐种子读数、判官上岗表、依据轴、扣分点 |
| `reports/…/能力分_扣分明细.md` | 插件臂每个非 strict 判定，逐条带录像引用 |
| `reports/…/好不好用.md` | 安装/写入/报错/文档（文档为人工栏） |
| `reports/…/成本与安全.md` | token、写入耗时、检索延迟、权限、卸载残留 |
| `reports/…/录像引用校验.json` | 每个【扣】行是否都能对到录像事件（须 all_pass=true） |
| `runs/*/timeline.md` | 录像 mm:ss 时间轴；报告里的 `⟦录像:<run>@mm:ss#seq⟧` 在这里按 #seq 查 |

## 7. 接你自己的插件

写一个 `Plugin` 子类（接口见 `harness/adapter.py` 与 SPEC §2），然后：

```bash
python -m harness.run --hmb ./hmb --plugin path/to/adapter.py:MyPlugin --seeds 1,2,3 --out runs/B_my
python -m harness.compare --base runs/B_null --plug runs/B_my --out reports/B_my_vs_null
```

底子臂 `runs/B_null` 可复用（同一 harness 版本、同卷、同种子）；compare 会核对两臂配置，不一致直接给 🚧。

## 8. 读数为什么和我的不完全一样

生成器 T=0.7（种子＝重复采样），网关不保证 seed 复现；判官 T=0 但模型服务端仍有微小非确定性。
所以**逐题判定会有出入，结论（四种之一）与整数题数区间应一致**。若你的结论与我们不同，请按 SPEC §9 开 issue，附你的 `runs/` 目录。

---

## 实测记录（干净 venv）

- 日期：2026-10-10 01:20–01:45 CST；执行人：pes-harness
- 环境：Linux 沙箱，Python 3.12.15，`git clone` 本仓库（`6ae05cc`）到全新目录 → `python3 -m venv .venv` → `pip install pytest`；hmb `git clone` 后 `checkout 72130ac`；`export PES_HMB=$PWD/hmb`
- 第 3 步自检：`19 passed`（干净 venv 内）
- 第 4 步冒烟：两臂各 2 卡 × 1 种子跑通；判官上岗考两批均通过（锚正确率 98%/100%、100%/100%）；compare 结论 🚧（"种子数 1 < 3"，符合预期）；`录像引用校验.json → all_pass: true`（3 个扣分点全部对到录像）
- 实测中遇到并已写进说明书的坑：① 冒烟中途被打断后，原命令不加 `--resume` 会拒绝覆盖已有录像（设计如此，加 `--resume` 即续）；② 网关按时间窗限流，多运行器并跑时须共享匀速闸（已默认）
- 第 5 步全量：即本站底子分与参照臂读数本身（`runs/B_null`、`runs/B_bm25`），见 `reports/B_bm25_vs_null/`
