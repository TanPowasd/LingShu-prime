# TanPowasd/vsa —— 超维计算 / 向量符号架构（VSA/HDC）记忆 · 阶段 1–2

零 LLM、零 API、零训练神经网络、确定性（固定种子）。与 `agm/` 无代码依赖；评测时只读 import `agm/umb`、`agm/bench`、`agm/all`
的数据加载与指标函数。依赖 numpy、scipy。

| 文件 | 内容 |
|---|---|
| `THEORY.md` | 理论核：MAP-B 族（D=10000）、绑定/叠加/置换/清理、痕迹 = Σ 角色⊗填充、Random Indexing、容量理论、不变量 I1–I7、诚实边界 |
| `PREREG_v1.md` | 预注册（读数前写定）：合成基准、真实集 dev 检索、LoCoMo 时间解绑 |
| `hdc.py` | 原语与容量公式（`bind/unbind/bundle/permute/cos`、`k_max`、`err_bound`、`MARGIN_MIN`） |
| `cleanup.py` | 清理记忆（边距不足 ⇒「存疑」） |
| `ri.py` | Random Indexing（写入时增量共现计数 A，C = A·I，按 1000 维一块投影） |
| `memory.py` | 分词、规则抽角色（中英文，规则号 + 原文片段可回溯）、`Memory.write/search_many/trace/decode/query` |
| `bm25.py` | 自写 Okapi BM25（k1=0.9 b=0.4） |
| `test_vsa.py` | 守卫 G1–G24 + `--mutate` 定点变异（31 条，全部须变红） |
| `synth.py` | 合成组合查询基准 + `--capacity` 容量曲线 |
| `real.py` | 真实集 dev 描述性检索（LoCoMo / hive / PerLTQA）+ LoCoMo 时间解绑 |
| `PREREG_v2.md` | 阶段 2 预注册（读数前写定）：te 召回 + VSA 解绑、时间规则 v2、PerLTQA 中文旁证、合成 v2（噪声 + 多跳） |
| `real_v2.py` | 阶段 2 真实集：LoCoMo dev 时间题（te10 候选、TIME/SESSION 双角色、显式时间优先、J1/J2 判定）、PerLTQA dev 中文时间题 |
| `synth_v2.py` | 合成 v2：代词 / 省略主语 / 规则内外改写 + T4 交集 / T5 链式多跳；VSA vs BM25 vs 符号表 |
| `RESULTS_v2.md` | 阶段 2 读数与结论 |
| `PREREG_seg.md` | 事件切分写入预注册（v0.1，用户 2026-10-21 确认；读数前提交） |
| `seg.py` | 事件切分：断层判据 o_t<θ·μ_t / 日期 / 场景 / K_MAX 强制切、S1 固定长度、段痕迹、段排序→成员轮展开、段痕迹解绑 |
| `seg_real.py` | 事件切分真实集读数（E1/E2/E3、§4 选臂；§5 保留集入口带只跑一次的拒跑保护） |
| `RESULTS_seg.md` | 事件切分读数与结论（dev 无增益：PerLTQA 显著倒退 ⇒ 未碰保留集） |
| `PREREG_long.md` | 长单元分块 L1 预注册（只切超 K_MAX 的单元；读数前提交）；`long_count.py` 保留集超限单元计数 |
| `long_real.py` | L1 真实集 dev 读数（复用 seg_real 口径；`seg.segment_long`） |
| `results/` | 读数（汇总 json/md；不含任何数据） |

## 复跑

```bash
cd <仓根>/TanPowasd/vsa
python -X utf8 test_vsa.py && python -X utf8 test_vsa.py --mutate
python -X utf8 synth.py               # → results/synth_v1.*
python -X utf8 synth.py --capacity    # → results/capacity_v1.*
# 真实集：环境变量同 agm/umb/README.md，另 UMB_PERLTQA=<PerLTQA>/Dataset/zh；逐题缓存写 $VSA_OUT（默认 <仓根>/TanPowasd/vsa/data，不入库）
python -X utf8 real.py --set hive && python -X utf8 real.py --set locomo && python -X utf8 real.py --set perltqa --budget-secs 900   # 可重复执行续跑
python -X utf8 real.py --summary      # → results/real_v1.*（bm25/te 读 $UMB_OUT/runs/dev/<集>/{bm25,te}.json 既有缓存）
```

阶段 2：
```bash
python -X utf8 synth_v2.py                     # → results/synth_v2.*
python -X utf8 real_v2.py --set locomo && python -X utf8 real_v2.py --set perltqa && python -X utf8 real_v2.py --summary   # → results/real_v2.*
```

只跑 dev；不跑 UMB test / PerLTQA test，不碰 KMB hold / TMD。读数与结论见 `results/`、`RESULTS_v1.md`、`RESULTS_v2.md`。
