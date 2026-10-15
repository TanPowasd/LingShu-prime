# hive 主轮 92 题：QMD + 统一系统提示词 · dsh-bounty#466 修复后干净重跑（2026-10-15）

## 为什么重跑
dsh-bounty#466（审计，已结算）指出：`bench/hive_official.py` 的作答产物目录只按臂名分、存在即静默 skip（F1），
`hx.py` 追问缓存没有 `_sys` 隔离（F2），截断/空源图被当完整图用（F3）。本次先修代码（见同一提交），
再在**全新克隆**的基准树上重跑 QMD+SYS 臂，确认读数不是复用来的。

## 修了什么（原型侧）
| 位置 | 改动 |
|---|---|
| `bench/hive_official.py` · `Manifest` / `cmd_gen` / `cmd_judge` | 产物目录写 `_identity.json`（臂、tag、模型、LLM_SYS、LLM_SYS_GRAPH、系统提示词 sha、基准 commit；逐题输入 sha）；目录已有结果而清单缺失/身份不同/逐题输入指纹不同 ⇒ `IdentityMismatch` 退出码 2、发调用前全量核对、0 调用；缺省目录 `out_<臂>` 在 LLM_SYS=1 时为 `out_<臂>_sys`；有失败题 ⇒ 退出码 1 |
| `confluence/hx.py` · `cache_dir` | 追问缓存 `cache_h` + `_sys` 后缀（F2） |
| `confluence/extract.py` · `CACHE` | LoCoMo 源图缓存与 `hive_extract.py` 同一规则（LLM_SYS=1 且 LLM_SYS_GRAPH≠0 ⇒ `cache_sys/`） |
| `confluence/hive_extract.py` · `load_full`、`hive_qmd.py`/`hive_mdllm.py` · `build` | 源图覆盖率 <1 ⇒ `PartialGraph`（F3） |
| `confluence/bench_dev.py` · `load_triples` | 源图缓存里一条三元组都没有 ⇒ `RuntimeError` |
| `confluence/hive_qmd.py` / `hive_hop.py` · `contexts` | 题面扩展 / 追问缓存缺题 ⇒ `RuntimeError`（不静默退回多维 / 单跳） |
| `confluence/test_fix466.py` | 守卫 G1–G14 + 定点变异 M1–M11 |

守卫读数（本机）：`python -X utf8 TanPowasd/agm/confluence/test_fix466.py` → 通过 14 / 失败 0；`--mutate` → 变异 11 条，未恰好点红 0 条。

#466 原始复现在修复后的表现（零调用）：对修复前留下的 `<bench>/sut/out_QMD`（92 个答案、无清单）跑
`LLM_SYS=1 LLM_SYS_GRAPH=0 python -X utf8 TanPowasd/agm/bench/hive_official.py gen <bench> --arm QMD --tag QMD --limit 2`
⇒ 标准错误「已有 2 个结果但没有身份清单（修复前产物）」、退出码 2、0 次调用、目录无写入。

## 重跑口径
- 基准：`FuRongJun-1999/hive-memory-bench` @ `f4509d7282f82982af5de9c8fe71863fc95b38cb`（#85 运行当时的版本；#466 附注 A：现行 main 的判分链已改，必须钉版本），**全新克隆**，无 `sut/`、`semantic/`、`real_*`。
- 臂：QMD（冻结配置，`PREREG_qmd.md`）+ `LLM_SYS=1`、`LLM_SYS_GRAPH=0`（源图沿用不带系统提示词的 `cache_hive/`，覆盖率 1.0；题面扩展用 `cache_q_sys/hive`，92/92，该缓存的 `_sys` 隔离 #466 已复核为真实存在）。QMD 臂不经过 `hx.py`。
- 模型：`cline-pass/deepseek-v4.1-flash`（作答与判官同一），temperature 0；判官 `system=False`（清单 `"system": false`）。
- 作答清单身份：`answers/_identity.json`；判官清单：`judge/_identity.json`。

