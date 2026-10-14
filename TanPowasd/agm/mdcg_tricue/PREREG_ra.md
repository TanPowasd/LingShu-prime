# 预注册：md_cg×TriCue 换 RA-AGM

日期 2026-10-15，读数前提交。用户「可以」（同意在 dsh-memory 本地分支替换并测试后备 PR）。

## 改动（dsh-memory 本地分支 feat/tricue-ra，基于 4a74b14 = MDCG_TRICUE 补丁 rebase 到 6869a13）
- `md_cg/tricue_rerank.py`：`RA_ROLES = {"assistant"}`；`TriCueIndex(ids, texts, roles=None)`；`rank` 扩散时边指向非种子且 role∈RA_ROLES 的节点不计；`index_for` 从索引项/frontmatter 读 role。
- 依据：与 LingShu-prime agm/lex PREREG_role.md R2 同一规则（Lex/v3/旧AGM 的 LME test 已经全部显著提升）；dsh-memory 的 forgetting.py 本来就把 assistant 归为 self_generated。
- 守卫 P9（5 条）+ 定点变异 M7（去闸门）、M8（索引不收 role）；M3 期望红集合多一条 P9 前提（语义必然）。19/19 绿，8/8 变异恰好点红。

## 测试（只跑一次，不调参）
- LongMemEval-S test 317 题：每题独立库，role 按原角色写入，同一库上 RA 关/开成对（bench_lme_ra.py）。
- LoCoMo test 1300 题：bench_e2e_en.py MDCG_TRICUE=1，与 readings 里 final_on（改动前）逐题对照；按守卫应逐题相同（LoCoMo 没有 assistant 角色）。

## 判定
LME r@10 符号检验显著更好（p<.05）且 LoCoMo 逐题不变 → 采纳，备 PR；LME 不显著 → 只报读数不提 PR；显著更差 → 放弃。

## 读数（2026-10-15，只跑一次）
LME-S test 317 题，同一库 RA 关 → 开（胜/负，符号检验）：
| 指标 | 关 | 开 | 胜/负 | p |
|---|---:|---:|---:|---:|
| r@5 | .437 | .460 | 24/11 | .041 |
| **r@10（主判据）** | .695 | .712 | 19/11 | .20 |
| r@25 | .829 | .849 | 20/3 | .0005 |
| hit@10 | .823 | .842 | 10/4 | .18 |
LoCoMo 全 1531 题 × 前 100 名与改动前 final_on 逐题相同（不同 0）；test hit@10 64.92% 不变。
dsh-memory 分支 feat/tricue-ra a1564e1：test_tricue_rerank 19/19，--mutate 8/8。

## 判定
主判据 r@10 方向向好但不显著（p=.20）→ 按预注册**只报读数，不提 PR**。r@5、r@25 显著改善，不作为改判依据（事后不换判据）。
推断：md_cg 路占融合权重 1/4、且自身不经 AGM，RA 的效果被稀释；在本仓三个单路算法里 r@10 都显著。
