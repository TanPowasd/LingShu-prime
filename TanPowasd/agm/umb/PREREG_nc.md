# 预注册：NC 写入序邻域聚合（TE 最终分之上）

日期 2026-10-18 14:1x CST。在任何 NC 读数之前提交（本文件与 `agm/nc/nc.py`、`agm/nc/test_nc.py` 同一 commit；该 commit 之前没有任何 nc1/nc2/nc3 缓存）。

## 1. 来由（消融，描述性，只 dev；详见 `results/umb_ng_abl.md`）
外部臂 ng（lingshu-ng 2521f7f 零模型默认召回，`results/umb_ng.md`）在 LoCoMo / hive 上高于 TE、LME 上低于 TE。只读调用 ng、经其公开配置口
（`MemoryEngine.set_lexical`、`retriever.assoc`）逐项关掉默认通路，dev 读数（r@10）：

| 变体 | LoCoMo（257） | hive（46，k=50） |
|---|---:|---:|
| te | .613 | .427 |
| ng 默认 | .675 | .487 |
| 关英文写入序上下文聚合（ctx_beta=0） | **.580**（vs ng 13/38 p=.0006） | .487（不经过，逐位同） |
| 关 C1 共现扩散（co_w=0） | .660 | .487 |
| 前 10 名零分邻居也纳入（ctx_fill=10，非默认） | .666 | .487 |
| 关 H2 头部精排 / 关 R2 相邻惩罚 | .675 / .675（逐位同） | — |
| 关中文锚定局部展开（anchor_span=0） | .675（不经过） | .455 |
| 关中文长预算邻接补全（lc_beta=0） | .675 | .481 |
| 中文联想整体关（assoc.enabled=False） | .675 | .424 |

结论（推断，dev 描述性）：ng 在 LoCoMo 的 +.062（vs TE）全部、且多于全部来自写入序上下文聚合（关掉后 .580 < TE）；hive 的 +.060 来自中文联想通路
（锚定展开 + 邻接补全，同为写入序邻接；整体关掉后 .424 ≈ TE）。两种都是「写入序上相邻条目的分数互相加持」。LME 消融在本文件提交时尚在跑
（部分题读数见 `results/umb_ng_abl.md` 定稿），不影响下面的设计（RA 规则作为候选之一，不作为前提）。

## 2. 臂 NC 的定义（`agm/nc/nc.py`，写死）
- 底分 f(i) = TE 最终分 = Lex_i / max Lex + 1.0·a_i（`tree.rank` 同式；`nc.te_scores` 逐位复现，守卫 N1）。
- f'(i) = f(i) + β · max{ decay^(d−1) · f(j) : j ∈ dom(f)，d = |j − i|，0 < d ≤ w，grp(j) = grp(i) }，i ∈ dom(f)；按 (−f', 块号) 排序，再照常 dedup 到轮。
  形式取 ng `context_aggregate` 的同式（取最大、只在已打分集合内、距离衰减 decay^(d−1)；消融中 ctx_fill 无增益 ⇒ 不拉入零分块）。
- 块号即写入序。组 grp 只在有真实先后的记忆集给出（每轮一个组号，块继承所在轮）：
  - LoCoMo：会话号（D<k>）；LME：haystack 会话序号；hive：章节 cid（章内块按原文先后；ng 不分章，此处更保守）；
  - 复用保留集：KMB 年份段（`lmeb_extra.kmb` 的 sess），TMD 会话号（`lmeb_extra.tmd` 的 sess）。
  - 检索集（10 个 BEIR / C-MTEB）与 PerLTQA（单元彼此独立）：grp = None ⇒ NC 逐位等于 TE（守卫 N2；run_umb.py 内对「记忆集且非 PerLTQA ⇔ grp 非空」显式断言）。不加任何相邻边。
- RA 角色规则交互：TE 的激活已对非种子 assistant 块关闸（fd.activate）。候选 ra=True 时，非种子（Lex 前 SEEDS=8 名之外）的 assistant 块
  在 NC 中既不接收也不贡献邻域分；ra=False 时与其它块同等。只有 LME 有 assistant 角色，LoCoMo / hive / KMB 上 ra 不起作用（逐位相同，推断由构造保证）。

