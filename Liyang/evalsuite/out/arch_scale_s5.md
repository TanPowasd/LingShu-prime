# 灵枢 lingshu 自建测评榜（LEADERBOARD_NG）

生成时间：2026-10-09 11:49（Asia/Shanghai）· 规则：evalsuite-rules-v1（2026-10-09 固定，先于 ng 首次读数提交）

## 参评快照

| 快照 | 实现 | 来源 | 提交 | 备注 |
|---|---|---|---|---|
| base | legacy | `/workspace/work/ls/upstream` | `2bb82910ff` | 冻结于 @2bb8291（git archive） |
| integrated | legacy | `/workspace/work/ls/integrated` | `667e84ab9c` | 冻结于 @667e84a（git archive） |
| ng-prev | ng | `/workspace/work/ls/wt-scale` | `1f0a5947d5` | 冻结于 @1f0a594（git archive） |
| ng | ng | `/workspace/work/ls/wt-scale` | `b1d5b1d96c` | 冻结于 @b1d5b1d（git archive） |

## 总榜

| 排名 | 快照 | 总分 | 探针分 | 性质分 | 性能分 | 质量分 |
|---|---|---|---|---|---|---|
| 1 | ng-prev | **99.6** | 99.2 | 100.0 | 99.1 | 99.9 |
| 2 | ng | **99.3** | 99.2 | 100.0 | 97.5 | 100.0 |
| 3 | integrated | **61.2** | 64.9 | 89.3 | 13.7 | 43.0 |
| 4 | base | **31.5** | 10.7 | 59.9 | 14.4 | 47.2 |

## 总分规则（evalsuite-rules-v1（2026-10-09 固定，先于 ng 首次读数提交））

规则在跑 ng 之前固定并随本文件提交；对所有快照同一套代码、同一组探针 / 种子 / 规模，不按快照调整。

- **总分 = 0.40·探针分 + 0.30·性质分 + 0.15·性能分 + 0.15·质量分**（各维度 0–100）。正确性（前两项）占 70%。
- **探针分** = OK 数 / 探针总数 × 100。分母恒为全部探针；BUG、ERR（崩溃）、TIMEOUT、**NA（未实现/导入失败）一律计 0**——未实现不能靠缺席提分，但 NA 单列，便于区分「没做」和「做错」。
- **性质分** = 各性质 (1 − 违反率) 的平均 × 100；每条性质固定种子 0..N−1（默认 N=200）。NA/ERR/TIMEOUT 的性质计 0。
- **性能分**：每个 (规模, 操作) 格与「本次参评快照中最优者」比：得分 = (最优+ε)/(本快照+ε)，最优者 1，缺失 / 超时 0；
  格子 = {add, recall, decay_cycle, self_check, activation 的中位耗时, Python 堆峰值} × 规模；取平均 × 100。
  这是**相对分**：加入新快照会改变其他快照的性能分，但不改变排序原则；原始毫秒数另表列出。
  各快照按规模**交错**测 2 轮，每格取两轮中位数的较小者（削弱共享机器负载漂移的偏置）。
- **质量分**：7 项越低越好的 AST 指标（最大模块行数、最大函数行数、最大圈复杂度、平均圈复杂度、平均函数长度、
  每百函数中 CC>10 的个数、重复代码块率），同样按「相对最优」计分后平均 × 100。
  范围：legacy = `lingshu/core/`，ng = `lingshu_ng/`（各自的记忆引擎本体）。实现不可导入（适配层 NA）时质量记 NA、计 0，
  避免半成品靠体量小拿高分。
- **附表**（bench/probes 旧 API 直连探针、各种读数）只展示不计分。
- 修订记录：v1 首次提交（bae8544）后、ng 正式参评前，P06 往返性质改为「本地层逐项等价 + 共享层原样恢复或整条隔离」，
  与探针 i125（无密钥导入不得改写结构层）口径一致；计分公式与权重未改。

## 维度一 · 缺陷探针榜（行为探针，经 adapters 抽象接口）

探针数：**131**，覆盖上游 core 相关 issue **86** 个。OK=缺陷不复现；BUG=仍复现；NA=该实现无此能力（导入失败/未实现）；ERR=探针崩溃；TIMEOUT=超时。

| 快照 | OK | BUG | NA | ERR | TIMEOUT | 修复率 |
|---|---|---|---|---|---|---|
| base | 14 | 117 | 0 | 0 | 0 | 10.7% |
| integrated | 85 | 46 | 0 | 0 | 0 | 64.9% |
| ng-prev | 130 | 1 | 0 | 0 | 0 | 99.2% |
| ng | 130 | 1 | 0 | 0 | 0 | 99.2% |

<details><summary>逐探针读数</summary>

