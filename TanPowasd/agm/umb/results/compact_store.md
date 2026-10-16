# 紧凑倒排（lex/compact.py）前后读数 · 2026-10-16

改动：`lex/compact.py` `CompactLexScorer`——只换块打分器存储，公式与累加顺序不变。
- 文档→词项：所有文档的词项 id 首尾相接存一条 `array('i')`，`doc_ptr` 记起点（CSR）。
- 倒排：term id → (文档号, 词频) 两条 `array('i')`；有序相邻对键压成整数 `a<<32|b`。
- 去掉每篇文档常驻的 tf/tf2 Counter 与位置表；RM3 文档词频、SDM 无序窗口位置均从 id 序列现场还原（位置按查询内文档缓存）。
- `umb/run_umb.py` 新增 `--store {compact,dict}`，默认 compact；`--store dict` 复现旧存储。

## 一致性
- 守卫 `lex/test_compact.py`：C1 英文/混合（RM3 开/关）分数逐位相同、C2 ZhMemory+RA-AGM 排序相同、C3 `tf[d]` 旧接口相同、C4 写入后 compact() 显式拒绝；`--mutate` M1 位置只取首次出现、M2 有序对键颠倒、M3 RM3 取错文档、M4 词频恒 1，4/4 被杀。
- UMB v0.1 全量（12 集，dev+test，zh 与 ra_zh 两臂）：10388 条 题×臂 记录与旧运行逐条比对（ndcg@10、r@10、r@100、mrr@10、top10）**0 差异**；bm25 臂不经此路径，未重跑。
- 已跑现有守卫：`lex/test_lex.py`、`lex/test_role.py`、`zh/test_zh.py` 全绿。

## 资源（同机，MedicalRetrieval 49,234 篇，ra_zh，前 200 题）
| 存储 | 建索引 | 每题 | 峰值 RSS |
|---|---|---|---|
| dict（旧） | 15.2 s | 0.0372 s | 1631 MB |
| compact | 15.3 s | 0.0175 s | 621 MB |

全量各集峰值 RSS（compact）：Ecom 767 MB、Video 531 MB、Medical 636 MB、Du 981 MB、MMarco 806 MB。arguana（长问句）两臂合计 271 s，旧存储 dev+test 合计约 327 s。建索引时间不变——瓶颈在分词，不在存储（推断，未单独剖析）。

## 复现
```
python -X utf8 lex/test_compact.py && python -X utf8 lex/test_compact.py --mutate
UMB_OUT=<数据目录> python -X utf8 umb/run_umb.py --arms zh,ra_zh --split all --budget-secs 1100            # compact
UMB_OUT=<数据目录> python -X utf8 umb/run_umb.py --arms zh,ra_zh --split all --budget-secs 1100 --store dict
```
