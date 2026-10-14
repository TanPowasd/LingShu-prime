# 预注册：把所有用 AGM 的算法换成拓展 AGM（RA，R2）

日期 2026-10-15，读数前提交。用户「将原来用 agm 的算法替换为拓展 agm，再测试一下两个测试集」。

## 替换对象（零模型、本仓内）
| 算法 | AGM 在哪 | 替换方式 |
|---|---|---|
| 旧AGM | bench/hive_retrieval.AGM.rank | role.old_agm_rank（同图同常数，加 R2 闸门） |
| TriCue v3 | RRF 里的 rank_agm 一路 | role.attach（rank_agm → role.rank relay=False） |
| Lex | rank_agm 管线 | role.attach |
md_cg×TriCue 在 dsh-memory 仓内，不在本轮（存疑，需要单独 PR）。

## 配置
R2 原样（PREREG_role.md 采纳版），不调任何参数；只跑 test 一次，没有 dev 选型。
LME test 317 题（md5%3≠0，三个分片），LoCoMo test 1301 题。LoCoMo 没有助手角色，按守卫 Z1/Z5/Z6 应逐题相同，用来核对。

## 判定（每个算法各自独立）
- 采纳 X+RA：LME test r@10 符号检验显著不差且 LoCoMo 不变；显著更好（p<.05）才称「提升」。
- 显著更差：不替换该算法，原 AGM 保留。

## 守卫
test_role.py 新增 Z5（attach 后无助手≡v3）、Z6（旧AGM 无角色≡原式）。

## 复跑
`PYTHONUTF8=1 python -X utf8 bench_swap.py lme --data partK.json --out swap_lme_K.json`（K=0,1,2）；`bench_swap.py locomo --out swap_loc.json`