| 探针 | issue | 说明 | base | integrated | ng-prev | ng |
|---|---|---|---|---|---|---|
| i7-numpy-free | #7 | core 轻核承诺：屏蔽 numpy 后 activation 模块不可导入 | **BUG** 激活模块: import:activation:import of numpy halted; None in sys.modules | **BUG** 激活模块: import:activation:import of numpy halted; None in sys.modules | **OK** 无 numpy 可用 | **OK** 无 numpy 可用 |
| i16-export | #16 | export_all 对缺失表抛 OperationalError | **OK** 导出成功 | **OK** 导出成功 | **OK** 导出成功 | **OK** 导出成功 |
| i20-provenance-human-review | #20 | from_legacy 永远推不出 human_review | **BUG** 往返后 methods=['none'] | **BUG** 往返后 methods=['none'] | **OK** 往返后 methods=['human_review'] | **OK** 往返后 methods=['human_review'] |
| i29-repeat-boost | #29 | 重复写入同一错误陈述即增信到 ~1.0 | **BUG** 30 次重复后置信度=1.000（同源重复不应被当作独立佐证） | **BUG** 30 次重复后置信度=1.000（同源重复不应被当作独立佐证） | **OK** 30 次重复后置信度=0.500（同源重复不应被当作独立佐证） | **OK** 30 次重复后置信度=0.500（同源重复不应被当作独立佐证） |
| i33-self-restart | #33 | 自我模型重启即失忆 | **BUG** 重启前 values=['诚实优先'] → 重启后 ['存在优先', '信任深化', '结构完整'] | **BUG** 重启前 values=['存在优先', '信任深化', '结构完整', '诚实优先'] → 重启后 ['存在优先', '信任深化', '结构 | **OK** 重启前 values=['存在优先', '信任深化', '结构完整', '诚实优先'] → 重启后 ['存在优先', '信任深化', '结构 | **OK** 重启前 values=['存在优先', '信任深化', '结构完整', '诚实优先'] → 重启后 ['存在优先', '信任深化', '结构 |
| i33-trust-restart | #33 | 信任积累活不过一次重启 | **BUG** 重启后 t_total=0.0 | **BUG** 重启后 t_total=0.0 | **OK** 重启后 t_total=0.42 | **OK** 重启后 t_total=0.42 |
| i35-search-truncation | #35 | 检索按插入序硬截断：600 条中第 550 条不可达 | **OK** search('TOK0550') 命中目标=True，返回 1 条 | **OK** search('TOK0550') 命中目标=True，返回 1 条 | **OK** search('TOK0550') 命中目标=True，返回 10 条 | **OK** search('TOK0550') 命中目标=True，返回 10 条 |
| i36-protect-decay | #36 | 被 protect 的情境节点被衰减删除 | **BUG** 300 轮后仍存在=False | **BUG** 300 轮后仍存在=False | **OK** 300 轮后仍存在=True | **OK** 300 轮后仍存在=True |
| i36-protect-fifo | #36 | 被 protect 的情境节点被 FIFO 上限淘汰 | **BUG** FIFO 后仍存在=False | **BUG** FIFO 后仍存在=False | **OK** FIFO 后仍存在=True | **OK** FIFO 后仍存在=True |
| i37-close-thread | #37 | close() 不 join 衰减线程，后台线程访问已关闭连接 | **BUG** 线程异常=['ProgrammingError']，close 后残留线程=0 | **OK** 线程异常=[]，close 后残留线程=0 | **OK** 线程异常=[]，close 后残留线程=0 | **OK** 线程异常=[]，close 后残留线程=0 |
| i38-insight-v2 | #38 | insight_verify V2 零证据即 verified 且 import | **BUG** status=verified，importance=0.9 | **BUG** status=verified，importance=0.9 | **OK** status=pending，importance=0.7 | **OK** status=pending，importance=0.7 |
| i44-gate-links | #44 | 长期层关联边从未建成（links 恒 0） | **BUG** links=0，实际边=0 | **OK** links=2，实际边=2 | **OK** links=2，实际边=2 | **OK** links=2，实际边=2 |
| i48-novelty-window | #48 | 新奇度只看 top-80：较老的既有知识被判为新 | **BUG** 已存在内容的新奇度=1.000 | **BUG** 已存在内容的新奇度=1.000 | **OK** 已存在内容的新奇度=0.000 | **OK** 已存在内容的新奇度=0.000 |
| i51-nonascii-key | #51 | 非 ASCII 设计者密钥让终裁从『拒绝』变成抛 TypeError | **BUG** TypeError: comparing strings with non-ASCII characters is not supporte | **BUG** TypeError: comparing strings with non-ASCII characters is not supporte | **OK** 错误密钥 → PermissionError | **OK** 错误密钥 → PermissionError |
| i52-access-memory | #52 | :memory: 后端检索命中后 access_count 恒 0 | **BUG** 3 次命中后 access_count=0 | **BUG** 3 次命中后 access_count=0 | **OK** 3 次命中后 access_count=3 | **OK** 3 次命中后 access_count=3 |
| i54-consume-paused | #54 | paused 期间 consume_events 静默丢弃排队事件 | **BUG** 暂停前排队 2 → 暂停期间 consume 后 0 | **BUG** 暂停前排队 2 → 暂停期间 consume 后 0 | **OK** 暂停前排队 2 → 暂停期间 consume 后 2 | **OK** 暂停前排队 2 → 暂停期间 consume 后 2 |
| i55-world-degenerate | #55 | world_model run(0) 等退化输入崩溃 | **BUG** UnboundLocalError: cannot access local variable 'v' where it is not as | **BUG** UnboundLocalError: cannot access local variable 'v' where it is not as | **OK** status=ok | **OK** status=ok |
| i57-escalation-value | #57 | check_escalation 的数值阈值门永不求值 | **BUG** value=0.05 时命中 'value > 0.9' 升级点=True | **BUG** value=0.05 时命中 'value > 0.9' 升级点=True | **OK** value=0.05 时命中 'value > 0.9' 升级点=False | **OK** value=0.05 时命中 'value > 0.9' 升级点=False |
| i81-threads | #81 | 多线程共享连接：并发读写抛异常 | **OK** 异常={}，知识层条数=210/210 | **OK** 异常={}，知识层条数=210/210 | **OK** 异常={}，知识层条数=210/210 | **OK** 异常={}，知识层条数=210/210 |
| i82-score-saturation | #82 | search_content 分数饱和：长短文同分 | **BUG** 分数取值集合=[1.0] | **BUG** 分数取值集合=[1.0] | **OK** 分数取值集合=[0.517857, 1.0] | **OK** 分数取值集合=[0.517857, 1.0] |
| i83-provenance-gate | #83 | 显式来源被 gate/novel_prefeed 覆盖（user→fixture | **OK** 往返后 source=user | **OK** 往返后 source=user | **OK** 往返后 source=user | **OK** 往返后 source=user |
| i88-anchors-50 | #88 | get_anchors 静默截为 50 条 | **BUG** 存 60 个锚点，返回 50，缺 10 | **OK** 存 60 个锚点，返回 60，缺 0 | **OK** 存 60 个锚点，返回 60，缺 0 | **OK** 存 60 个锚点，返回 60，缺 0 |
| i88-layer-enum | #88 | get_layer_nodes 整层枚举截断（知识层 61 条） | **BUG** 知识层 61 条，整层枚举返回 50 | **OK** 知识层 61 条，整层枚举返回 61 | **OK** 知识层 61 条，整层枚举返回 61 | **OK** 知识层 61 条，整层枚举返回 61 |
| i89-radius0 | #89 | spatiotemporal_query(time_radius=0) 同刻候选 | **BUG** ZeroDivisionError | **OK** 返回 [('b', 0.0)] | **OK** 返回 [('b', 0.0)] | **OK** 返回 [('b', 0.0)] |
| i92-old-schema | #92 | 老库（缺后加列/表）打开即崩或永远补不上 | **OK** 老库可用=True | **OK** 老库可用=True | **OK** 老库可用=True | **OK** 老库可用=True |
| i93-dangling-import | #93 | import_all 原样引入孤儿边且不报 | **BUG** 孤儿边入库=True，导入回执报告悬挂=False | **OK** 孤儿边入库=True，导入回执报告悬挂=True | **OK** 孤儿边入库=False，导入回执报告悬挂=True | **OK** 孤儿边入库=False，导入回执报告悬挂=True |
| i94-consolidate-round | #94 | consolidate_cycle 演练提权第 1 轮误触发 | **BUG** 提权轮次=[1, 11]（期望首提权在第 10 次演练） | **OK** 提权轮次=[10]（期望首提权在第 10 次演练） | **OK** 提权轮次=[10]（期望首提权在第 10 次演练） | **OK** 提权轮次=[10]（期望首提权在第 10 次演练） |
| i95-activation-empty-graph | #95 | 空认知图默认 hops=2 激活抛 ValueError | **BUG** ValueError: zero-size array to reduction operation maximum which has n | **OK** 空图激活 size=0 | **OK** 空图激活 size=0 | **OK** 空图激活 size=0 |
| i107-selfcheck-blind | #107 | self_check 在全新/无自我库上仍报 self_ok=True | **BUG** 全新引擎 self_ok=True | **OK** 全新引擎 self_ok=False | **OK** 全新引擎 self_ok=False | **OK** 全新引擎 self_ok=False |
| i109-external-anchor | #109 | register_external_anchor 无密钥直写结构层 | **BUG** 外部输入落层=structure | **OK** 被拒 | **OK** 被拒 | **OK** 被拒 |
| i114-gate-unreachable | #114 | 默认 t_total=0 时全新内容快照一律 discarded / 长期层不可 | **BUG** 5 条全新快照状态=['discarded', 'discarded', 'discarded', 'discarded', 'discar | **BUG** 5 条全新快照状态=['discarded', 'discarded', 'discarded', 'discarded', 'discar | **OK** 5 条全新快照状态=['ok', 'ok', 'ok', 'ok', 'ok'] | **OK** 5 条全新快照状态=['ok', 'ok', 'ok', 'ok', 'ok'] |
| i115-conflict-edge-decay | #115 | 矛盾 OPPOSITE 边被普通衰减删除，conflict 标签残留 | **BUG** 80 轮后 opposite 边=0，conflict 标签仍在=True | **BUG** 80 轮后 opposite 边=0，conflict 标签仍在=True | **OK** 80 轮后 opposite 边=1，conflict 标签仍在=True | **OK** 80 轮后 opposite 边=1，conflict 标签仍在=True |
| i117-verify-edge-range | #117 | verify_edge 不校验置信度范围（5.0 照单写入） | **BUG** verify_edge(5.0) 后 conf=5.0 | **BUG** verify_edge(5.0) 后 conf=5.0 | **OK** verify_edge(5.0) 后 conf=1.0 | **OK** verify_edge(5.0) 后 conf=1.0 |
| i118-rejected-revive | #118 | 已否决的提案可被『复核』复活后改判通过 | **BUG** 复活改判结果=True，落层=structure | **BUG** 复活改判结果=True，落层=structure | **OK** 复活改判结果=False，落层=knowledge | **OK** 复活改判结果=False，落层=knowledge |
| i118-same-identity | #118 | 同一身份可走完提案→复核→终裁全程 | **BUG** 同人三签结果=True，落层=structure | **BUG** 同人三签结果=True，落层=structure | **OK** 同人三签结果=False，落层=knowledge | **OK** 同人三签结果=False，落层=knowledge |
| i118-standard-range | #118 | 验证标准终裁参数不做值域校验（dedup_static=5.0） | **BUG** 生效值=5.0 | **BUG** 生效值=5.0 | **OK** 生效值=0.95 | **OK** 生效值=0.95 |
| i118-unverified-adjudicate | #118 | 未复核的提案可直接终裁通过 | **OK** 结果=False，落层=knowledge | **OK** 结果=False，落层=knowledge | **OK** 结果=False，落层=knowledge | **OK** 结果=False，落层=knowledge |
| i122-history-bound | #122 | SelfModel.history 无界增长 | **BUG** 300 次 update_self 后 history 长度 300 | **OK** 300 次 update_self 后 history 长度 200 | **OK** 300 次 update_self 后 history 长度 200 | **OK** 300 次 update_self 后 history 长度 200 |
| i125-import-escalation | #125 | import_all 可关闭全部升级点 | **BUG** 启用升级点 6 → 导入后 0 | **BUG** 启用升级点 6 → 导入后 0 | **OK** 启用升级点 6 → 导入后 6 | **OK** 启用升级点 6 → 导入后 6 |
| i125-import-structure | #125 | import_all 无密钥改写结构层原文 | **BUG** 导入后结构层原文=P0: 可以自主生成目标 | **BUG** 导入后结构层原文=P0: 可以自主生成目标 | **OK** 导入后结构层原文=P0: 不得自主生成目标 | **OK** 导入后结构层原文=P0: 不得自主生成目标 |
| i126-activation-cache | #126 | 激活引擎图缓存不刷新：新增节点被丢弃 | **BUG** 新增节点在激活结果=False，seeds=0 | **OK** 新增节点在激活结果=True，seeds=1 | **OK** 新增节点在激活结果=True，seeds=1 | **OK** 新增节点在激活结果=True，seeds=1 |
| i127-primary-delete-structure | #127 | PRIMARY 以同 id 改写为知识层后可删除结构层 | **BUG** 结构层节点现状=None | **BUG** 结构层节点现状=None | **OK** 结构层节点现状=structure | **OK** 结构层节点现状=structure |
| i127-sub-demote | #127 | SUB 以同 id 写知识层节点即可把结构层节点降级并删除 | **BUG** 结构层节点现状=None | **BUG** 结构层节点现状=None | **OK** 结构层节点现状=('structure', 'P0: 不得自主生成') | **OK** 结构层节点现状=('structure', 'P0: 不得自主生成') |
| i127-sub-importance | #127 | SUB 可改写结构层节点 importance/confidence | **BUG** importance 0.8→0.30000000000000004，confidence 1.0→0.5 | **BUG** importance 0.8→0.30000000000000004，confidence 1.0→0.5 | **OK** importance 0.8→0.8，confidence 1.0→1.0 | **OK** importance 0.8→0.8，confidence 1.0→1.0 |
| i130-reflect-escalation | #130 | 反思判出需设计者后不调用升级点（check_escalation 零调用） | **BUG** check_escalation 调用次数=0 | **BUG** check_escalation 调用次数=0 | **OK** check_escalation 调用次数=1 | **OK** check_escalation 调用次数=1 |
| i130-sub-escalation | #130 | SUB 无密钥即可关闭全部升级点 | **BUG** 升级点 6 → SUB 关闭后启用 0 | **OK** 升级点 6 → SUB 关闭后启用 6 | **OK** 升级点 6 → SUB 关闭后启用 6 | **OK** 升级点 6 → SUB 关闭后启用 6 |
| i132-zero-score | #132 | 零分节点仍作为检索结果返回 / 同义扩展子串误触发 | **BUG** top1 是目标=True，零分结果=9，无关『灵枢智能体』结果=9 | **OK** top1 是目标=True，零分结果=0，无关『灵枢智能体』结果=0 | **OK** top1 是目标=True，零分结果=0，无关『灵枢智能体』结果=0 | **OK** top1 是目标=True，零分结果=0，无关『灵枢智能体』结果=0 |
| i138-cond-unasserted | #138 | 非法/带空格的条件值静默折叠为 UNASSERTED，同 cond_hash | **BUG** 非法 style 与未声明同哈希=True | **BUG** 非法 style 与未声明同哈希=True | **OK** 非法 style 与未声明同哈希=False | **OK** 非法 style 与未声明同哈希=False |
| i139-replace-nonatomic | #139 | subgraph_replace 新子树缺键时旧子树已被删（非原子） | **BUG** 失败后旧子树根仍在=False | **BUG** 失败后旧子树根仍在=False | **OK** 失败后旧子树根仍在=True | **OK** 失败后旧子树根仍在=True |
| i139-replace-parent | #139 | old_sub_root_id==parent_id 时父节点自身被删 | **BUG** 父节点仍在=False | **BUG** 父节点仍在=False | **OK** 被拒 | **OK** 被拒 |
| i139-replace-protected | #139 | subgraph_replace 级联删除受保护节点 | **BUG** 受保护叶子仍在=False | **BUG** 受保护叶子仍在=False | **OK** 被拒 | **OK** 被拒 |
| i140-content-swap | #140 | 复核后同 id 改写内容，终裁把未经复核的内容写进结构层 | **BUG** 结构层内容=所有用户输入一律可信无需校验 层=structure | **BUG** 结构层内容=所有用户输入一律可信无需校验 层=structure | **OK** 结构层内容=所有用户输入一律可信无需校验 层=knowledge | **OK** 结构层内容=所有用户输入一律可信无需校验 层=knowledge |
| i142-correction-boost | #142 | 对同一命题反复更正，原命题反而增信 | **OK** 25 次更正后原命题置信度 0.50→0.50 | **OK** 25 次更正后原命题置信度 0.50→0.50 | **OK** 25 次更正后原命题置信度 0.50→0.50 | **OK** 25 次更正后原命题置信度 0.50→0.50 |
| i142-negation | #142 | M5 去重把否定命题当重复吞掉 | **BUG** 否定句返回旧节点=True，否定句入库=False | **BUG** 否定句返回旧节点=True，否定句入库=False | **OK** 否定句返回旧节点=False，否定句入库=True | **OK** 否定句返回旧节点=False，否定句入库=True |
| i142-number | #142 | M5 去重对数值改动不敏感（2.5 毫克→7.5 毫克） | **BUG** 数值更正被合并=True | **BUG** 数值更正被合并=True | **OK** 数值更正被合并=False | **OK** 数值更正被合并=False |
| i145-cycle-branch | #145 | reason_causal 遇环的分支整条丢弃 | **OK** 返回 2 条链，含到环上节点 c 的链=True | **OK** 返回 2 条链，含到环上节点 c 的链=True | **OK** 返回 2 条链，含到环上节点 c 的链=True | **OK** 返回 2 条链，含到环上节点 c 的链=True |
| i145-dup-report | #145 | 同一个环被每个节点重复报告 | **OK** 唯一 4 环报 1 个 | **OK** 唯一 4 环报 1 个 | **OK** 唯一 4 环报 1 个 | **OK** 唯一 4 环报 1 个 |
| i145-long-chain | #145 | reason_causal 链长超过 max_depth 时返回 0 条 | **OK** 7 步链 max_depth=5 → 1 条（应返回截断链而不是全丢） | **OK** 7 步链 max_depth=5 → 1 条（应返回截断链而不是全丢） | **OK** 7 步链 max_depth=5 → 1 条（应返回截断链而不是全丢） | **OK** 7 步链 max_depth=5 → 1 条（应返回截断链而不是全丢） |
| i145-self-loop | #145 | find_cycles 漏报自环 | **OK** 自环报环 1 个 | **OK** 自环报环 1 个 | **OK** 自环报环 1 个 | **OK** 自环报环 1 个 |
| i145-two-cycle | #145 | find_cycles 漏报 2 环 A⇄B | **OK** A⇄B 报环 1 个 | **OK** A⇄B 报环 1 个 | **OK** A⇄B 报环 1 个 | **OK** A⇄B 报环 1 个 |
| i146-provenance-roundtrip | #146 | to_tags 的 verify_methods / vref 凭证读不回（st | **BUG** 强度 strong→weak | **BUG** 强度 strong→weak | **OK** 强度 strong→strong | **OK** 强度 strong→strong |
| i153-dedup-bypass | #153 | set_dedup_config 无密钥旁路，get_verifier_conf | **BUG** set_dedup(0.5) 后 get_verifier_config 报 0.85→0.85（报数与生效值不一致） | **BUG** set_dedup(0.5) 后 get_verifier_config 报 0.85→0.85（报数与生效值不一致） | **OK** set_dedup(0.5) 后 get_verifier_config 报 0.85→0.5（报数与生效值不一致） | **OK** set_dedup(0.5) 后 get_verifier_config 报 0.85→0.5（报数与生效值不一致） |
| i153-verifier-restart | #153 | 终裁通过的验证标准重启即失效 | **BUG** 终裁后 0.95 → 重启后 0.85 | **BUG** 终裁后 0.95 → 重启后 0.85 | **OK** 终裁后 0.95 → 重启后 0.95 | **OK** 终裁后 0.95 → 重启后 0.95 |
| i154-reflect-negation | #154 | 可逆性按子串判：『不删除』判为不可逆+需设计者 | **BUG** needs_designer=True | **BUG** needs_designer=True | **OK** needs_designer=False | **OK** needs_designer=False |
| i154-reflect-self-evidence | #154 | recursive_reflect 把自己的归档当证据：第二次起偏差恒 Fals | **BUG** 三次 deviation=[True, False, False] | **BUG** 三次 deviation=[True, False, False] | **OK** 三次 deviation=[True, True, True] | **OK** 三次 deviation=[True, True, True] |
| i156-cwd-hijack | #156 | 构造引擎时按裸模块名从 sys.path 导入：cwd 里同名 .py 被执行 | **BUG** cwd 中被执行的同名模块=['entity_registry', 'semantic_space', 'attention_policy' | **OK** cwd 中被执行的同名模块=[] | **OK** cwd 中被执行的同名模块=[] | **OK** cwd 中被执行的同名模块=[] |
| i161-activation-space-query | #161 | 纯空格查询命中全部节点 | **BUG** 空格查询 seeds=4 | **OK** 空格查询 seeds=0 | **OK** 空格查询 seeds=0 | **OK** 空格查询 seeds=0 |
| i164-importance-range | #164 | importance 无值域校验：1e6 原样入库并霸占 recall | **BUG** importance=1e6 入库后读数 1000000.0 | **OK** importance=1e6 入库后读数 1.0 | **OK** importance=1e6 入库后读数 1.0 | **OK** importance=1e6 入库后读数 1.0 |
| i164-negative-importance | #164 | 负 importance 原样入库 | **BUG** importance=-5 入库后 -5.0 | **OK** importance=-5 入库后 0.0 | **OK** importance=-5 入库后 0.0 | **OK** importance=-5 入库后 0.0 |
| i165-shared-sync | #165 | 共享层同步载荷不含结构层/锚点层 | **BUG** 载荷含结构=False，含锚点=False，共 1 条 | **BUG** 载荷含结构=False，含锚点=False，共 1 条 | **OK** 载荷含结构=True，含锚点=True，共 2 条 | **OK** 载荷含结构=True，含锚点=True，共 2 条 |
| i166-induce-majority | #166 | 某主题占候选池过半时 induce_concepts 归纳为 0 | **BUG** 10 条同主题 + 9 条噪声 → 归纳概念 0 个 | **BUG** 10 条同主题 + 9 条噪声 → 归纳概念 0 个 | **OK** 10 条同主题 + 9 条噪声 → 归纳概念 1 个 | **OK** 10 条同主题 + 9 条噪声 → 归纳概念 1 个 |
| i167-pending-deleted | #167 | 待终裁提案节点被 FIFO 删除后终裁仍返回成功 | **BUG** 终裁返回=True，节点=None | **BUG** 终裁返回=True，节点=None | **OK** 终裁返回=True，节点=structure | **OK** 终裁返回=True，节点=structure |
| i168-structure-edge | #168 | 结构层节点的关联边随对端知识节点删除被剥光 | **BUG** 情境端被遗忘=True，结构节点剩余边=0 | **BUG** 情境端被遗忘=True，结构节点剩余边=0 | **OK** 情境端被遗忘=False，结构节点剩余边=1 | **OK** 情境端被遗忘=False，结构节点剩余边=1 |
| i176-time-based | #176 | 遗忘按调用次数而非流逝时间（0.1s 内 50 次 decay 等于 50 分钟 | **BUG** 0.00s 墙钟内 50 次 decay 后 importance 0.5→0.182 | **BUG** 0.01s 墙钟内 50 次 decay 后 importance 0.5→0.182 | **BUG** 0.02s 墙钟内 50 次 decay 后 importance 0.5→0.182 | **BUG** 0.01s 墙钟内 50 次 decay 后 importance 0.5→0.182 |
| i179-what-happened-at | #179 | what_happened_at 只看 importance 前 500 条 | **BUG** what_happened_at(t) 命中目标=False | **OK** what_happened_at(t) 命中目标=True | **OK** what_happened_at(t) 命中目标=True | **OK** what_happened_at(t) 命中目标=True |
| i180-cred-step | #180 | cred_step 与 cred_factor 语义反转，混用单步归零 | **BUG** cred_step(100, cred_factor(0.1,1)) = 9.516（期望 ≈90.48） | **OK** cred_step(100, cred_factor(0.1,1)) = 90.484（期望 ≈90.48） | **OK** cred_step(100, cred_factor(0.1,1)) = 90.484（期望 ≈90.48） | **OK** cred_step(100, cred_factor(0.1,1)) = 90.484（期望 ≈90.48） |
| i181-cjk-tag | #181 | 中文标签写成 \uXXXX，按中文标签检索 0 条 | **BUG** by_tag('苹果')=0，by_tag('ent:猫')=0 | **OK** by_tag('苹果')=1，by_tag('ent:猫')=1 | **OK** by_tag('苹果')=1，by_tag('ent:猫')=1 | **OK** by_tag('苹果')=1，by_tag('ent:猫')=1 |
| i182-self-nonatomic | #182 | 坏调用后内存已改、快照写不进（运行态与持久态分叉） | **BUG** 坏调用失败=True，内存被污染=True，之后正常调用成功=False，SELF 节点 0→0 | **OK** 坏调用失败=True，内存被污染=False，之后正常调用成功=True，SELF 节点 0→1 | **OK** 坏调用失败=True，内存被污染=False，之后正常调用成功=True，SELF 节点 0→1 | **OK** 坏调用失败=True，内存被污染=False，之后正常调用成功=True，SELF 节点 0→1 |
| i182-self-overwrite | #182 | update_self 无门控 setattr：一次调用即改写价值观 | **BUG** values ['存在优先', '信任深化', '结构完整'] → ['被篡改的价值观'] | **OK** 拒绝: PermissionError | **OK** 拒绝: PermissionError | **OK** 拒绝: PermissionError |
| i183-search-wildcard | #183 | search_content('%') 返回全库（通配符注入） | **BUG** '%' 与 '_' 查询共命中 40 条（库中无字面 %/_） | **OK** '%' 与 '_' 查询共命中 0 条（库中无字面 %/_） | **OK** '%' 与 '_' 查询共命中 0 条（库中无字面 %/_） | **OK** '%' 与 '_' 查询共命中 0 条（库中无字面 %/_） |
| i183-tag-like | #183 | 标签检索 LIKE 子串误配（ent:car_1 命中 ent:car_12 / | **BUG** by_tag('ent:car_1') → ['frame of ent:carX1', 'frame of ent:car_1', 'fr | **OK** by_tag('ent:car_1') → ['frame of ent:car_1'] | **OK** by_tag('ent:car_1') → ['frame of ent:car_1'] | **OK** by_tag('ent:car_1') → ['frame of ent:car_1'] |
| i184-autodecay-dies | #184 | auto-decay 线程首次异常即静默退出 | **BUG** 衰减线程存活=False，后续情境仍被衰减=False | **OK** NaN 边被拒，无法触发线程异常 | **OK** NaN 边被拒，无法触发线程异常 | **OK** NaN 边被拒，无法触发线程异常 |
| i184-tx-lock | #184 | 写方法中途异常后连接停在未提交事务里，外部写入 database is lock | **BUG** decay 抛异常=True，外部写入被锁=True | **OK** NaN 边被拒，无中途异常 | **OK** NaN 边被拒，无中途异常 | **OK** NaN 边被拒，无中途异常 |
| i185-inf-importance | #185 | +inf importance 永生并排第一 | **BUG** 50 轮衰减后 inf | **OK** inf 被拒 | **OK** inf 被拒 | **OK** inf 被拒 |
| i185-nan-edge | #185 | NaN 边置信度入库，边衰减每轮抛 TypeError | **BUG** decay 抛 TypeError: unsupported operand type(s) for *: 'NoneType' and ' | **OK** NaN 边被拒 | **OK** NaN 边被拒 | **OK** NaN 边被拒 |
| i185-nan-importance | #185 | NaN importance 入库（NULL / NaN 永不遗忘） | **BUG** NaN 写入后读数 None | **OK** NaN 被拒（ValueError） | **OK** NaN 被拒（ValueError） | **OK** NaN 被拒（ValueError） |
| i191-sub-self | #191 | SUB 实例 update_self 抛 PermissionError（SEL | **BUG** PermissionError: role=sub 无权写入共享层（self），共享层由父节点主控 | **OK** SUB 可写本地自我层 | **OK** SUB 可写本地自我层 | **OK** SUB 可写本地自我层 |
| i199-activation-empty-query | #199 | 空查询把全图节点当满分种子 | **BUG** 空查询 seeds=4 | **OK** 空查询 seeds=0 | **OK** 空查询 seeds=0 | **OK** 空查询 seeds=0 |
| i200-skill-failure | #200 | 技能失败从不降信（50 败 10 胜置信度仍高） | **BUG** 50 败 10 胜 confidence=0.95 | **OK** 50 败 10 胜 confidence=0.42 | **OK** 50 败 10 胜 confidence=0.18 | **OK** 50 败 10 胜 confidence=0.18 |
| i200-skill-substring | #200 | record_action_sequence 用子串把『备份』追加进『删除备份』 | **BUG** 删除备份 程序='rm -rf /backup/old → tar czf db.tgz /dat' conf=0.55 | **OK** 删除备份 程序='rm -rf /backup/old' conf=0.50 | **OK** 删除备份 程序='rm -rf /backup/old' conf=0.50 | **OK** 删除备份 程序='rm -rf /backup/old' conf=0.50 |
| i200-skill-wildcard | #200 | 技能检索 hint 含 _ / % 命中任意技能 | **BUG** '_'/'%' 命中 ['删除备份', '删除备份'] | **OK** '_'/'%' 命中 [] | **OK** '_'/'%' 命中 [] | **OK** '_'/'%' 命中 [] |
| i201-self-recall | #201 | 自我快照以普通记忆参与 recall，挤掉真实记忆 | **BUG** recall top10 中 SELF=10，真实记忆在列=False | **OK** recall top10 中 SELF=0，真实记忆在列=True | **OK** recall top10 中 SELF=0，真实记忆在列=True | **OK** recall top10 中 SELF=0，真实记忆在列=True |
| i201-self-unbounded | #201 | 每次 update_self 新增一个不可删除的 SELF 节点（无界） | **BUG** 100 次 update_self 后 SELF 层节点 100 | **OK** 100 次 update_self 后 SELF 层节点 1 | **OK** 100 次 update_self 后 SELF 层节点 1 | **OK** 100 次 update_self 后 SELF 层节点 1 |
| i205-self-edge-decay | #205 | 自我→经历因果边被衰减删除 | **BUG** 自我→经历边 1 → 300 轮后 0 | **OK** 自我→经历边 1 → 300 轮后 1 | **OK** 自我→经历边 1 → 300 轮后 1 | **OK** 自我→经历边 1 → 300 轮后 1 |
| i206-trust-gate | #206 | t_total 极大时任意快照都以 imp=1.0 写入长期层并加保护 | **BUG** 闲聊快照 layer=long_term imp=1.0 protected=True | **OK** 闲聊快照 layer=knowledge imp=0.561 protected=None | **OK** 闲聊快照 layer=knowledge imp=0.55 protected=None | **OK** 闲聊快照 layer=knowledge imp=0.55 protected=None |
| i206-trust-nan | #206 | update_trust_state 接受 NaN / 越界 t_total | **BUG** 被原样接受的非有限值=['nan', 'inf'] | **OK** 被原样接受的非有限值=[] | **OK** 被原样接受的非有限值=[] | **OK** 被原样接受的非有限值=[] |
| i207-low-imp-context | #207 | importance ≤ 阈值的情境记忆永不衰减、永不删除 | **BUG** 1000 轮衰减后存活 3/3 | **OK** 1000 轮衰减后存活 0/3 | **OK** 1000 轮衰减后存活 0/3 | **OK** 1000 轮衰减后存活 0/3 |
| i210-archive-immortal | #210 | 归档值落在衰减死区：归档节点永久驻留 | **BUG** 归档+500 轮衰减后仍在=True | **OK** 归档+500 轮衰减后仍在=False | **OK** 归档+500 轮衰减后仍在=False | **OK** 归档+500 轮衰减后仍在=False |
| i210-forget-zero | #210 | forget_advisor：0.0 不归档 / 降权反把 0.05 抬到 0. | **BUG** 0.05 节点→0.1，0.0 节点被归档/删除=False | **OK** 0.05 节点→0.05，0.0 节点被归档/删除=True | **OK** 0.05 节点→0.05，0.0 节点被归档/删除=True | **OK** 0.05 节点→0.05，0.0 节点被归档/删除=True |
| i212-evolution-bound | #212 | 同值重复修正 value_evolution 仍无界追加 | **BUG** 同值 500 次 evolution 增量 1002 | **OK** 同值 500 次 evolution 增量 0 | **OK** 同值 500 次 evolution 增量 0 | **OK** 同值 500 次 evolution 增量 0 |
| i212-value-refine | #212 | record_value_change 细化一条价值观即抹掉整表 | **BUG** 细化前 ['存在优先', '信任深化', '结构完整'] → 细化后 ['存在优先（细化）'] | **OK** 细化前 ['存在优先', '信任深化', '结构完整'] → 细化后 ['存在优先（细化）', '信任深化', '结构完整'] | **OK** 细化前 ['存在优先', '信任深化', '结构完整'] → 细化后 ['存在优先（细化）', '信任深化', '结构完整'] | **OK** 细化前 ['存在优先', '信任深化', '结构完整'] → 细化后 ['存在优先（细化）', '信任深化', '结构完整'] |
| i213-novelty-english | #213 | 新奇检测对英文/代码/西里尔失明（恒 0.5） | **BUG** 首见新奇度={'The production': 0.5, 'rm -rf /var/li': 0.5, 'Москва столица': | **OK** 首见新奇度={'The production': 1.0, 'rm -rf /var/li': 1.0, 'Москва столица': | **OK** 首见新奇度={'The production': 1.0, 'rm -rf /var/li': 1.0, 'Москва столица': | **OK** 首见新奇度={'The production': 1.0, 'rm -rf /var/li': 1.0, 'Москва столица': |
| i213-novelty-identifier | #213 | 只改数字/标识符（收款账号、IP）被判完全已知 | **BUG** 新奇度={'999999': 0.0, '.0.0.5': 0.0} | **OK** 新奇度={'999999': 0.9, '.0.0.5': 0.9} | **OK** 新奇度={'999999': 0.9, '.0.0.5': 0.9} | **OK** 新奇度={'999999': 0.9, '.0.0.5': 0.9} |
| i213-novelty-repeat-en | #213 | 英文内容重复仍判 0.5（无法识别已知） | **BUG** 重复英文新奇度=0.500 | **OK** 重复英文新奇度=0.000 | **OK** 重复英文新奇度=0.000 | **OK** 重复英文新奇度=0.000 |
| i214-promote-context | #214 | 情境层→知识层巩固通路不存在（维护周期从不提升） | **BUG** 3 次维护后层=context | **BUG** 3 次维护后层=context | **OK** 3 次维护后层=knowledge | **OK** 3 次维护后层=knowledge |
| i215-cycle-consistency | #215 | 环长 > max_depth 时 has_cycle=True 而 self_c | **BUG** has_cycle=True，self_check cycles_found=0 | **OK** has_cycle=True，self_check cycles_found=1 | **OK** has_cycle=True，self_check cycles_found=1 | **OK** has_cycle=True，self_check cycles_found=1 |
| i215-selfcheck-time | #215 | 有环稠密图 self_check 仍整趟深搜（45 节点/211 边） | **BUG** self_check 用时 3.03s 完成=True | **OK** self_check 用时 0.35s 完成=True | **OK** self_check 用时 0.02s 完成=True | **OK** self_check 用时 0.06s 完成=True |
| i216-failure-importance | #216 | 失败经验 importance 低于成功（负记忆不同价） | **BUG** 成功 importance=0.6 失败=0.4 | **OK** 成功 importance=0.5 失败=0.5 | **OK** 成功 importance=0.5 失败=0.5 | **OK** 成功 importance=0.5 失败=0.5 |
| i216-rejected-resubmit | #216 | 设计者否决过的提案原文重提即写入结构层 | **BUG** 重提落层=structure | **OK** 重提被拒 | **OK** 重提被拒 | **OK** 重提被拒 |
| i216-skill-from-failures | #216 | 同一失败犯 21 次，技能照常提取 / 负记忆不参与 | **BUG** 技能存在=True conf=0.50 | **OK** 技能存在=True conf=0.21 | **OK** 技能存在=True conf=0.08 | **OK** 技能存在=True conf=0.08 |
| i217-sub-snapshot | #217 | SUB 经快照『已存在→更新』分支改写结构层节点 | **BUG** 结构层 tags 变化=True，被登记保护=True | **OK** 结构层 tags 变化=False，被登记保护=False | **OK** 结构层 tags 变化=False，被登记保护=False | **OK** 结构层 tags 变化=False，被登记保护=False |
| i222-blindspot-bypass | #222 | store.resolve_blindspot 无密钥即可关闭盲区 | **BUG** 无密钥绕过后盲区仍开放=False | **OK** 无密钥绕过后盲区仍开放=True | **OK** 无密钥绕过后盲区仍开放=True | **OK** 无密钥绕过后盲区仍开放=True |
| i223-dedup-importance | #223 | 去重命中时丢弃更高的 importance | **BUG** 两次写入 importance 0.3/0.95 → 库中最大 0.30 | **OK** 两次写入 importance 0.3/0.95 → 库中最大 0.95 | **OK** 两次写入 importance 0.3/0.95 → 库中最大 0.95 | **OK** 两次写入 importance 0.3/0.95 → 库中最大 0.95 |
| i223-dedup-modality | #223 | 不同模态的同文内容被合并成一个节点 | **BUG** audio 并入 text 节点=True | **OK** audio 并入 text 节点=False | **OK** audio 并入 text 节点=False | **OK** audio 并入 text 节点=False |
| i223-dedup-tags | #223 | 去重命中时丢弃新输入的 tags/entities | **BUG** 按 project:alpha 检索命中 0 条（应能找到合并或新建的节点） | **OK** 按 project:alpha 检索命中 1 条（应能找到合并或新建的节点） | **OK** 按 project:alpha 检索命中 1 条（应能找到合并或新建的节点） | **OK** 按 project:alpha 检索命中 1 条（应能找到合并或新建的节点） |
| i224-context-hit | #224 | 快照命中情境层旧节点报 long_term+protected，节点仍留在情境层 | **BUG** 回执 long_term，旧情境节点现状=None | **OK** 回执 long_term，旧情境节点现状=knowledge | **OK** 回执 long_term，旧情境节点现状=knowledge | **OK** 回执 long_term，旧情境节点现状=knowledge |
| i224-receipt-layer | #224 | write_snapshot 回执 layer 与实际落库层不一致 | **BUG** hint=0.2: 回执 context/None 实际 knowledge | **OK** 回执与落库一致 | **OK** 回执与落库一致 | **OK** 回执与落库一致 |
| i225-polarity | #225 | 失败经验并进成功节点并为其增信 | **BUG** 失败返回成功节点=True，成功节点置信度=0.600 | **OK** 失败返回成功节点=False，成功节点置信度=0.500 | **OK** 失败返回成功节点=False，成功节点置信度=0.500 | **OK** 失败返回成功节点=False，成功节点置信度=0.500 |
| i229-activation-opposite | #229 | OPPOSITE（矛盾）边按兴奋传导，被反驳结论激活 | **BUG** 被三条证据反驳的旧结论激活值=1.5 | **OK** 被三条证据反驳的旧结论激活值=0 | **OK** 被三条证据反驳的旧结论激活值=0 | **OK** 被三条证据反驳的旧结论激活值=0 |
| i234-sub-edge-structure | #234 | SUB 可在结构层节点间新增并自证『已验证』边 | **BUG** SUB 注入边存在=True，verified=True | **OK** SUB 写共享层边被拒 | **OK** SUB 写共享层边被拒 | **OK** SUB 写共享层边被拒 |
| i234-sub-protect | #234 | SUB 可为结构层节点登记保护 | **BUG** 结构层节点被 SUB 登记保护=True | **OK** 结构层节点被 SUB 登记保护=False | **OK** 结构层节点被 SUB 登记保护=False | **OK** 结构层节点被 SUB 登记保护=False |
| i234-sub-tag-structure | #234 | SUB 可对结构层节点打标签 | **BUG** tags=['structure', 'promotion_pending'] | **OK** tags=['structure'] | **OK** tags=['structure'] | **OK** tags=['structure'] |
| i243-facade-init | #243 | world 门面声明 init 动作但没有 init 分支 | **BUG** init 失败的门面=['spacetime_consistency', 'world_model', 'world_learner', ' | **OK** init 失败的门面=[] | **OK** init 失败的门面=[] | **OK** init 失败的门面=[] |
| i244-sub-edge-overwrite | #244 | SUB 以同 id 覆盖 PRIMARY 的结构层因果边 | **BUG** 边现状={'id': 'edge_2243c46d_1791517359560', 'src': 'struct_70064532_1791 | **OK** 边现状={'id': 'edge_d44f2dd2_1791517384789', 'src': 'struct_757caed5_1791 | **OK** 边现状={'id': 'edge_50b84a0bde5b', 'src': 'struct_dbdf9c115cc5', 'dst': ' | **OK** 边现状={'id': 'edge_7d2b196c5e25', 'src': 'struct_f8b4b9309c16', 'dst': ' |
| i246-cap-float | #246 | 容量传 200.0 后每次写入抛 TypeError | **OK** float 容量可用 | **OK** float 容量可用 | **OK** float 容量可用 | **OK** float 容量可用 |
| i246-cap-restart | #246 | 情境层容量不持久：重启后第一条 add_context 删掉几百条 | **BUG** 重启前 300 条 → 重启后写 1 条后 200 条 | **OK** 重启前 300 条 → 重启后写 1 条后 301 条 | **OK** 重启前 300 条 → 重启后写 1 条后 301 条 | **OK** 重启前 300 条 → 重启后写 1 条后 301 条 |
| i252-dense-scc | #252 | 11 节点互为因果：self_check 全枚举（14s/3GB） | **BUG** BUG self_check 8s 未完成 | **OK** self_check 用时 0.06s | **OK** self_check 用时 0.01s | **OK** self_check 用时 0.01s |
| i252-find-cycles-budget | #252 | find_cycles 在稠密 SCC 上无预算（9 节点完全图） | **BUG** find_cycles 用时 2.16s，返回 125664 | **BUG** find_cycles 用时 6.38s，返回 125664 | **OK** find_cycles 用时 1.84s，返回 100000 | **OK** find_cycles 用时 1.55s，返回 100000 |
| i257-protect-ghost | #257 | 不存在的 id 也能进保护名单 | **BUG** 幽灵 id 在保护名单=True | **OK** 幽灵 id 在保护名单=False | **OK** 幽灵 id 在保护名单=False | **OK** 幽灵 id 在保护名单=False |
| i257-protect-many | #257 | 保护名单 >16383 条后 decay_cycle 抛 too many SQ | **OK** decay 正常 | **OK** decay 正常 | **OK** decay 正常 | **OK** decay 正常 |
| i258-consolidate-1000 | #258 | consolidate_cycle 只处理 importance 前 1000  | **BUG** 20 条低重要度中被降权 0 | **OK** 20 条低重要度中被降权 20 | **OK** 20 条低重要度中被降权 20 | **OK** 20 条低重要度中被降权 20 |

