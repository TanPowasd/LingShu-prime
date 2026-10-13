# CHANGELOG rel-v1.15（gen-r13：带语义模型时说话人先验重排窗口 sp_n 20 → 40）

- 版本号：**rel-v1.15**；base sha：LingShu-prime main **3ca58e43**（= rel-v1.14）；发布树 rel-v1@3d6da8ea（= rel-v1.14 0030ce0b + rel-r13f4w：`lingshu_ng/lexical.py` 缺省 `sp_n` 20→40、`tests_ng/test_speaker_prior.py` 断言同步）。
- 相对上次推送版（Liyang/ = rel-v1.14）的增量：只改一个常数。**只在注入了 bge 语义模型（densefuse sf≠0）时生效**；无模型路径（缺省安装）逐位不变。

## 改了什么
`LexicalConfig.sp_n`：说话人先验（F4，rel-v1.11 起缺省 sp 0.5）参与重排的候选名次窗口由前 20 扩到前 40。效果只落在第 11–40 名之间的次序，因而只影响 r@25 / all@25 这类「读取 ≥25 条」的指标。设 `sp_n=20` 即逐位退回 rel-v1.14。

## 验收（PREREG_GEN_v3 修订 14 / 14a，判据在读数前提交）
关键项（事先登记）= {r@25, all@25} × {W0 cm11_hold, W1 cm11s_hold}，对推送版带模型缺省（B15+F4，sp_n 20），Holm–Bonferroni α=.05；H-CM11 = ConvoMem 未用文件 500 job / 801 题，单次运行后即暴露。

| 集 | 指标 | rel-v1.14（sp_n 20） | **rel-v1.15（sp_n 40）** | Δ [95% CI] | 胜:负 | Holm |
|---|---|---|---|---|---|---|
| W0 cm11_hold | r@25 | .9320 | **.9519** | +.020 [+.013, +.028] | 27:0 | 显著 + |
| W0 cm11_hold | all@25 | .8851 | **.9189** | +.034 [+.022, +.047] | 27:0 | 显著 + |
| W1 cm11s_hold | r@25 | .9282 | **.9407** | +.013 [+.007, +.019] | 17:0 | 显著 + |
| W1 cm11s_hold | all@25 | .8851 | **.9039** | +.019 [+.010, +.029] | 15:0 | 显著 + |

- 跟踪项（两口径 × r@5 / r@10 / hit@5 / hit@10 / all@10）：**r@5、r@10 没有提升**——W0 r@5 .8252 = .8252、r@10 .8901 → .8908（1:0，不显著）；W1 r@5 .8177、r@10 .8820 均不变（0:0）；hit@5/hit@10 两口径 0:0；无显著负。
- 对 gen-v3.2（无模型英文基线）7 项全部显著为正（这主要来自 rel-v1.5 起已有的语义融合，不是本版新增）。
- dev（已暴露集）无显著负：cm8_dev r@25 +.028（12:0）；lmelp_dev s@10 0:1（不显著）；lme_dev / loc_dev 带模型逐题不变。
- 延迟（cm8_dev 前 20 job × 1 轮）：热查询 p95 95.7 ms，对 R7 基准 71.99 ms = **1.33×**；冷首查 p95 103.92 ms，对 R7 97.49 ms = **1.07×**（门 ≤1.5×）；对 rel-v1.14 带模型缺省 1.06× / 0.90×。

## 收益在哪里看得到（照实）
- **只有读取 ≥25 条且注入了 bge 模型时才看得到收益。** 缺省 `recall(..., limit=10)`（compat_engine / engine / retrieval）只取 10 条，**缺省 limit 10 看不到任何变化**；mem0 v3 风格 top_k 20 也看不到。看得到的场景：按字数预算装满上下文的读者（如 4000/8000 字档约 25/50 条）、top_k ≥25 的调用方。
- 不写「整体更优」：本版只是 r@25 / all@25 在 H-CM11 上的提升，前 10 名不变。

## 回归门（rel-v1.15 候选树 bench_rel/q_g13.sh）
- tests_ng：**3075 passed**（wt-rel）；Liyang/ 内结果见推送记录。
- gate_rel 四段与 rel-v1.14 逐项相同（cn 只有耗时字段不同）：cn HMB cid **.6804** / 原句 .3701 / 要点 .6395 / excl .3108，链门 gold6 **.836** / mrr **.7543** / chain_cov **.994**；chainzh 同；t2r（r1test）2000 p.740 f.479 x.628 | 4000 p.907 f.792 x.856 | 8000 p.927 f.826 x.903；hmbzh dev T2 cid .6775。
- gen 无模型（tag rel115，`--np 1`）：loc_dev r@5 .6041 / r@10 **.749** / r@25 .8195，383/383 逐题名次与 rel114 相同；LME dev s@5 .988 / t@10 .9036 / t@50 .9759，83/83 逐题名次与 rel114 相同。
- 带模型 lmelp_dev / lmelps_dev（tag rel115emb，只记读数，不作门）：lmelp_dev s@5 .1909 / s@10 .2636 / t@10 .2273 / t@50 .4182，lmelps_dev s@5 .1727 / s@10 .2182 / t@10 .1909 / t@50 .3909；两集 110/110 逐题名次与研究树 wt-gen r13_dev@w40 相同（发布树 ≡ 研究树）。对 rel-v1.14 带模型缺省：lmelp_dev s@10 .2727→.2636（0 胜 1 负，不显著），其余 7 项相同。

## 没赢的地方（照实）
- r@5 / r@10 / hit@5 / hit@10 两口径无提升；缺省 limit 10 的调用方看不到收益。
- 无模型路径无任何变化（F4 只在注入语义模型时生效）。
- H-CM11 已暴露，不能再用于裁定。
- 前 10 名外的证据轮（多为用户自述轮，名次中位 28–37，25–40% 在第 50 名外）要拉进前 10 需查询改写/分解，成本高，按项目方向调整（主攻可用性/稳定性/兼容性）**gen 检索调优到此停止**。

## 推送记录
- 推送提交基于远端 **3ca58e43**（rel-v1.14），只改 Liyang/ 16 文件（本 CHANGELOG、README 版本条目、`lingshu_ng/lexical.py` 一个常数、测试 1、`bench_gen/PREREG_GEN_v3.md` 修订 14/14a、`bench_gen/v3/r13/` 判定脚本 8、`bench_rel/` 门脚本 3：q_g13.sh / cmp_rank.py / cmp_emb.py）；不含 bench_gen/out 数据与语料。Liyang 内 `pytest tests_ng`：**3074 passed, 1 skipped**；TanPowasd learn 25/25、reason 14/14 只运行通过，TanPowasd/ 未修改、无 .pyc/__pycache__ 改动。推送后的提交 sha 记于循环状态文件。
