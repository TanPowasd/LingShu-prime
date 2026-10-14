# 预注册：md_cg×TriCue 换拓展 AGM（RA）

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