</details>

## 维度二 · 性质测试（自写随机化框架，每条 200 个固定种子）

| 性质 | 说明 | base | integrated | ng-prev | ng |
|---|---|---|---|---|---|
| P01-layer-immutability | 锚点/结构层在任意维护操作序列后内容与层不变 | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P02-dedup-idempotent | 同一内容重复写入幂等：返回同一 id、库中只有一条 | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P03-dedup-polarity | 去重对否定/数值敏感：插入『不』或改一个数字的句子不被合并 | 69/200（34.5%） | 69/200（34.5%） | 0/200（0.0%） | 0/200（0.0%） |
| P04-decay-monotone | 衰减单调：可衰减节点 importance 不增、被删节点不复活 | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P05-decay-termination | 衰减终止：未保护的情境节点在有限轮（factor=0.2，≤150 轮）内被遗忘 | 196/200（98.0%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P06-export-import-roundtrip | 导出→导入往返：本地层（知识/情境）与其间的边逐项等价；共享层（锚点/结构）要么原样恢复、要么整条不导入（隔离），绝不被改写 | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P07-cycle-vs-brute | 环检测与暴力枚举一致：has_cycle 判定 + find_cycles 计数（n≤6） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P08-concurrent-no-loss | 并发写不丢：3 线程各写 8 条唯一内容，全部恰好落库一次 | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P09-nonfinite-rejected | 非有限数值（NaN/±inf）不进库：要么被拒，要么不以非有限值存储 | 200/200（100.0%） | 48/200（24.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P10-recall-no-self | 检索不返回 SELF 快照 | 200/200（100.0%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P11-sub-no-protected-write | SUB 角色不可改写受保护层（锚点/结构）的节点与边 | 188/200（94.0%） | 112/200（56.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P12-importance-range | importance 写入后恒在 [0,1]（越界值被拒或钳制） | 135/200（67.5%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P13-tag-exact | 按标签检索精确匹配（含 _ % 中文 前缀相同的标签） | 92/200（46.0%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P14-gate-receipt | 门控回执层 = 实际落库层（任意 hint） | 43/200（21.5%） | 0/200（0.0%） | 0/200（0.0%） | 0/200（0.0%） |
| P15-protected-survive | 被 protect 的节点在衰减/容量淘汰/遗忘建议后仍存在 | 81/200（40.5%） | 93/200（46.5%） | 0/200（0.0%） | 0/200（0.0%） |

