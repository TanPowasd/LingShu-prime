# EverOS · 考卷 B · 站外复核包

> 给**站外复核人**：照本包复跑安装、核对读数、逐条签《需复核的判断点清单》。EverOS 不是灵枢自家插件，
> 本包按普通插件口径准备；但本场能力分**未完成**，复核重点是安装体验、成本外推与适配器口径是否公道。

## 0 被测对象与环境

| 项 | 值 |
|:--|:--|
| 插件 | <https://github.com/EverMind-AI/EverOS> |
| 被测版本 | PyPI `everos==1.4.1` = tag `v1.4.1` = commit `462ebf9fd59b55c03fefb8eec855c62500f2a3cf`（2026-09-24） |
| 接入方式依据 | 官方 DSH 插件 <https://github.com/EverMind-AI/plugins/tree/main/dsh> @ `f76f4d06135a0b5d784d15eed133ecdcedc12d47` |
| 接法 | 本地 HTTP：`everos server start --root <记忆根>`；写 `/api/v2/memory/add`（`defer_extraction=true`，≥50 条或估算 ≥12,000 token 一批）+ `/api/v2/memory/flush`；召回 `/api/v2/memory/search` user 轨（`include_profile=true`）+ agent 轨，`method=keyword`，`top_k=5`，query 截前 2,000 字 |
| 插件用 LLM | `[llm]` → 考场侧本地转发器 `plugins/everos/llm_proxy.py` → Cline `cline-pass/deepseek-v4.1-flash`（只改 model、关 thinking，其余透传）；嵌入/重排/多模态未配 |
| 考卷 | hive-memory-bench @ `72130ac`，`e2e/questions/题卡_C型_续接预测_v0.1.json`（89 卡），`e2e/corpus/`（16 份） |
| 生成器 / 判官 | 同 dsh-memory 报告：Cline flash，生成器 T 0.7 / 1500，双判官 T 0 / 600（以 run 目录 `config.json` 为准） |
| 机器 | 2 核 / 7 GB Linux 沙箱，Python 3.12.15，uv 已装 |
| 日期 | 2026-10-10（CST） |

## 1 重跑命令

```bash
cd pes
export CLINE_API_KEY=...     # 只给考场侧转发器；EverOS 进程环境里没有它

# 1) 安装体验录像（照 README Quick Start；约 2 分钟）
python3 plugins/everos/llm_proxy.py --port 18611 --log runs/everos/proxy_probe.jsonl &   # 第 5 步配置指向它
python3 plugins/everos/install_recorded.py --steps S1,S2,S2v,S3,S4
python3 plugins/everos/install_recorded.py --resume --steps S5,S6,S7
python3 plugins/everos/install_recorded.py --resume --steps U      # 先停 :8000 的服务

# 2) 冒烟（harness，限 1 份语料、2 卡、不判分；约 15 分钟，视网关排队）
PES_SBX_ROOT=$PWD/runs/sbx PES_EVEROS_PORT=18800 PES_EVEROS_SESSIONS=公式符号复制乱码原因.md \
  python3 -m harness.run --plugin plugins/everos/adapter.py:EverOS --seeds 1 --limit 2 --skip-judge --out runs/B_everos_smoke

# 3) 全量臂（89 卡 × 3 种子；写入 698 批，预计数小时；断点续跑）
PES_EVEROS_PAR=4 ./tools/start_everos_arm.sh        # 中断后再跑同一命令即续
python -m harness.compare --base runs/B_null --plug runs/B_everos --out reports/B_everos_vs_null

# 4) 读数汇总
python3 plugins/everos/report_numbers.py > reports/everos_站外复核包/读数_everos.json
```

## 2 本包内容

| 文件 | 内容 |
|:--|:--|
| `录像/everos_install.jsonl` + `_时间轴.md` | 照 README 的安装 S1–S7 与卸载 U0–U3 |
| `录像/everos_checks.jsonl` | 只读核对（API 缺省 hybrid → 422；/health 能力矩阵） |
| `录像/everos_probe.jsonl` | 单会话写入探针（`传递信任与经验.md`，中途停掉，只用于单位成本） |
| `录像/B_everos_smoke.jsonl` | harness 冒烟（1 份语料 5 批、2 卡召回、种子 1 作答） |
| `录像/B_everos.jsonl` | 全量臂录像（截至报告时刻，未完成） |
| `读数_everos.json` | 机读读数（安装步、单位写入成本、全量进度、冒烟召回、外联采样） |
| `需复核的判断点清单.md` | 逐条签字 |
