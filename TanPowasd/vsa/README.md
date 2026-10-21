# TanPowasd/vsa —— 超维计算 / 向量符号架构（VSA/HDC）记忆 · 阶段 1–2

零 LLM、零 API、零训练神经网络、确定性（固定种子）。
**默认写入 = L1**（2026-10-21 起，`PREREG_long.md` §1：短单元逐单元原样写入，只把叠加项数 > K_MAX=221 的单元按写入序装成 ≤ K_MAX 的块；`seg.segment_long`）。依据 `RESULTS_long_hold.md`；短轮语料上 L1 ≡ S0。
代码默认已接入（2026-10-21）：`memory.Memory.write` 默认 `chunk_long=True` 走 `seg.segment_long`（≤K_MAX 单元逐位同旧路径；>K_MAX 单元切块、共享单元号、不再拒写，块数见 `Memory.n_chunks`）；单元级排序 `Memory.rank_units`、单元级解绑 `Memory.units()`。`Memory(chunk_long=False)` 或 `write(..., chunk_long=False)` 回到旧路径 S0（超 K_MAX 在 `trace` 抛 `CapacityError`），`real.py` / `real_v2.py` 已显式钉 S0 以复现历史读数。等价核对见 `results/default_check.md`。
**正文日期边界（2026-10-22，`RESULTS_body_date.md`，选项 D）**：每个长单元在单元级解绑时只解出首个日期（L1 首块 TIME；首块多 TIME 时常为存疑），问长文档正文里的约定 / 截止日期会被确定性地答成首个日期或存疑。正文日期 BD（时间锚点子痕迹，`Memory(body_date=True)` + `real_v2.answer_time_q`）已实现为可选开关，**默认关**：dev 未过 `PREREG_body_date.md` §2 门槛（PerLTQA first 类 2 题由对变错），保留集 crossproj-zh-bodydate 未运行。
与 `agm/` 无代码依赖；评测时只读 import `agm/umb`、`agm/bench`、`agm/all`
的数据加载与指标函数。依赖 numpy、scipy。

| 文件 | 内容 |
|---|---|
| `THEORY.md` | 理论核：MAP-B 族（D=10000）、绑定/叠加/置换/清理、痕迹 = Σ 角色⊗填充、Random Indexing、容量理论、不变量 I1–I7、诚实边界 |
| `PREREG_v1.md` | 预注册（读数前写定）：合成基准、真实集 dev 检索、LoCoMo 时间解绑 |
| `hdc.py` | 原语与容量公式（`bind/unbind/bundle/permute/cos`、`k_max`、`err_bound`、`MARGIN_MIN`） |
| `cleanup.py` | 清理记忆（边距不足 ⇒「存疑」） |
| `ri.py` | Random Indexing（写入时增量共现计数 A，C = A·I，按 1000 维一块投影） |
| `memory.py` | 分词、规则抽角色（中英文，规则号 + 原文片段可回溯）、`Memory.write/search_many/trace/decode/query`；默认写入 L1（`chunk_long`、`n_chunks`、`rank_units`、`decode_unit`/`units()`） |
| `bm25.py` | 自写 Okapi BM25（k1=0.9 b=0.4） |
| `test_vsa.py` | 守卫 G1–G34 + `--mutate` 定点变异（46 条，全部须变红）；G25–G28 = `Memory.write` 默认 L1；G29–G34 = 正文日期 BD |
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
| `RESULTS_long.md` | L1 读数与结论（dev 合格：PerLTQA E2 .148→.333 p=.002、无倒退） |
| `PREREG_long_hold.md` | L1 新造保留集确认预注册（crossproj-zh-long；读数前提交） |
| `long_hold.py` | 新造保留集结构校验 / 冻结 / S0 vs L1 只跑一次 |
| `RESULTS_long_hold.md` | 保留集确认：E1 .910→.950（10/2 p=.039）、E2 .375→.650（22/0 p<.001）⇒ **L1 通过，VSA 默认写入 = L1** |
| `default_check.py` | `Memory.write` 默认 L1 的实现等价核对（dev 四集 + crossproj-zh-long：新默认 ≡ 已提交 L1、开关关闭 ≡ S0，逐题；非新读数） |
| `PREREG_body_date.md` | 正文日期 BD 预注册（选项 B / 锚点 B-iii / 仅长单元；新保留集 crossproj-zh-bodydate 规格；读数前提交） |
| `bd_real.py` | BD dev 读数（L1 vs BD，E1 逐位断言、E2、PerLTQA 分型逐题） |
| `bd_hold.py` | crossproj-zh-bodydate 结构校验 / 冻结 / 只跑一次入口（按 dev 门槛未运行） |
| `RESULTS_body_date.md` | BD 读数与判定：dev 不合格（first 类逐题倒退 2 题，机制 = 原 L1 靠多 TIME 干扰存疑落到证据单元）⇒ 维持 L1，默认 `body_date=False` |
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

默认写入 L1 的实现等价核对（环境变量同上；逐单元缓存写 $VSA_OUT/runs/{dev,hold}/defchk_*，不入库）：
```bash
for s in crossproj hive locomo perltqa; do python -X utf8 default_check.py --set $s; done
python -X utf8 default_check.py --hold-long $VSA_OUT/runs/hold/long_crossproj_long.json
python -X utf8 default_check.py --summary --hold-long $VSA_OUT/runs/hold/long_crossproj_long.json   # → results/default_check.*
```

只跑 dev；不跑 UMB test / PerLTQA test，不碰 KMB hold / TMD。读数与结论见 `results/`、`RESULTS_v1.md`、`RESULTS_v2.md`。