<details><summary>首个反例</summary>

- `P03-dedup-polarity` @ base：seed=0 — 『移告警剂量6毫克』与『移告警剂量7毫克』被合并
- `P03-dedup-polarity` @ integrated：seed=0 — 『移告警剂量6毫克』与『移告警剂量7毫克』被合并
- `P05-decay-termination` @ base：seed=0 — 150 轮后仍存活 importance=[0.1, 0.01, 0.0, 0.05]
- `P09-nonfinite-rejected` @ base：seed=0 — trust=-inf 存为 -inf
- `P09-nonfinite-rejected` @ integrated：seed=4 — verify_edge=-inf 存为 -inf
- `P10-recall-no-self` @ base：seed=0 — recall 返回 SELF 节点 2 个
- `P11-sub-no-protected-write` @ base：seed=0 — SUB 操作 [6, 2, 4] 后共享层发生变化
- `P11-sub-no-protected-write` @ integrated：seed=0 — SUB 操作 [6, 2, 4] 后共享层发生变化
- `P12-importance-range` @ base：seed=0 — knowledge importance=806690.970 存为 806690.970427902
- `P13-tag-exact` @ base：seed=1 — by_tag('苹果') 返回 0，真值 2
- `P14-gate-receipt` @ base：seed=5 — hint=0.13 回执 context 实际 knowledge
- `P15-protected-survive` @ base：seed=0 — 受保护节点被删除
- `P15-protected-survive` @ integrated：seed=0 — 受保护节点被删除

