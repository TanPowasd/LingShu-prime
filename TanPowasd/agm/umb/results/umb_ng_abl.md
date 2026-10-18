# ng 外部臂消融（描述性，只 dev）

> 对象：lingshu-ng `2521f7f`（`results/umb_ng.md` 同一克隆、同一接入口径：零模型、钉钟、每会话/每题一库）。只读调用：构造后经 ng 公开配置口改单项默认
> ——词级通路 `MemoryEngine.set_lexical(**覆盖)`（compat 层 `set_lexical_config` 委托此方法），中文联想 `retriever.assoc = dataclasses.replace(…)`（ng `assoc.py` 文件头登记的配置入口）；不改 ng 代码。
> 变体表 `ng_arm.VARIANTS`，臂名 `ngv_<变体>`（只记忆集，run_umb 断言）。机读：`results/umb_ng_abl.json`。p = 配对符号检验（双侧，平局剔除）。

## 读数（r@10；hive 为 8000 字预算证据完整率，ng 取 k=50）

| 变体 | 改动 | LoCoMo（257） | hive（46） | LME（236） |
|---|---|---:|---:|---:|
| te | （基线） | .613 | .427 | .790 |
| ng | ng 默认 | .675 | .487 | .740 |
| ctx0 | 英文写入序上下文聚合关（ctx_beta .8→0） | **.580**（vs ng 13/38 p=6e-4） | .487 = | **.718**（22/26 p=.67） |
| fill10 | 前 10 名零分邻居也纳入聚合（非默认，ctx_fill 0→10） | .666（1/4） | .487 = | .734（3/5） |
| co0 | C1 词元共现扩散关（co_w .3→0） | .660（3/7 p=.34） | .487 = | **.778**（27/9 p=.004） |
| hd0 | H2 头部精排关（hd_n 10→0） | .675 = | .487 = | .740 = |
| div0 | R2 长块相邻写入惩罚关（diversify→False） | .675 = | .487 = | .755（10/5 p=.30） |
| lexbase | ctx0+co0+hd0+div0（裸 BM25+SDM） | .574（12/39 p=2e-4） | .487 = | .759（31/19 p=.12） |
| anc0 | 中文 AX1 锚定局部展开关（anchor_span 6→0） | .675 = | **.455**（0/4 p=.12） | — |
| lc0 | 中文 LC 长预算邻接补全关（lc_beta .5→0） | .675 = | .481（8/12 p=.5） | — |
| ax0 | 中文联想整体关（assoc.enabled→False） | .675 = | **.424**（8/17 p=.11） | — |
| both0 | ctx0 + anc0 | .580 | .455 | .718 |

「=」表示与 ng 逐题相同（该通路在此集上不经过：英文问句走词级通路 Q10，不进中文联想；中文问句不进词级通路）。LME 未跑 anc0/lc0/ax0（英文问句不经过中文联想，LoCoMo 上已实测逐位相同）。

## 归因（推断，dev 描述性，样本小处注明）
1. **LoCoMo**：ng 对 TE 的 +.062 全部来自写入序上下文聚合——关掉后 .580，反而低于 TE .613（ng 自身的裸词级打分不如 TE）。共现扩散贡献约 +.015（不显著），其余项为零。
2. **hive**：ng 对 TE 的 +.060 来自中文联想通路：锚定局部展开约 +.032、长预算邻接补全约 +.006，二者合关（ax0）回到 .424 ≈ TE。两者都是写入序邻接（锚块之后 6 个块加分 / 种子邻块补全）。46 题，均不显著。
3. **LME**：上下文聚合对 ng 也是正的（+.022，不显著）；ng 输 TE 的主要来源是 **C1 共现扩散**（关掉 +.038，27/9 p=.004，关后 .778 与 TE 无显著差异 17/26 p=.22），R2 相邻惩罚次之（+.015，不显著）。
   ——这一点与 umb_ng.md §3.2 的推断（「LME 上 ng 的词级通路不如 TE 扩散」）不同：输在共现扩散这一附加项，而非邻接聚合。
4. 零分邻居补位（fill10）在三集上都不增益 ⇒ 聚合只在已打分集合内即可（NC 据此不拉入零分块）。

## 复跑
```bash
export UMB_NG=<lingshu-ng 克隆根>   # HEAD 2521f7f；其余 UMB_* 同 te_run.sh
cd <仓根>/TanPowasd/agm/umb
V=ngv_ctx0,ngv_fill10,ngv_co0,ngv_hd0,ngv_div0,ngv_lexbase,ngv_anc0,ngv_lc0,ngv_ax0,ngv_both0
python -X utf8 run_umb.py --arms $V --split dev --sets locomo,hive --no-summary
python -X utf8 run_umb.py --arms ngv_ctx0,ngv_fill10,ngv_co0,ngv_hd0,ngv_div0,ngv_lexbase,ngv_both0 --split dev --sets lme --no-summary
python -X utf8 ng_abl.py            # → results/umb_ng_abl.json + 表
```
