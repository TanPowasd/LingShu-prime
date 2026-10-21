# VSA 长单元分块 L1 · 新造保留集 crossproj-zh-long 确认（按 PREREG_long_hold v0.1）

日期：2026-10-21。零 LLM、零 API key（数据生成与读数都是 0 次 LLM 调用）、确定性（空间种子 `vsa-v1`，PYTHONHASHSEED=0）。SPDX: LicenseRef-TanPowasd-Proprietary
提交顺序：预注册（c736e17）→ 生成器 + 结构校验 + 冻结 sha256 + 读数脚本（ffed629，读数前）→ 只跑一次 → 本文件。
原始汇总：`results/long_hold.json/.md`；逐题缓存 `$VSA_OUT/runs/hold/long_crossproj_long.json`（不入库）。

## 数据
`datasets/crossproj-zh-long/release/crossproj_zh_long_hold.json`，sha256 `db2c6ffdd9cc20e596f0f93f9e7f11dad5ab505e5d8a03694f3266c1528ff22f`（运行时硬核对一致）。
零 LLM 模板生成（`gen.py`，种子 20261021，重跑同哈希）；44 场 646 轮，长单元 92 个（全为粘贴的长文档，项数 224–335），200 题（检索 120 + 时间 80）。详见 `DATACARD.md`。
冻结前唯一的修订：首版长单元只有 25 < 60，按 §1 只加长文档（14–18 → 22–28 条）并把填充事实占比 1/3 → 1/6，未看任何算法输出。

## 守卫
读数前后 `test_vsa.py` G1–G24 全绿；`--mutate` 31/31 变红。运行时断言：sha256 一致、L1 任何痕迹 ≤ K_MAX（最大 221）、E2 题集 = 80 道时间题、只跑一次（结果 / 缓存已存在即拒跑）。

## 读数（S0 vs L1，只跑一次）

| 读数 | 题数 | S0 | L1 | L1 胜/负 | p | 结论 |
|---|---:|---:|---:|---|---:|---|
| E1 r@10（score.py evidence_groups） | 200 | 0.9100 | **0.9500** | 10/2 | .039 | 显著上升 |
| E2 时间解绑（te10 候选，canon_zh 相等） | 80 | 0.3750 | **0.6500** | 22/0 | 4.8e−7 | 显著上升 |

E3（描述性）：S0 拒写 92（每个长单元都拒写）、S0 最大项数 335；L1 长单元 92 → 184 块（每篇恰 2 块），痕迹共 738，最大项数 221，拒写 0。

E2 按题型（描述性，读数后，不入判定）：
| 类型 | 题数 | S0 对 | L1 对 | 备注 |
|---|---:|---:|---:|---|
| (a) 短轮事件日期 | 30 | 30 | 30 | 短单元，两臂逐题相同 |
| (b) 长文档抬头日期 | 30 | 0 | 22 | S0：证据单元拒写，30 题全部答「存疑」（推断：其余候选也无可解 TIME，且候选第一多为该长单元，SESSION 回退同样拒写） |
| (c) 长文档正文日期 | 20 | 0 | 0 | 两臂都错：v2 规则每单元只取最先出现的日期（抬头），正文日期不入痕迹（预注册时已预期） |
te10 候选命中证据 79/80。

E1 胜负分布（描述性，读数后）：胜 10 = fact_long 7、update_latest 2、time_docdate 1；负 2 = fact_long 1、time_docdate 1；短轮题全部平局。
推断：长单元在 L1 下由两块各自打分、按最好的一块排序，比 S0「整篇一个向量」更容易让局部事实浮上前 10；与 PerLTQA dev 的 E1 打平（9/9）不同，可能因为本集长文档更长、条目之间话题更杂（存疑）。

## 判定（§4，读数前写死）
ΔE1 = +0.040 ≥ 0、ΔE2 = +0.275 ≥ 0 ⇒ 不降 ✓；E1、E2 都显著上升 ✓ ⇒ **L1 通过** ⇒ 按规则，VSA 默认写入改为 L1（`README.md`、`RESULTS_long.md` 已同步更新）。

## 独立性边界与诚实结论
- 这是在**独立性有限**的保留集上的确认：生成器与 crossproj-zh 同源（存疑）——同一设计范式、同一格式与评分器，而且模板出自实现 L1 的同一方，编写者知道 L1 的机制。
  「纪要抬头写日期」是常见惯例，但 (b) 类题正好落在 L1 机制能救的位置；E2 的提升几乎全部来自 (b)（22/0），可能偏向 L1（存疑）。
- 本集比真实对话更「长」：92 个长文档全部超 K_MAX，而 LoCoMo / hive / crossproj-zh 这类短轮语料里 L1 ≡ S0（dev 已证逐题全等）。所以 L1 改成默认，在短轮语料上不改变任何结果，只在有长单元时起作用。
- 局限：(c) 类（长文档正文里的日期）两臂都 0/20——L1 解决的是「拒写」，不是「每单元只有一个 TIME」；那是 v2 时间规则的边界，另需方案（needs-owner-decision）。
- 模板中文规整、语义组合有不自然处，绝对分数（E1 .91/.95）不可与 crossproj-zh 或真实集横比。
- 默认写入改为 L1 只改了文档口径；`memory.Memory.write` 仍是逐单元写入（超 K_MAX 抛 CapacityError），L1 路径在 `seg.segment_long`，读数脚本用 `long_real.rank_unit` 接入。是否把 L1 并入 `Memory.write` 的默认代码路径另行决定（推断：需要新守卫，不在本次范围）。

## 复跑
```bash
cd <仓根>/TanPowasd/datasets/crossproj-zh-long && python3 gen.py && sha256sum release/crossproj_zh_long_hold.json   # 应为 db2c6ffd…f22f
cd <仓根>/TanPowasd/vsa
python -X utf8 test_vsa.py && python -X utf8 test_vsa.py --mutate      # G1–G24 全绿；31/31 变红
python -X utf8 long_hold.py --check                                    # 结构校验（长单元 92，无错误）
python -X utf8 long_hold.py --run      # 只跑一次：已有 results/long_hold.json 或 $VSA_OUT/runs/hold/long_crossproj_long.json 即拒跑；复核需先移走二者（约 1 分钟）
```
