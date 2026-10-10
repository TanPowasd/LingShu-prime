# dsh-auto-memory 适配器说明（plugins/dsh-auto-memory/）

被测：<https://github.com/AskTheWay/dsh-auto-memory> —— npm `dsh-auto-memory@0.7.0`
（tarball sha256 `83dd3b98…7e99`，integrity `sha512-0LpHFXmd…MBg==`，`lib/index.js` sha256 `bd7d79ea…1858`），
git tag `v0.7.0` = commit `08972390f9ebb3bfe7acf394d0b18748c4de449d`（2026-10-09 00:16 +0800）。

| 文件 | 作用 |
|:--|:--|
| `install_recorded.py` | 真实宿主安装录像：`npm i -g @deepseek-ai/dsh@0.2.0-rc.2` → README 原命令 `dsh plugin --profile demo add dsh-auto-memory` → `--dump-config` 核对插件进入 profile |
| `host_emu.mjs` | 宿主仿真驱动（node）：真实 Cordis 栈上挂载真实插件包 |
| `emu.py` | Python 侧：准备 node 运行目录（链接真实宿主依赖、拷 tarball 包并校验哈希）、桥接插件固化调用到 Cline（harness/llm.py 匀速闸） |
| `run_pairs.py` | 预注册 B0/P 配对执行器（逐卡落盘、断点续跑、无效整对重跑） |
| `run_loop_dam.sh` | 后台续跑外壳（flock 单实例） |
| `verify_state.py` | 快照契约 dam-snap-v1 的独立校验脚本（不 import 运行/恢复代码，不信任自报） |
| `analyze.py` | 汇总：scores → verdict_v3、baseline-report、证据 manifest |

`_src/`（git clone）、`_pkg/`（tarball 解包）、`_sbx/`（宿主安装与仿真目录）不入库，可按上述哈希复现。

## 1 为什么是宿主仿真

真实宿主装得上（`install/` 录像：DSH 0.2.0-rc.2 全局安装 540 包、插件 add 成功、`--dump-config` 里出现 `id: auto-memory`）。
但考卷 B 要把 16 份**历史**对话灌进记忆：真实宿主的会话只能由真实 agent 循环逐轮生成，无法把既成历史作为“过去的会话”回放；
宿主的模型供应商是 DeepSeek Anthropic-Messages 端点（`dsh-llm-deepseek-api-key`），本站只有 Cline（OpenAI 形）且须走匀速闸。
所以执行时用**宿主仿真**：

**真实（未改一行）**：插件包 `lib/index.js`（apply / 工具注册 / 注入段 / 固化 / store / matching）、`@deepseek-ai/cordis 4.0.4`、`dsh-system-prompt`、`dsh-tools`、`dsh-llm`（`createUserMessage`、`BlockAssembler`）、`dsh-atomic-write`、`dsh-home-paths`、`schemastery`、`yaml`——全部取自真实宿主安装目录。

**仿真（偏差如实列出）**：
1. 会话事件：语料每轮 → `ctx.emit('session/event', session, {type:'user/message'|'assistant/message'})`；用户消息用 `createUserMessage({source:{kind:'user'}})`；说话人标记行转成 role（纯格式）。AI 轮里的推理块原样作为 text（真实宿主中推理是独立块、不被插件捕获——仿真里会被截到 500 字进缓冲，偏差方向不明）。
2. 会话结束：`ctx.emit('agent/disposed', {agent:{session, options:{provider, model}}})`，根会话、`delegationDepth=0`。
3. `llm` 服务：`ctx.reflect.provide('llm', {stream})`；stream 把插件请求交 Python → Cline flash（T=0.7、max_tokens=插件给的 2048、thinking off），再按 dsh-llm chunk 形（block-start / text-delta / block-end / finish）喂回插件自己的 `BlockAssembler`。真实宿主还会叠加 `dsh-llm-retry`、供应商路由、计量等，这里没有。
4. 每会话重新挂载插件 fiber；等插件的固化流结束后 `fiber.dispose()`（插件 teardown 先 abort——此时流已结束——再排空写入），记忆只在磁盘上延续。
5. **没有 agent 循环**：模型不能调用 `memory_read`/`memory_write`，所以 P 只得到注入段（索引：标题+一行描述），读不到记忆正文。对插件是偏保守的下界。
6. 阶段 A 每份语料单独固化时“已有记忆名”为空；阶段 B 回放这些输出时插件看到的是已有记忆（更新/去重真实发生，但模型当初没看到已有名单）。
7. 16 份语料视为同一工作区（同一 cwd）；`_user` 作用域也注入。

## 2 B0 / P

- B0：harness 考卷 B 底子臂原样（`examB.GEN_SYSTEM` + `examB.gen_messages(card, [])`）。
- P：同上，system 后追加 `SystemPrompt.assemble({agent:{session:{header:{cwd}}}})` 得到的 `memory:index` 段（≤4,096 字节，含写入指导与 `<memory_context>` 壳）。段为空时与 B0 逐字节相同。
- 防泄题：本卡语料只固化答案行之前的轮次；其它 15 份整份固化（沿用 SPEC v0.1 §4『其它文件 → 保留』，语料先后未知，对 P 有利，已登记）。

## 3 状态与恢复

见 `validation/dam-20261010T1045/state-inventory.json`。每卡、每份阶段 A 语料都用独立空记忆根，作业前 `verify_state.py card-pre`、作业后 `card-post`（Python 重算清单哈希对比 node 自报、无 .lock/.tmp 残留、索引行都指向真实文件）；每次运行前 `run-pre`（state 目录为空、无残留 node 进程、宿主目录无 memory/sessions、插件包哈希未变）。
