# 编年（Chronicle）：版本链记忆算法

这是一个独立的通用版本链核心，用于反复修改、撤回、恢复、冲突和按时间查询的记忆。
它把记忆从“相似文本排名”改成“不可变事件链 + 查询路由”。核心不包含人物、地点、小说或测试集字段。

每条事件保存主体、属性、操作、旧值、新值、生效时间、记录时间、原因和原文证据。相同值再次出现仍是新的事件。
每个主体—属性维护有序时间链；查询先按类型路由，再进行硬时间过滤：

- `current/state/at`：取查询时点之前最后一个事件，并区分 `active`、`retired`、`unresolved`、`absent`。
- `history`：返回截至时点的全部版本事件。
- `chain`：返回完整变更链，包含 `from/to`、原因和证据。
- `reason`：按具体事件时间定位变更原因。

实体和属性别名通过显式别名表解析，无法确认的自然语言可以留在原文回退层，不会自动成为事实。
文本抽取器应作为上游适配器注入；本目录不针对某一语料添加句式规则。

## 新版 chain 测试集控制

`bench_chain.py` 读取本地 `hive-memory-bench/chain` 的生成器事件日志，作为**结构化控制**重放 63 条主链、901 个事件和 642 道题。
这项测试验证版本索引、区间定位、四态和查询路由，不把答案键当作自然语言抽取成绩。

在仓库外执行：

```powershell
& 'E:/DF/liyang-hive-eval/.venv/Scripts/python.exe' -B -X utf8 `
  'E:/DF/liyang-hive-eval/LingShu-prime/TanPowasd/chronicle/bench_chain.py' `
  'E:/DF/liyang-hive-eval/hive-memory-bench' `
  --out 'E:/DF/liyang-hive-eval/runs/version-chain-426a86a'
```

核心测试：

```powershell
& 'E:/DF/liyang-hive-eval/.venv/Scripts/python.exe' -B -X utf8 -m unittest `
  discover -s 'E:/DF/liyang-hive-eval/LingShu-prime/TanPowasd/chronicle' `
  -p 'test_*.py'
```

两种运行均不调用模型、不访问网络、不需要 key。自然语言解释器的准确率仍需独立报告，不能用本结构化控制替代。

## 文件

- `chronicle.py`：事件日志、别名、时间区间、四态和查询路由。
- `test_chronicle.py`：重复值、迟到事件、撤回/恢复、冲突、别名和原文回退测试。
- `bench_chain.py`：新版状态链轨的零模型结构化控制。
- `results/chain_control_426a86a.json`：已保存的 642/642 控制读数。
