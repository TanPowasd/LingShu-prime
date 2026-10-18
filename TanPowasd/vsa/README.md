# TanPowasd/vsa —— 超维计算 / 向量符号架构（VSA/HDC）记忆 · 阶段 1

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
| `test_vsa.py` | 守卫 G1–G9 + `--mutate` 定点变异（12 条，全部须变红） |
| `synth.py` | 合成组合查询基准 + `--capacity` 容量曲线 |
| `real.py` | 真实集 dev 描述性检索（LoCoMo / hive / PerLTQA）+ LoCoMo 时间解绑 |
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

只跑 dev；不跑 UMB test / PerLTQA test，不碰 KMB hold / TMD。读数与结论见 `results/` 与 `RESULTS_v1.md`。