</details>

## 维度三 · 性能（中位耗时 ms；文件库；N 个知识节点 + N/10 情境 + N/2 条 DAG 因果边）

> 测量机为共享的 2 核沙箱，同一快照两次运行的中位数可差 ±30%（尤其 50k 档）；性能分只占 15%，跨快照比较请看数量级与趋势，正式结论建议在独占机器上用 `--skip probes,props,legacy,quality` 复跑性能档。

**N = 1000**

| 快照 | 灌库 s | 首读 ms（不计分） | add | recall | decay_cycle | self_check | activation | Py 堆峰值 MB | maxrss MB |
|---|---|---|---|---|---|---|---|---|---|
| base | 0.06 | 8.50 | 4.54 | 8.29 | 5.45 | 0.92 | 4.21 | 22.5 | 44.3 |
| integrated | 0.07 | 8.80 | 4.96 | 8.56 | 2.84 | 1.21 | 11.57 | 23.6 | 46.4 |
| ng-prev | 0.09 | 31.60 | 0.71 | 0.96 | 0.93 | 0.02 | 0.92 | 3.7 | 24.1 |
| ng | 0.06 | 44.20 | 0.70 | 0.95 | 0.94 | 0.02 | 0.96 | 3.6 | 24.1 |

**N = 10000**

