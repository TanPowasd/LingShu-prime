标题：交付：状态链轨 v0.2 记忆算法 RRF3 v1.1 + ChronicleDM（625 题 现值 0.979 / 历史 0.927 / 变更链 0.982 / 滞后 0.021，校准门四条全过，零 key 可复算）

---

## 这是什么

交付一套在 `FuRongJun-1999/hive-memory-bench` 状态链轨 v0.2（`426a86a`）上评测的记忆算法：

> **RRF3 v1.1 召回 → LLM 抽取槽位事件 → ChronicleDM 编年判别记忆 → 官方读者提示作答**

用基准自带的 `chain/tools/probe_judge.py` 机械判分（零 LLM 判官）。本仓目前没有对应的 `bounty` 任务 issue，因此按 #1、#3 的 issue 交付形式提交，请维护者裁定。如果另有正式任务 issue，请告诉我，我会并过去，改走 `/claim` → `/deliver`。

完整说明（系统组成、全部读数、caveats、带 key 重跑步骤）：
https://github.com/TanPowasd/LingShu-prime/blob/main/TanPowasd/proposals/issue_draft_chain_chronicle_dm.md

---

## 一、结论速览（全量 625 题，官方判分器，与《报告_首轮_v1》同口径）

| 臂 | 现值 | 历史 | 变更链 | 滞后混淆↓ | 四态 | 逐字回源 | 缘由随账 |
|:--|--:|--:|--:|--:|--:|--:|--:|
| **本交付** | **0.979** | **0.927** | **0.982** | **0.021** | **0.980** | 0.866 | **1.000** |
| 朴素 BM25（首轮） | 0.660 | 0.808 | 0.964 | 0.277 | 0.741 | 0.906 | 0.968 |
| 灵枢（首轮） | 0.489 | 0.780 | 0.643 | 0.298 | 0.822 | 0.176 | 0.921 |
| 版本盲对照（同模型） | 1.000 | 0.000 | 0.000 | 0.000 | 0.508 | 0.000 | 0.000 |
| 闭卷对照（同模型） | 0.000 | 0.000 | 0.000 | 0.000 | 0.061 | 0.000 | 0.000 |

- 测试集 419 题（预注册 A1、B1 为开发集）：现值 1.000、历史 0.908、变更链 1.000、四态 0.985、滞后 0.000。
- 校准门：① 版本盲指纹 ② 闭卷门 ③ 链长单调 ④ 读数自洽，四条全部通过。其中 ③ 是按官方相邻桶 5 个百分点的容差判定的（短/中/长 0.946 / 0.941 / 0.966）。
- 模型：`cline-pass/deepseek-v4.1-flash`，temperature=0。主臂约 1,214 次逻辑调用，接口报告的花费约 3.62 美元。

## 二、怎么复跑（证据块）

零 key、不联网、不调用模型，几分钟内跑完：

```bash
git clone https://github.com/TanPowasd/LingShu-prime.git
cd LingShu-prime && git checkout bb47b34
cd TanPowasd/chronicle_dm/results
python -B hive-chain-keyed-20261011/verify_offline.py
# 预期 "verified": true, "questions": 642, "scored_all": 625, "scored_test": 419, "network_attempts": 0, "model_calls": 0
python -B hive-chain-controls-20261011/summarize_controls.py
# 预期 "criteria": {"c1": true, "c2": true, "c3": true, "c4": true}, "passed": true
```

单元测试：`python TanPowasd/chronicle_dm/test_chronicle_dm.py`（9 项）、`pytest -q TanPowasd/agm/rrf3/test_rrf3.py`（8 项）。

产物：`TanPowasd/chronicle_dm/results/hive-chain-keyed-20261011/`（642 份答卷、实际读者材料、逐题抽取事件、源码与判分器快照、SHA-256 清单）和 `hive-chain-controls-20261011/`（对照臂答卷与校准判据）。

## 三、边界与未确认项

1. 增益不能单独归给 ChronicleDM：召回从 RRF3 v1.0 换到 v1.1（金标段召回 351 → 406/411）是打破现值天花板的主要一步。
2. 版本盲和闭卷是基准规定的读者对照，不是 ChronicleDM 内部的结构消融；闭卷提示会引导模型弃答，低分不能单独排除预训练污染。
3. 历史题扣分：测试集 11 道里有 10 道把状态正确判为 unresolved，但把两个候选值写进了同一个 value，官方分数没有因此改动。
4. 题目是公开的模板合成题；抽取提示是在看过题型后写的（没有按题改写）。自由对话下的泛化、跨会话持续写入都没有测。

## 四、最小性与副作用

- 没有修改 `hive-memory-bench`、`dsh-memory` 或本仓的任何文件。全部代码和证据都在 `TanPowasd/LingShu-prime` 的 `TanPowasd/` 目录下。
- 包内没有任何 key；完整请求提示和原始响应只留在本地。
- 不涉资金。代码许可见 LingShu-prime 根目录 LICENSE（需授权声明）；包内的基准数据保留 CC BY 4.0，判分器保留 MIT。