```
B=<hive-memory-bench@f4509d7 的全新克隆>
LLM_SYS=1 LLM_SYS_GRAPH=0 python -X utf8 TanPowasd/agm/bench/hive_official.py gen $B --arm QMD          # → $B/sut/out_QMD_sys
cd $B && python -X utf8 score_sut.py build out_QMD_sys real_QMD_sys
python -X utf8 semantic.py prepare real_QMD_sys --select semantic                                   # 65 条判官请求
LLM_SYS=1 LLM_SYS_GRAPH=0 python -X utf8 <LingShu-prime>/TanPowasd/agm/bench/hive_official.py judge $B real_QMD_sys
python -X utf8 semantic.py finalize real_QMD_sys
python -X utf8 三分数.py real_QMD_sys --json s3_QMD_SYS_rerun.json
```

## 读数（主轮 92 题，同一量具 f4509d7）
| 臂 | 覆盖率均 | 中位 | 达标≥.7 | 编造 | 保真 |
|---|---:|---:|---:|---:|---:|
| 直读（全文上界） | .603 | .600 | 35 | 0 | 1.000 |
| **QMD+SYS 重跑（本次）** | **.572** | **.600** | **30** | **0** | **1.000** |
| QMD+SYS 原读数（#85，2026-10-12） | .561 | .5835 | 31 | 0 | .996 |
| QMD | .520 | .500 | 20 | 0 | .996 |
| 旧 AGM | .514 | .5335 | 25 | 1 | .996 |
| BM25 | .482 | .400 | 20 | 1 | .996 |
| TriCue v3 | .472 | .500 | 15 | 1 | .996 |

逐题配对（重跑对各臂，胜/负/平，双侧符号检验；对照臂用已发布的逐题分数 `TanPowasd/agm/tricue/results/hive_keyed_v3_20261011/三分数/s3_*.json`）：

| 对 | 胜/负/平 | p |
|---|---|---:|
| QMD+SYS 原读数 | 15/15/62 | 1.0 |
| TriCue v3 | 44/9/39 | 1.2e-06 |
| BM25 | 43/17/32 | .0011 |
| QMD | 32/21/39 | .169 |
| 旧 AGM | 34/19/39 | .053 |
| 直读 | 27/34/31 | .443 |

**结论**：#466 修复后干净重跑，.561 → .572（达标 31 → 30，编造 0 → 0）。与原读数逐题 15 胜 15 负 62 平（p=1.0），差异属阅读器/判官的运行间波动（推断：上下文逐题由同一缓存与同一冻结代码确定，`port_equiv.py` 复核排序可重现；作答与判词在 temperature 0 下仍不逐字可复现，见 `port_equiv_llm.json` 里判官 3/3 JSON 不逐字相同）。对 TriCue v3、BM25 显著胜出的结论不变；对 QMD（不带系统提示词）的优势仍不显著（p=.169，原 .085）；对直读仍落后、不显著。

## 调用数（本次）
作答：第一段进程被沙箱中断前落盘 62 题（另有至多 8 个在途调用随中断丢失，**存疑**，按上限计），续跑 30 题，0 失败；判官 65，0 失败；网关连通性探针 1；移植版等价性实调 7（另一段超时被杀的同脚本运行至多 7，存疑）。合计 165 ～ 180 次。key：主账号（网关注入）。

## 移植版等价性（dsh-memory md_cg/qmd.py、md_cg/qmd_llm.py）
- `port_equiv_zerokey_sys.json` / `port_equiv_zerokey_plain.json`：同进程、同缓存，92 题 QMD / 多维 v3×3 / v3 完整排序与 8000 字上下文**逐位相同**（差异 0）。
- `port_equiv_llm.json`：92 条作答 + 65 条判官请求，两边发出的 messages 157/157 逐字相同；判官请求无 system；题面扩展与源图提示词逐字相同；作答提示词 sha 与本次重跑清单 92/92 一致。带 key 实调 7 次：作答 3/3 可解析且字段集合与重跑答卷相同；判官 3/3 可解析、字段相同、JSON 不逐字相同；题面扩展 1 批 10 题 0 缺失，实体集合与 `cache_q_sys` 的平均 Jaccard .492。