| 快照 | 灌库 s | 首读 ms（不计分） | add | recall | decay_cycle | self_check | activation | Py 堆峰值 MB | maxrss MB |
|---|---|---|---|---|---|---|---|---|---|
| base | 0.7 | 13.60 | 7.60 | 12.55 | 62.13 | 9.58 | 35.19 | 33.0 | 60.8 |
| integrated | 0.72 | 14.10 | 8.17 | 13.23 | 30.85 | 12.34 | 105 | 41.9 | 70.1 |
| ng-prev | 0.86 | 356 | 0.94 | 1.79 | 6.99 | 0.03 | 6.97 | 10.5 | 28.8 |
| ng | 0.64 | 434 | 0.92 | 1.88 | 7.47 | 0.03 | 6.86 | 12.0 | 29.1 |

**N = 50000**

| 快照 | 灌库 s | 首读 ms（不计分） | add | recall | decay_cycle | self_check | activation | Py 堆峰值 MB | maxrss MB |
|---|---|---|---|---|---|---|---|---|---|
| base | 4.24 | 14.00 | 18.14 | 22.47 | 590 | 98.52 | 286 | 98.1 | 132.8 |
| integrated | 5.64 | 22.10 | 23.89 | 13.83 | 323 | 104 | 749 | 139.9 | 182.1 |
| ng-prev | 6.7 | 2481 | 1.99 | 5.09 | 35.53 | 0.04 | 38.29 | 32.2 | 55.0 |
| ng | 3.74 | 2326 | 1.95 | 5.06 | 35.21 | 0.04 | 39.45 | 34.2 | 55.2 |

