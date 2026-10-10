# RRF3：AGM 记忆系统主实现（v1.0.0，2026-10-10）

近因 + 字二元组 BM25 + 静态 AGM 图扩散，三路倒数排名融合（RRF，k=60，等权）。单文件、纯标准库、零模型调用。
许可：见仓库根 LICENSE（LicenseRef-TanPowasd-Proprietary）。

## 用法
```python
from rrf3 import RRF3Memory
m = RRF3Memory()
m.add_turn("user", "……"); m.add_turn("ai", "……")
hits = m.retrieve("新问题", budget=4000)   # [Hit(id, turn, role, text)]，融合顺序
ctx  = m.context("新问题", budget=4000)    # 同一批块按时间顺序拼好
```

## 算法（参数全部固定，与测评一致）
| 部分 | 设置 |
|---|---|
| 切块 | 每轮按行累积，规范化 ≥300 字切一块 |
| 图边 | 同轮相邻 前→后 0.5 / 后→前 0.25；上一轮末块→本轮首块 0.4 / 反向 0.25 |
| 近因 | 从新到旧 |
| BM25 | 字二元组，df > 5% 跳过，长度归一 0.25+0.75·len/avg |
| AGM | BM25 前 8 为种子，扩散 2 步，非种子衰减 35%，阈值 0.05，k-WTA 80，后接 BM25 余下 |
| 融合 | 每路前 400，Σ 1/(60+rank)；按融合顺序装到预算（首块总要，装不下即停） |

## 读数（hive-memory-bench e2e，16 份对话，4041 次查询，4000 字，零 LLM）
| 方案 | 覆盖 | 窗口外 |
|---|---:|---:|
| **RRF3** | 0.1559 | **0.0522** |
| 近因+AGM | 0.1562 | 0.0416 |
| 最近窗口 | 0.1450 | 0 |
窗口外 RRF3 对近因+AGM 16/16 文件胜，bootstrap 95% CI [0.0085, 0.0122]；覆盖持平（8/8）。全部方案见 `../bench/README.md`。

## 验证
```bash
python -m pytest -q rrf3/test_rrf3.py                       # 7 个单元测试
python rrf3/verify_equiv.py <hive-memory-bench 路径>         # 与测评臂逐条对照
```
对照结果：16 个文件、4041 次查询，取块不一致 0，覆盖 0.1559（与测评臂相同）。

## 不包含
学习、赫布、固化、反射、SAM/AC 入口——测评中均无收益或为负，留在 `../bench/` 与 `../agm_*.py` 作研究原型。
