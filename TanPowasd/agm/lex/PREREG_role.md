# 预注册：RA 发言角色感知扩散（AGM 改进）

日期 2026-10-15，读数前提交。用户「改进实施」。

## 动机（探索所得，非 test）
- AGM-PPR（PREREG_ppr.md）显示：LME 上 AGM 的损失来自扩散段，LoCoMo 上 AGM 的收益也来自扩散段。
- LME dev 前 30 题取证：前 10 轮里助手轮占比 Lex 单独 36% → AGM 45%；LME 漏检金标轮 91/91 是用户轮。
- 推断：在「用户—助手」记忆里，助手回复是对用户事实的复述/建议，扩散把它们推上来会挤掉用户轮；LoCoMo 两人对话无此问题。

## 方法（role.py；与 rank_agm 同式，只加角色过滤）
- R1：非种子助手块不进激活段（仍可中继激活）。
- R2：边进入非种子助手块的激活直接丢弃（不排前、不中继）。
无助手角色的记忆（LoCoMo、hive）与 rank_agm 逐位相同，所以本轮只可能改变 LME。

## 判定
- dev：最好的 R 臂宏平均 ≥ .714（等价于 LME dev ≥ .773，LoCoMo 不变）才进 test；两臂都过取宏平均高者，同分取 R1。
- test 只跑一次：LME test vs Lex 管线符号检验显著更好（p<.05）；LoCoMo 与 hive 逐位相同（守卫保证，复跑核对）。否则维持 Lex。

## 守卫
test_role.py：Z1 无助手≡AGM 逐位；Z2 非种子助手块不被推前；Z3 种子保留；Z4 R2 不中继。--mutate：M1 去掉角色过滤、M2 relay 开关失效，均被抓出。

## 复跑
`BENCH_ARMS=role PYTHONUTF8=1 python -X utf8 bench_cc.py lme --data part{0,1,2}.json --split dev --out roledev_lme_{i}.json`；`... locomo --split dev --out roledev_loc.json`

## dev 读数（2026-10-15，test 前提交）
| 臂 | LME r@10 | LoCoMo r@10 | 宏平均 | LME 胜/负 vs Lex |
|---|---:|---:|---:|---|
| Lex（AGM） | .763 | .655 | .709 | — |
| R1 | .773 | .655 | .714 | 3/0 |
| R2 | .782 | .655 | **.719** | 6/0 |
LoCoMo 两臂逐题与 Lex 相同（符合守卫 Z1）。按规则选中 R2，进 test（只跑一次）。