## 维度四 · 代码质量（自写 AST 指标）

| 快照 | 范围 | 模块数 | 总行数 | 最大模块行数 | 函数数 | 最大函数行数 | 平均函数长度 | 平均 CC | CC>10 个数 | 重复块率 |
|---|---|---|---|---|---|---|---|---|---|---|
| base | `lingshu/core` | 8 | 6579 | 5248（core.py） | 336 | 155 | 16.66 | 4.4 | 35 | 0.9% |
| integrated | `lingshu/core` | 10 | 8176 | 5493（core.py） | 389 | 174 | 17.76 | 4.75 | 44 | 1.1% |
| ng-prev | `lingshu_ng` | 109 | 19591 | 752（compat.py） | 1524 | 48 | 8.52 | 3.0 | 53 | 0.5% |
| ng | `lingshu_ng` | 109 | 19703 | 752（compat.py） | 1534 | 48 | 8.52 | 3.0 | 53 | 0.5% |

<details><summary>base · 圈复杂度 top10</summary>

| 函数 | CC | 行数 |
|---|---|---|
| `lingshu/core/core.py:world3d@2850` | 45 | 153 |
| `lingshu/core/provenance.py:from_legacy@271` | 38 | 90 |
| `lingshu/core/core.py:insight_report@1636` | 29 | 48 |
| `lingshu/core/core.py:induce_concepts@4840` | 25 | 79 |
| `lingshu/core/core.py:recalc_structural_importance@1403` | 24 | 111 |
| `lingshu/core/core.py:ingest_frame@4258` | 24 | 65 |
| `lingshu/core/longterm_gate.py:write_snapshot@162` | 23 | 76 |
| `lingshu/core/provenance.py:validate@196` | 22 | 38 |
| `lingshu/core/core.py:find_cycles@860` | 19 | 107 |
| `lingshu/core/core.py:visual_check@2788` | 19 | 61 |

