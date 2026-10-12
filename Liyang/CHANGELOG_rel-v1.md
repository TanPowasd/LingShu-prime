# CHANGELOG · lingshu_ng rel-v1（2026-10-12）

相对上次推送版（Liyang/ = ng@875d838 + 读路径第三阶段 neural，提交 7dbbebb）的集成升级。
发布树 = 重写仓库分支 `rel-v1`：ng@875d838 ← 合入 gen-v1（英文词级通路 gen-v3.2）、zh-v1（中文 v7.1）、chain-v1（版本链，可选）← 移植已推送版 neural（默认关）← retrieval 拆模块（行为不变）。

## 新增 / 变更
- **英文词级通路 Q10（gen-v3.2，默认开，按语料与查询自动路由）**：BM25 + SDM 邻近 + 写入序上下文聚合（`lexical.py`/`lexpath.py`）、词元共现扩展（`cooc.py`）、头部精排（`headrank.py`）。纯标准库。
- **中文联想通路 Q11（v7.1，默认开）**：锚定局部展开 + 联想扩散（`assoc.py`），可选语义重排/自适应截断（`semrank.py`，BAAI/bge-reranker-base，MIT，ONNX；需 `onnxruntime`+`tokenizers` 与模型目录 `LINGSHU_NG_SEM`）。**缺依赖或缺模型时逐位退回 v4（零模型）**；回退开关 `{"tp_head":0,"sem_n":0}`。链式问句（历次变更/演变等）只重排不截断。
- **版本链（chain，可选，默认关）**：`engine.enable_chain()` / `chain_answer()`，现值/时点历史/变更链/四态/缘由，带来源原文；零 LLM。
- **neural 第三阶段**：保持上次推送版行为（不设环境变量 = 关）。
- 结构：`retrieval.py` 拆出 `lexpath.py`，recall 交付共用 `_deliver`，满足模块 <600 行 / 函数 <60 行门禁。

## 集成核对（本发布树实跑）
- tests_ng：**2947 passed**（上次推送版 2815 passed / 1 skipped）。
- HMB 检索轨（184 问）：cid **.6804**（= 上次）、原句 .2770→**.3701**、要点 .5765→**.6395**、must_exclude .3108（=）。
- 状态链门（419 题）：gold6 .836 / mrr .7543（=），chain_cov .9763→**.994**。
- 中文 T2R2 r1test（380 题）：与冻结 v7.1 逐题相同 379/380；1 题（中英混合查询 `python3.8安装pip`）因英文路由改进走词级通路而名次不同，三档九项均值到三位小数完全相同。HMB 中文 184 问与 v7.1 逐题相同。
- 英文 dev：loc_dev 383 题、LME dev 83 题与冻结 gen-v3.2 逐题相同（LME dev s@5 .988 / t@10 .9036）。

## 证据（各线保留集，均为当时未暴露、只跑一次；现已暴露）
- 英文（对 ng@875d838）：LME test s@5 .5995→.9716、LoCoMo test 证据轮 r@10 .438→.694（配对 bootstrap，p<1e-4）。对 TriCue v3：REALTALK 694 题、ConvoMem H-CM/H-CM4/H-CM6 显著胜；LME 轮级 t@10 / s@10 / t@50 **平手（未胜）**。
- 中文（T2Ranking 人工标注判定集 T2R2 r1test，对 max(AGM, 多维v3×3 启发, TriCue v3)）：不劣 6/9；2000 证据召回 +.190、4000 全证据 +.163 显著胜；**2000/4000 误用仍输**；8000 证据低 .003。v7 对 v4 九项无一显著变差。BGE 训练含 T2Ranking 训练侧，同分布，不外推。
- 版本链（H4 保留集）：gold6 .871 vs ng .839（14胜2负，p=.004）；抽取完全正确率 .040（**预登记目标未达**）。

## 未胜 / 已知限制
- LME 轮级 t@10/s@10/t@50 对 TriCue v3 平手；中文误用（判别上限 AUC≤.74）与 HMB must_exclude 仍输；多维v3×3 LLM 源图臂未测（超预算）。
- 语义重排依赖本地模型，模型权重不随仓库发布。

## 署名
BM25（Robertson & Zaragoza）、SDM（Metzler & Croft 2005）、MMR（Carbonell & Goldstein 1998）思想自行实现；bge-reranker-base（BAAI，MIT）仅作可选外部模型调用，未复制代码或权重。对手实现（AGM / 汇流多维 / TriCue）只在本地 import 测评，未复制。
