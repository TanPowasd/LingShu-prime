# 上游 core issue → 探针覆盖

来源：GitHub FuRongJun-1999/lingshu issues（state=all，只读 API 拉取于 2026-10-09），按标题/正文筛 core 相关（含 core 门面上的 world 入口 #55/#243）。
core 相关 issue 92 个；写成行为探针的 86 个，探针 131 个。

| issue | 状态 | 标题 | 探针 |
|---|---|---|---|
| #7 | open | [core] activation.py 无保护 import numpy 击穿「轻核承诺」；且现有 import 冒烟结构上无法证伪该契约 | `i7-numpy-free` |
| #16 | closed | [core] export_all 未对缺失表降级：entities 表全仓 0 处创建，标称「灾备基础」的导出必然抛 Operationa | `i16-export` |
| #20 | open | [core/provenance] from_legacy 两项遗留：human_review 永远推不出；「白箱校验」记录 strengt | `i20-provenance-human-review` |
| #29 | open | [core/记忆] 重复写入即增信、矛盾不入账、知识节点不衰减、检索不看置信度——错误内容可被"养"到置信度 1.0 并排在真话前面 | `i29-repeat-boost` |
| #33 | open | [core] 自我模型重启即失忆：SELF 层声明「不可遗忘」但引擎启动时无条件新建 | `i33-self-restart`, `i33-trust-restart` |
| #35 | open | [core] 检索按插入序硬截断无 ORDER BY：600 条记忆只返回前 300，老记忆永久不可达 | `i35-search-truncation` |
| #36 | open | [core] 「不可遗忘」保护在两条遗忘路径上完全失效：衰减周期与情境层上限均不检查保护标记 | `i36-protect-decay`, `i36-protect-fifo` |
| #37 | open | [core] 关闭生命周期竞态：close() 不 join 衰减线程，后台线程继续访问已关闭连接必然抛异常 | `i37-close-thread` |
| #38 | open | [core] 洞见验证（insight_verify）自证通道：V2 零证据自报即 verified 且 importance 直升 0.9 | `i38-insight-v2` |
| #44 | open | [core/longterm_gate] 「信息差驱动的关联边」两条路径整体静默失效：relation_type 传字符串致 Attribu | `i44-gate-links` |
| #48 | open | [core] 长期记忆门控的新奇度只看「最高重要性/最近 80 条」：更老的既有知识对它不可见，已存在的内容被判为新知识并重复提权入库 | `i48-novelty-window` |
| #51 | open | core: hmac.compare_digest 对非 ASCII 密钥抛 TypeError——6 条终裁通路从「拒绝」变成「抛异常不可 | `i51-nonascii-key` |
| #52 | open | core: increment_access 在 :memory:（引擎默认）后端静默失效——另开连接落进空库，access_count 恒 | `i52-access-memory` |
| #53 | open | core/activation: 条件衰减的 cond_match 项从未接线（全仓 0 调用 + 空循环），且 :18 声明 max、:2 | —（静态契约（cond_match 全仓零调用、docstring 公式与实现不符）：无行为读数可测，留给代码质量/评审） |
| #54 | open | core: consume_events 先清空 _event_queue 再判 paused——paused 期间排队事件被静默丢弃（且  | `i54-consume-paused` |
| #55 | open | world: 三处退化输入崩溃——verify_run(0) / 空世界 _select() / VoxelWorld(size<5)（各附 | `i55-world-degenerate` |
| #57 | open | [core/nn] 公开 API 的未兑现契约：声明参数在函数体内零引用（全仓 29 处，其中 check_escalation 的数值阈值 | `i57-escalation-value` |
| #81 | open | [core] 多线程下 LayeredStore 不可用：共享单个 Connection，2 写线程即 235 次异常且污染读路径 | `i81-threads` |
| #82 | open | [core] search_content 相关度分数恒饱和到 1.0：只要含查询词的每个 bigram 就满分，相关度排序失效 | `i82-score-saturation` |
| #83 | closed | [core/provenance] 显式来源被 gate/novel_prefeed 覆盖，system/tool/fixture 无法往返 | `i83-provenance-gate` |
| #88 | open | [core] get_layer_nodes 承诺整层枚举却静默截为 50 条，get_anchors 漏掉已存锚点 | `i88-anchors-50`, `i88-layer-enum` |
| #89 | open | [core] spatiotemporal_query 的 time_radius=0 在同刻候选出现时抛 ZeroDivisionErro | `i89-radius0` |
| #92 | closed | [core] 启动只读化守卫 + SCHEMA_VERSION 恒为 1：老库的缺列/缺表永远补不上，engine 构造即崩 | `i92-old-schema` |
| #93 | open | [core] 声明的 FOREIGN KEY 从未启用：孤儿边可写入、可由 import_all 引入，verify_integrity 只 | `i93-dangling-import` |
| #94 | open | [core] consolidate_cycle 用增量前的过期副本判 %10：高重要度记忆第 1 轮即被提权，第 10 次演练漏提、第 1 | `i94-consolidate-round` |
| #95 | open | [core/activation] 空认知图默认激活抛 ValueError，工作态和审计流程中断 | `i95-activation-empty-graph` |
| #103 | open | [core/记忆] 复核报告：写入路径缺来源判据、知识层缺衰减与冲突落账、检索终排未纳入置信度（基线 d7c6b33） | —（#29 的复核报告，读数与 #29 相同 → 由 i29-* / i142-* 覆盖） |
| #107 | open | [core] self_check 自检结构性失明：self_ok 用 in-memory self_model 兜底，恒 True、无法发 | `i107-selfcheck-blind` |
| #109 | open | [core] register_external_anchor 绕过 D-007 终裁：外部输入无密钥直写结构层，置信度 1.0、不可删除、 | `i109-external-anchor` |
| #114 | open | [core/longterm_gate] 评分上限结构性低于阈值：默认 t_total=0 时 imp≤0.4725，长期层不可达，全新内容 | `i114-gate-unreachable` |
| #115 | open | [core/记忆] register_conflict 的 OPPOSITE 边会被普通 decay_cycle 按未验证边删除（55 轮  | `i115-conflict-edge-decay` |
| #117 | open | [world/prediction × core] 预测反馈写回不对称：一次命中即把目标节点的全部因果入边永久标为 verified（自此免 | `i117-verify-edge-range` |
| #118 | open | [core/治理] D-003 双签与 A-2 四步制衡只验密钥、不验角色与状态：同一身份可走完全程；已否决的提案可被「复核」复活后改判通过 | `i118-rejected-revive`, `i118-same-identity`, `i118-standard-range`, `i118-unverified-adjudicate` |
| #122 | open | [core/self] SelfModel.history 无界增长：update_self 每调一次 append 一条，无 MAX/钳制 | `i122-history-bound` |
| #125 | open | [core/M13] import_all 是一条无密钥的全权写入通道：一份篡改的备份即可改写结构层原文、伪造「已终裁」的验证标准、关闭全部 | `i125-import-escalation`, `i125-import-structure` |
| #126 | open | [core/activation] SciPy 图缓存不刷新：新增节点被丢弃，删除边仍参与激活 | `i126-activation-cache` |
| #127 | open | [core/权限] 共享层写保护只看「新节点的 layer」不看「库里旧行的 layer」：SUB 角色用同 id 写一个知识层节点即可把结 | `i127-primary-delete-structure`, `i127-sub-demote`, `i127-sub-importance` |
| #130 | open | [core/A-3] 升级点机制全链路断开：check_escalation 全仓零调用方；recursive_reflect 判出「不可逆 | `i130-reflect-escalation`, `i130-sub-escalation` |
| #132 | open | [core/检索] SYNONYM_GROUPS 用子串触发扩展：「EMAIL」→灵枢/智能，「数据库」→记忆/记录，泛词灌满 LIMIT  | `i132-zero-score` |
| #133 | open | [core/condition_normalize] 「声明域可被求值域反驳」在实现中不存在：E1 两端都是 asserted 域，9 个声 | —（条件域『声明↔求值』反驳机制的设计缺失（需维护者裁决口径），无固定判据） |
| #138 | open | [core/condition_normalize] 非法值或带空格的值被静默折叠成 __UNASSERTED__：与「未声明」同 cond | `i138-cond-unasserted` |
| #139 | open | [core/子图替换] subgraph_replace 是一条「先删后挂、无范围校验」的级联删除：new_subtree 缺键即旧子树永久 | `i139-replace-nonatomic`, `i139-replace-parent`, `i139-replace-protected` |
| #140 | open | [core/治理] 晋升提案只记 node_id、不锁内容：复核后同 id 改写即可让终裁把未经复核的内容写进结构层（SUB 角色借此越权写 | `i140-content-swap` |
| #142 | open | [core/记忆] M5 去重对否定词与数值不敏感：「不过敏」「7.5 毫克」「尚未修复」被当作重复吞掉，原命题反而增信；更正 25 次后错 | `i142-correction-boost`, `i142-negation`, `i142-number` |
| #145 | closed | [core/因果推理] reason_causal 把超过 max_depth 或带环的链整条丢弃（返回 0 条）；find_cycles  | `i145-cycle-branch`, `i145-dup-report`, `i145-long-chain`, `i145-self-loop`, `i145-two-cycle` |
| #146 | open | [core/provenance] to_tags 写出的验证方式与 vref 凭证 from_legacy 读不回：strong 验证往返 | `i146-provenance-roundtrip` |
| #153 | open | [core/A-2] 终裁通过的验证标准重启即失效（台账和结构层仍写「已通过」）；同一参数有无密钥旁路 set_dedup_config，g | `i153-dedup-bypass`, `i153-verifier-restart` |
| #154 | open | [core/3.12 反思] recursive_reflect 把自己的归档当证据：同一 claim 第二次起偏差恒为 False；可逆性 | `i154-reflect-negation`, `i154-reflect-self-evidence` |
| #156 | open | [core/装配][安全] 引擎构造时按裸模块名从 sys.path 导入 13 个组件：当前目录里任一同名 .py 即在进程内执行、拿到活 | `i156-cwd-hijack` |
| #161 | open | [core/activation] 空查询或纯空格查询把前 top_k 个节点全部以满分 1.0 种入工作态（_seed_by_text 的 | `i161-activation-space-query` |
| #164 | open | [core/写入] importance 全路径无值域校验：add_perception / ingest_frame 接受 1e6 或负数 | `i164-importance-range`, `i164-negative-importance` |
| #165 | open | [core/共享层同步][结构层] 唯一的「蜂群分层同步」导出的是本地知识层、结构层/锚点层 0 条进入载荷；载荷有损且全仓零消费方——SU | `i165-shared-sync` |
| #166 | open | [core/归纳] induce_concepts 倒排预筛丢掉池内 DF>半数的二元组：某主题占候选池过半时永远聚不成概念（同主题 10  | `i166-induce-majority` |
| #167 | open | [core/固化流水线][结构层] 待终裁的提案节点会被衰减 / 情境层 FIFO 静默删除，之后终裁仍返回 True、提案记为 appro | `i167-pending-deleted` |
| #168 | open | [core/遗忘][结构层] 「结构层关联边不衰减」不成立：对端为情境层时随自然遗忘被连带删除，对端为知识层时 delete_node 一并 | `i168-structure-edge` |
| #169 | open | [core/架构] 引擎 13 个「器官」模块不在仓内：默认构造后 15 个组件为 None、错误只存在属性里不告警，self_check  | —（架构层：13 个『器官』模块不在仓内、组件静默为 None；判据依赖实现内部属性，不写行为探针） |
| #176 | open | [core/time_core] 时间核章程未兑现：连续核 cred(dt) 全仓零调用，记忆遗忘按「调用次数」而非流逝时间——interv | `i176-time-based` |
| #179 | open | [core/P1-2 时间维度] what_happened_at / session_summary 只在「importance 前 50 | `i179-what-happened-at` |
| #180 | open | [core/time_core] cred_step 参数语义与 cred_factor 返回值反转，混用导致离散指数核单步归零 | `i180-cred-step` |
| #181 | open | [core/存储] tags 列用默认 ensure_ascii 写入：中文标签存成 \uXXXX，get_nodes_by_tag/tag | `i181-cjk-tag` |
| #182 | open | [core/self][自我层] SelfModel.update 是无门控的 setattr，且「先改内存、后落快照」：价值观/身份/信任 | `i182-self-nonatomic`, `i182-self-overwrite` |
| #183 | open | [core/存储] 标签检索用 LIKE '%tag%' 且不转义 %/_：ent:car_1 命中 ent:car_12 与 ent:ca | `i183-search-wildcard`, `i183-tag-like` |
| #184 | open | [core/事务] 写方法无事务边界：中途异常后连接停在未提交事务里，持有写锁（其他连接 database is locked），半截改动被 | `i184-autodecay-dies`, `i184-tx-lock` |
| #185 | open | [core/数值] 浮点入参零校验：NaN 存成 NULL 永不遗忘且让边衰减每轮抛 TypeError，inf 永生并霸占 ORDER B | `i185-inf-importance`, `i185-nan-edge`, `i185-nan-importance` |
| #191 | open | [core/self][权限] SELF 层被并入 IMMUTABLE_LAYERS（共享层写权限），与 Role 章程「SELF＝本地层」 | `i191-sub-self` |
| #195 | closed | [core/longterm_gate] 长期层关联边从未建成：`relation_type` 传字符串致 `add_edge` 抛 `At | —（与 #44 同根（relation_type 传字符串），由 i44-gate-links 覆盖） |
| #199 | closed | [core/activation] `ActivationEngine` 空查询把全图节点当种子并给满分——静默返回「全部命中」错答 | `i199-activation-empty-query` |
| #200 | open | [core/P1-3 技能] record_action_sequence 用 LIKE 子串认技能：「备份」的步骤被追加进「删除备份」（程 | `i200-skill-failure`, `i200-skill-substring`, `i200-skill-wildcard` |
| #201 | open | [core/self][检索] 自我快照以普通记忆身份参与检索且不可删除：每次 update_self / update_trust_sta | `i201-self-recall`, `i201-self-unbounded` |
| #205 | open | [core/self][遗忘] decay_cycle 的边衰减只排除 anchor/structure、漏掉 SELF：update_se | `i205-self-edge-decay` |
| #206 | open | [core/self][信任状态×长期门控] update_trust_state 声称「仅记录，不参与决策」，却对 t_total 零值域 | `i206-trust-gate`, `i206-trust-nan` |
| #207 | open | [core/衰减] decay_cycle 情境层只处理 importance > min_confidence 的节点：importanc | `i207-low-imp-context` |
| #208 | open | [core/飞轮] _note_reuse 每次检索把本轮累计的整个 bucket 重新插入 flywheel_reuse：同轮同节点重复计 | —（只在内部计数器 _reuse_tracker / flywheel_reuse 表上可见，不经公开接口） |
| #210 | open | [core/遗忘] forget_advisor 三处错误：importance=0.0 被 `or 0.5` 当成 0.5 不归档；「降权 | `i210-archive-immortal`, `i210-forget-zero` |
| #212 | open | [core/self][价值观] record_value_change（价值观修正的「正规路径」）会把整个价值观列表替换为单条：细化一条即 | `i212-evolution-bound`, `i212-value-refine` |
| #213 | open | [core/longterm_gate][海马体 H1] 新奇检测对非汉字内容失明：英文/代码/假名/韩文/西里尔 novelty 恒为 0 | `i213-novelty-english`, `i213-novelty-identifier`, `i213-novelty-repeat-en` |
| #214 | open | [core/海马体·睡眠巩固] 情境层→长期层的巩固通路整条不存在：门控的「情境层」判定不落库、promote_context_memori | `i214-promote-context` |
| #215 | open | [core/因果推理] #145 修复后仍有两处缺口：①self_check 的 has_causal_cycle 与 find_cycle | `i215-cycle-consistency`, `i215-selfcheck-time` |
| #216 | open | [core/负记忆][A-1] 被拒路径表是只写黑洞：行动、固化、召回、激活前没有任何一处查负记忆——设计者已否决的提案原文重提即写入结构层 | `i216-failure-importance`, `i216-rejected-resubmit`, `i216-skill-from-failures` |
| #217 | open | [core/longterm_gate][海马体·快照] write_snapshot 的「已存在→更新」分支不看层、不看角色，直接用裸 S | `i217-sub-snapshot` |
| #222 | open | [core/D-007] 盲区闭环的设计者密钥只加在引擎门面：同一对象的 store.resolve_blindspot / store.u | `i222-blindspot-bypass` |
| #223 | open | [core/记忆] add_perception 的 M5 去重命中时丢弃新输入的 entities / tags / importance | `i223-dedup-importance`, `i223-dedup-modality`, `i223-dedup-tags` |
| #224 | open | [core/longterm_gate] write_snapshot 返回的 layer 与实际落库层不一致：hint<0.4 报 con | `i224-context-hit`, `i224-receipt-layer` |
| #225 | open | [core/负记忆][M5×P1-3] M5 去重无视成败极性：同一操作序列的失败经验被并进「成功」节点并给它增信（5 次失败把成功节点置信 | `i225-polarity` |
| #229 | open | [core/activation][负记忆] 激活引擎没有任何抑制通路：OPPOSITE（矛盾）边按 0.5 兴奋传导，被三条证据同时反驳的 | `i229-activation-opposite` |
| #234 | open | [core/权限] 边、标签、保护、冲突登记不做角色检查：SUB 可在结构层节点间新增「已验证」永不衰减的边，也能改写、删除 PRIMARY | `i234-sub-edge-structure`, `i234-sub-protect`, `i234-sub-tag-structure` |
| #243 | open | [core/world 门面] spacetime_consistency / world_model / world_learner /  | `i243-facade-init` |
| #244 | open | [core/权限][结构层] 边接口零角色/零层守卫：SUB 可经公开 add_edge/verify_edge 在锚点/结构层之间注入「已 | `i244-sub-edge-overwrite` |
| #246 | open | core/情境层·M4] 情境层容量上限只活在进程内存里，FIFO 淘汰却作用于持久库：一次普通重启后的第一条 add_context 静默 | `i246-cap-float`, `i246-cap-restart` |
| #252 | open | [core/因果推理] #145 后续：self_check 并非「不受影响」——有环即调用 find_cycles 全枚举，11 节点互为 | `i252-dense-scc`, `i252-find-cycles-budget` |
| #257 | open | [core/情境层·遗忘] 保护名单只增不减，decay_cycle 却把它展开成 2N 个 SQL 占位符：长期记忆累计超过 16383  | `i257-protect-ghost`, `i257-protect-many` |
| #258 | open | [core/巩固周期] consolidate_cycle 用 query_nodes(limit=1000) 且按 importance  | `i258-consolidate-1000` |

## 未写探针的 issue

- #53：静态契约（cond_match 全仓零调用、docstring 公式与实现不符）：无行为读数可测，留给代码质量/评审
- #103：#29 的复核报告，读数与 #29 相同 → 由 i29-* / i142-* 覆盖
- #133：条件域『声明↔求值』反驳机制的设计缺失（需维护者裁决口径），无固定判据
- #169：架构层：13 个『器官』模块不在仓内、组件静默为 None；判据依赖实现内部属性，不写行为探针
- #195：与 #44 同根（relation_type 传字符串），由 i44-gate-links 覆盖
- #208：只在内部计数器 _reuse_tracker / flywheel_reuse 表上可见，不经公开接口

## 未纳入的 issue

非 core 的 nn / gen / world（非 core 门面）/ tools / ci / docs / packaging 类 issue 不在本榜（ng 只重写记忆引擎）；
其中 world/nn 的既有复现保留在 bench/probes 旧探针附表里。