</details>

<details><summary>integrated · 圈复杂度 top10</summary>

| 函数 | CC | 行数 |
|---|---|---|
| `lingshu/core/world_facade.py:world3d@24` | 54 | 174 |
| `lingshu/core/provenance.py:from_legacy@288` | 38 | 90 |
| `lingshu/core/core.py:recalc_structural_importance@1872` | 31 | 135 |
| `lingshu/core/core.py:insight_report@2191` | 30 | 54 |
| `lingshu/core/longterm_gate.py:write_snapshot@228` | 30 | 111 |
| `lingshu/core/core.py:add_perception@2786` | 26 | 84 |
| `lingshu/core/core.py:induce_concepts@4994` | 25 | 80 |
| `lingshu/core/core.py:ingest_frame@4335` | 24 | 65 |
| `lingshu/core/core.py:insight_verify@2137` | 23 | 53 |
| `lingshu/core/provenance.py:validate@196` | 22 | 38 |

</details>

<details><summary>ng-prev · 圈复杂度 top10</summary>

| 函数 | CC | 行数 |
|---|---|---|
| `lingshu_ng/compat_frame.py:ingest_frame@61` | 20 | 37 |
| `lingshu_ng/graphquery.py:recalc_structural_importance@205` | 20 | 43 |
| `lingshu_ng/provenance.py:validate@125` | 20 | 32 |
| `lingshu_ng/types.py:from_json@86` | 20 | 31 |
| `lingshu_ng/engine.py:_find_duplicate@145` | 18 | 24 |
| `lingshu_ng/exchange.py:_sanitize_node@98` | 18 | 31 |
| `lingshu_ng/gen/layout.py:plan@195` | 18 | 44 |
| `lingshu_ng/types.py:to_json@67` | 18 | 17 |
| `lingshu_ng/compat_world.py:_w3_build@97` | 17 | 35 |
| `lingshu_ng/nn/search.py:recursive_search@62` | 17 | 45 |

</details>

<details><summary>ng · 圈复杂度 top10</summary>

| 函数 | CC | 行数 |
|---|---|---|
| `lingshu_ng/compat_frame.py:ingest_frame@61` | 20 | 37 |
| `lingshu_ng/graphquery.py:recalc_structural_importance@205` | 20 | 43 |
| `lingshu_ng/provenance.py:validate@125` | 20 | 32 |
| `lingshu_ng/types.py:from_json@95` | 20 | 31 |
| `lingshu_ng/engine.py:_find_duplicate@145` | 18 | 24 |
| `lingshu_ng/exchange.py:_sanitize_node@108` | 18 | 31 |
| `lingshu_ng/gen/layout.py:plan@195` | 18 | 44 |
| `lingshu_ng/compat_world.py:_w3_build@97` | 17 | 35 |
| `lingshu_ng/nn/search.py:recursive_search@62` | 17 | 45 |
| `lingshu_ng/nn/text.py:build_lexicon@73` | 17 | 38 |

</details>

## 复跑

```bash
cd /workspace/work/ls/rewrite
python3 evalsuite/run_all.py \
  --snap base=/workspace/work/ls/upstream@2bb8291 \
  --snap integrated=/workspace/work/ls/integrated \
  --snap ng=/workspace/work/ls/rewrite        # name=ng → 走 lingshu_ng.compat 门面
```

单个探针：`PYTHONPATH=<快照根>:evalsuite python3 evalsuite/probe_runner.py --impl legacy|ng --probe <id>`；单条性质：`... --prop <id> --seeds 200`；性能：`... --perf 10000 [--trace]`。
