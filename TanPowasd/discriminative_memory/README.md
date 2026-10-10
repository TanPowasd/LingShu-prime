# 通用判别记忆（实验实现）

**结论：在已确认结构、同一证据包与字符预算下，按新增要求覆盖/新增成本选证据有初步收益；尚未证明通用自然语言召回与长期记忆优于 AGM、BM25 或 RRF3。**

本实现把原文、解释和修订分开存储，按实体、属性、角色、条件及双时间查询，并在预算内交付完整依据。
重复变更、旧事实纠正、迟到历史、撤回/恢复、计划与实际状态、条件依赖和冲突都有显式处理。
实体/字段由调用方提供，支持任意 JSON 值；没有针对某篇小说、人物或搬家文字的专用抽取规则。

自然语言事实抽取、指代解析和问题绑定尚未实现。`append_raw` / `search_raw` 只保存与查找原文，返回 `evidence_only`。

## 实测与边界

150 个随机 schema 任务，1024 字符预算下的加权证据要求覆盖率：

| 方法 | 覆盖率 | 全要求满足 |
|---|---:|---:|
| 判别记忆 | 91.4% | 85/150 |
| BM25 证据包 | 85.4% | 68/150 |
| AGM 证据包 | 82.2% | 61/150 |
| RRF 三路证据包 | 84.1% | 66/150 |
| SQL 直接取证 | 75.4% | 39/150 |

这张表只比较结构化证据选择。所有方法共享确认结构与已绑定问题；AGM/RRF 是证据包排序对照，SQL 是直接装包对照。
它不是官方 Hive 端到端成绩，也不是自然语言理解的优劣结论。

原实验另有 800/800 时间 oracle 检查、60 次 schema 重命名与 150 次重复记录检查。
39 个小实例中 38 个达到穷举覆盖上界，另一个为 50% 对 75%，选择器不保证全局最优。
Hive 原文接口检查为 303 块、184 次查询，仅验证原文、预算与无隐式事实写入。
此前工作区合计 177 项测试通过；这里附带本算法的 48 项测试。

下一步应独立评估通用文本解释与问题绑定，区分解释错误和选择错误，再在现实输入上比较完整流程。

## 使用与复跑

Python 3.10+；核心仅使用标准库。基准和测试中的 AGM/RRF 对照引用相邻 `../agm/bench/hive_retrieval.py`，需要 PyYAML。
在本目录执行：

```sh
python -m pip install -r requirements-bench.txt
python -B -X utf8 demo_discriminative.py
python -B -X utf8 verify_discriminative.py
python -B -X utf8 bench_discriminative.py --output outputs/offline
```

可选 Hive 原文检查使用已存在的本地仓库：

```sh
python -B -X utf8 bench_discriminative.py --output outputs/with-hive --hive-root /path/to/hive-memory-bench
```

上述程序不调用模型、不需要 key，验证与基准主动禁用网络。完整模型评测须事先获得用户授权。
新输出存入 `outputs/`，历史结果存入 `results/original-20261010/`。

| 文件 | 内容 |
|---|---|
| [discriminative_memory.py](discriminative_memory.py) | SQLite 日志、证据编译、预算选择、原文回退 |
| [temporal_facts.py](temporal_facts.py) | 从先前实验原样复用的双时间状态底层 |
| [demo_discriminative.py](demo_discriminative.py) | 通用接口、反复变更、历史纠正与条件依赖示例 |
| [test_discriminative_memory.py](test_discriminative_memory.py) | 48 项行为测试 |
| [bench_discriminative.py](bench_discriminative.py) | 固定合成选择、时间 oracle 与可选 Hive 原文检查 |
| [verify_discriminative.py](verify_discriminative.py) | 离线测试、历史/发布哈希、抽样复建与结果核对 |
| [IMPLEMENTATION_AND_RESULTS.md](IMPLEMENTATION_AND_RESULTS.md) | 完整结论、接口、读数与限制 |
| [DESIGN.md](DESIGN.md) | 原始设计；包含尚未实现的目标 |
| [results/original-20261010](results/original-20261010) | 原始结果与冻结输入；历史路径仅用于追溯 |
| [publication_manifest.json](publication_manifest.json) | 发布文件及原始实验摘要 |
| [publication_verification.json](publication_verification.json) | 仓库布局下的发布验证结果 |

本目录遵循 [TanPowasd 目录授权声明](../LICENSE) 与 [仓库全局授权声明](../../LICENSE)。