## 3. 候选（≤ 3，读数前写死）
| 臂 | β | w | decay | RA 规则 | 理由 |
|---|---:|---:|---:|---|---|
| nc1 | 0.8 | 3 | 0.6 | 否 | ng 默认原样 |
| nc2 | 0.8 | 3 | 0.6 | 是 | 同上 + 非种子 assistant 不参与（LME 上 ng 输 TE，推断与长助手轮被邻居抬升有关） |
| nc3 | 0.4 | 2 | 0.6 | 是 | 半强度窄窗（TE 激活已沿问答邻接扩散一次，防重复计数） |

## 4. 选择与采纳
1. **选臂（UMB dev 13 集：12 集 + PerLTQA dev）**：候选合格 ⇔ 13 集等权宏平均 > TE 的宏平均，且三个记忆集（lme / locomo / hive）上无显著倒退
   （dev 逐题配对符号检验 vs TE：负 > 胜 且 p < .05 即倒退）。合格者取宏平均最高；并列取 β 小、再取 w 小。无合格 ⇒ 止步：保留模块、不改默认、不发 reuse 查询。
   - 由构造，NC 在 10 个检索集与 PerLTQA 上逐位等于 TE（守卫 N2 + run_umb 断言），这 11 集的 NC 读数取 TE 既有 dev 缓存；另以 scifact dev 前 20 题实跑
     nc1 核对 top10 与 te 逐题相同（记入结果文件）。故 13 集宏平均之差 = 三个记忆集之差之和 / 13。
   - UMB test 与 PerLTQA test 已用掉，不作证据；本轮不跑。
2. **独立验证（复用保留集，PREREG_reuse.md 流程）**：选中臂对 TE 各问 1 次，指标 r@10：
   `reuse.py --set kmb --arm <NCk> --base TE --train kmb_dev.json --hold kmb_hold.json`；`reuse.py --set tmd --arm <NCk> --base TE --md5 tmd.json`。
   每题文件由 `lex/bench_cc.py`（`BENCH_ARMS=role,tree,nc`，`LEX_RM3=0`）生成；保留侧逐题结果只由 reuse.py 读取，分析者不打开、不打印。
   - 倒退 ⇔ 答案 < 0；提升 ⇔ 答案 > 0。
3. **采纳** ⇔ 选臂合格，且两个 reuse 答案都 ≥ 0、至少一个 > 0。
   - 采纳则：`tree.attach`（AGM 默认检索的 TE 挂接）在 TE 打分后接 NC（选中参数），组取记忆对象的写入序组（`m._nc_grp`，未设置 ⇒ None ⇒ 与 TE 逐位相同），
     并在 `lex/README.md` 与本文件写明；UMB 的 `te` 臂作为历史基线不改名不改义。
   - 否则：保留 `agm/nc/` 模块与 nc1–nc3 臂，不改任何默认。

## 5. 守卫
`agm/nc/test_nc.py` N1–N6；`--mutate` M1–M9（忽略组 / 取和 / 去 decay / 窗口差一 / 助手可贡献 / 助手可接收 / grp=None 不短路 / 丢激活项 / 吞无角色错）全杀。

## 6. 存疑
- ng 的聚合作用在其自身词级打分（BM25 k1 1.2 b .5 + SDM）上，NC 作用在 TE 最终分（含激活）上：同式不同底，β 的最优值不必相同（这是设 nc3 的理由）。
- hive 以章节为组比 ng（全库一条写入流）保守；章边界处的跨章邻接被切断。
- LoCoMo 上 ng 不分会话；NC 按会话切断。两者差异未单独消融。

## 7. 复跑
```bash
# 环境：te_run.sh 的 UMB_* / DIST_TABLE（另 UMB_NG 只为消融；UMB_PERLTQA 不需要——PerLTQA 上 NC ≡ TE）
cd <仓根>/TanPowasd/agm
python -X utf8 nc/test_nc.py && python -X utf8 nc/test_nc.py --mutate
cd umb
python -X utf8 run_umb.py --arms nc1,nc2,nc3 --split dev --sets lme,locomo,hive --no-summary
python -X utf8 run_umb.py --arms te,nc1 --split dev --sets scifact --limit 20 --no-summary
python -X utf8 nc_report.py          # → results/umb_nc.md / .json
```
