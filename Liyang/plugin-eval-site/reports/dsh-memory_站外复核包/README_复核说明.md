# dsh-memory · 考卷 B · 站外复核包

> 本包给**站外复核人**用：灵枢（dsh-memory）是本站同门的官方插件，按《方案 v2.2》§6①「自家人管得更严」，
> 本站自己人的结论不算数，须由站外人按本包复跑、核对、逐条签字。复核人与本站、与灵枢项目方都不应有隶属关系。

## 0 被测对象与环境（一字不差地复现这些）

| 项 | 值 |
|:--|:--|
| 插件 | <https://github.com/FuRongJun-1999/dsh-memory> |
| 被测 commit | `c8c3655234d57214ae990ab2c7590f7ba590d901`（2026-10-10 00:22 +0800；package.json 0.8.1；MCP serverInfo `mdcg-mcp 0.8.1`） |
| 接法 | stdio MCP：`python3 -m md_cg.mcp_server`，`MDCG_MCP_SURFACE=full`；写 `cg(op=ingest, action=jsonl)`；召回 `mdcg_recall(query, k=5)` 其余全缺省 |
| 令牌 | designer，`--clearance private`，ops = README 原参数 + `ingest,session`（理由见 `plugins/dsh-memory/README_适配器.md` §4） |
| 考卷 | hive-memory-bench @ `72130ac`（注意：考卷仓与被测插件同属 GitHub 账号 FuRongJun-1999） `e2e/questions/题卡_C型_续接预测_v0.1.json`（89 卡），语料 `e2e/corpus/`（16 份） |
| 生成器 / 判官 | Cline `cline-pass/deepseek-v4.1-flash`；生成器 temperature 0.7、max_tokens 1500；双判官 temperature 0、max_tokens 600（参数以 run 目录 `config.json` 为准） |
| 种子 | 1, 2, 3（种子只作用于生成器；召回每卡一次、各种子共用——同库同查询召回逐次一致已自测） |
| 机器 | 2 核 / 7 GB Linux 沙箱，Python 3.12.15，Node 22.23.3 |
| 测试日期 | 2026-10-10（CST） |

## 1 重跑命令

```bash
# 0) 取代码
git clone <本站仓库> pes && cd pes            # 或使用本包所在仓库
git clone https://github.com/FuRongJun-1999/hive-memory-bench /workspace/work/ls/hmb && git -C /workspace/work/ls/hmb checkout 72130ac   # 本站所用 hmb commit
export CLINE_API_KEY=...                         # 生成器/判官用；不会进入插件沙箱

# 1) 安装体验录像（照 README 走一遍，约 30 秒；产物 = 录像/install.jsonl + install_时间轴.md）
python3 plugins/dsh-memory/install_recorded.py --sha c8c3655234d57214ae990ab2c7590f7ba590d901 \
    --out reports/dsh-memory_站外复核包/录像

# 2) 退役/撤销旧账复测（约 10 秒）
python3 plugins/dsh-memory/retire_probe.py --out reports/dsh-memory_站外复核包/录像

# 3) 考卷 B：底子臂 / 插件臂 / BM25 参照臂（各 3 种子，逐题落盘，可 --resume）
python3 -m harness.run --plugin null  --seeds 1,2,3 --out /tmp/pes-runs/B_null
python3 -m harness.run --plugin bm25  --seeds 1,2,3 --out /tmp/pes-runs/B_bm25
python3 -m harness.run --plugin plugins/dsh-memory/adapter.py:DshMemoryPlugin --seeds 1,2,3 --out runs/B_dsh
#   插件期约 95 分钟（写入 ≈60 s；89 次召回 × ≈60 s）；中断后加 --resume 续跑
```

## 2 包内文件

| 路径 | 内容 |
|:--|:--|
| `录像/install.jsonl` · `录像/install_时间轴.md` | 真实安装全程（每条命令、输出、退出码、耗时；令牌明文已遮蔽） |
| `录像/snap_before.json` · `snap_after_install.json` · `residue_after_uninstall.json` | HOME 与 MDCG_ROOT 快照与卸载后残留 |
| `录像/retire_probe.jsonl` · `retire_probe_时间轴.md` | 退役/撤销复测录像 |
| `run_B_dsh/` | 考卷 B 插件臂运行目录拷贝：`config.json` `state.json` `summary.json` `recording.jsonl` `timeline.md` 与 `q/`（逐题召回材料、各种子作答）、`judge/`（各种子判官批，含锚题上岗记录） |
| `逐题结果_B_dsh.csv` | 每卡 × 每种子：判档（插件臂 / 底子臂 / BM25）、召回源、泄题过滤动作、材料字数、录像时间点 |
| `历史成绩与旧账_原文摘录.md` | 蜂巢基准里灵枢的历史成绩与旧账，逐字摘录（含好看的和难看的） |
| `需复核的判断点清单.md` | 本站做过的每一个"判断"，逐条请复核人签 同意 / 不同意 / 无法判断 |

## 3 怎么核

1. 先跑 §1-1，对照 `录像/install_时间轴.md` 看每个报错是否复现（报告里每个扣分点都标了 mm:ss）。
2. 跑 §1-3 后，`summary.json` 的 per_seed 档位分布与报告表格逐格比对；种子间波动是生成器温度带来的，三种子方向是否一致才是看点。
3. 逐条过 `需复核的判断点清单.md`。任何一条"不同意"都请写理由，本站按《方案》§6③ 出更正版、旧版保留。
