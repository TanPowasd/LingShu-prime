// dsh-auto-memory 0.7.0 · 宿主仿真驱动（Host emulation driver）
//
// 在真实 Cordis 栈上挂载真实插件包（npm tarball 的 lib/index.js），用 DSH 0.2.0-rc.2 自带的
// 真实 @deepseek-ai/{cordis,dsh-system-prompt,dsh-tools,dsh-llm,dsh-atomic-write} 实现。
// 仿真的只有三件事（如实声明，见 README_适配器.md §3）：
//   ① 会话事件流：把语料轮次按 dsh 事件形状 emit 为 'session/event'（user/message、assistant/message）；
//   ② 会话结束：emit 'agent/disposed'（根会话、delegationDepth=0、provider/model 路由字段）；
//   ③ llm 服务：ctx.reflect.provide('llm', {stream}) —— stream 把插件的固化请求经 stdout 交给
//      Python 侧（harness/llm.py 匀速闸 → Cline flash），或在 replay 模式下回放本运行已缓存的输出。
// 插件自身的 captureText / appendCapped / buildConsolidationPrompt / parseCandidates / sanitize /
// decideConsolidationAction / store.write（文件锁 + 原子写 + 索引重建）/ renderMemoryIndexText（预算截断、
// 协议壳）全部是插件真实代码，未改一行。
//
// 协议：stdin 第一行 = job JSON；之后 stdin 每行 = 对 @@REQ 的应答（@@RESP {...}）。
// stdout：@@REQ {...} / @@EVT {...} / @@DONE {...}。其余输出视为日志。
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { createHash } from 'node:crypto'
import readline from 'node:readline'
import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import * as autoMemory from 'dsh-auto-memory'

const rl = readline.createInterface({ input: process.stdin })
const lines = []
const waiters = []
rl.on('line', l => { if (waiters.length) waiters.shift()(l); else lines.push(l) })
const nextLine = () => new Promise(r => { if (lines.length) r(lines.shift()); else waiters.push(r) })
const out = (tag, obj) => process.stdout.write(`${tag} ${JSON.stringify(obj)}\n`)

function manifest(root) {
  const files = []
  if (!existsSync(root)) return files
  const walk = d => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, e.name)
      if (e.isDirectory()) walk(p)
      else files.push({ path: p.slice(root.length + 1), bytes: statSync(p).size, sha256: createHash('sha256').update(readFileSync(p)).digest('hex') })
    }
  }
  walk(root)
  return files.sort((a, b) => (a.path < b.path ? -1 : 1))
}

const sleep = ms => new Promise(r => setTimeout(r, ms))

async function main() {
  const job = JSON.parse(await nextLine())
  const cfg = { maxBytes: 4096, memoryDir: job.memoryDir, enableUserScope: true, autoSummarize: true,
    autoSummarizeMaxMemories: 5, autoSummarizeMaxTokens: 2048, staleAfterDays: 0, ...(job.config || {}) }
  const ctx = new Context()
  await ctx.plugin(SystemPrompt, {})
  await ctx.plugin(ToolRuntime, {})
  let streamState = null   // {called, done}
  const llm = {
    async *stream(request) {
      streamState.called = true
      const prompt = request.messages.map(m => m.content.filter(b => b.type === 'text').map(b => b.text).join('\n')).join('\n')
      let text
      if (streamState.replay !== undefined) {
        text = streamState.replay
        out('@@EVT', { type: 'llm.replay', session: streamState.sid, prompt_sha256: createHash('sha256').update(prompt).digest('hex'), prompt_chars: prompt.length, text_chars: text.length })
      } else {
        out('@@REQ', { session: streamState.sid, provider: request.provider, model: request.model, maxTokens: request.maxTokens, prompt })
        const resp = JSON.parse((await nextLine()).replace(/^@@RESP /, ''))
        if (resp.error) {
          streamState.done = true
          yield { type: 'finish', reason: { kind: 'error', error: new Error(resp.error) } }
          return
        }
        text = resp.text
      }
      yield { type: 'block-start', index: 0, blockType: 'text' }
      yield { type: 'text-delta', index: 0, text }
      yield { type: 'block-end', index: 0, block: { type: 'text', text } }
      streamState.done = true
      yield { type: 'finish', reason: { kind: 'stop' } }
    },
  }
  ctx.reflect.provide('llm', llm)
  const result = { sessions: [] }
  for (const s of job.sessions) {
    // 每个会话重新挂载插件（等价于每会话一次宿主进程生命周期；记忆只在磁盘上延续）
    const fiber = await ctx.plugin(autoMemory, cfg)
    const session = { id: `sess-${s.id}`, header: { cwd: job.cwd, delegationDepth: 0 } }
    for (const t of s.turns) {
      const content = [{ type: 'text', text: t.text }]
      if (t.role === 'user') {
        ctx.emit('session/event', session, { type: 'user/message', data: createUserMessage({ content, source: { kind: 'user' } }) })
      } else if (t.role === 'assistant') {
        ctx.emit('session/event', session, { type: 'assistant/message', data: { message: { role: 'assistant', content } } })
      }
    }
    streamState = { sid: s.id, called: false, done: false, ...(s.replay !== undefined ? { replay: s.replay } : {}) }
    const before = manifest(job.memoryDir)
    ctx.emit('agent/disposed', { agent: { session, options: { provider: job.provider || 'cline-bridge', model: job.model || 'cline-pass/deepseek-v4.1-flash' } } })
    // 等待插件发起固化调用（其 async 任务先 await store.listAll）；无调用（缓冲为空等）3 s 后视为未触发
    for (let i = 0; i < 300 && !streamState.called; i++) await sleep(10)
    for (let i = 0; i < 360000 && streamState.called && !streamState.done; i++) await sleep(5)
    // 卸载 fiber：插件 effect teardown 会 abort（此时流已结束，不影响）并排空在途写入任务
    await fiber.dispose()
    const after = manifest(job.memoryDir)
    result.sessions.push({ id: s.id, llm_called: streamState.called, replay: s.replay !== undefined, files_before: before.length, files_after: after.length })
  }
  // 注入段：真实 SystemPrompt.assemble，agent 上下文给 cwd
  const fiber = await ctx.plugin(autoMemory, { ...cfg, autoSummarize: false })
  const assembly = await ctx.systemPrompt.assemble({ agent: { session: { id: 'probe', header: { cwd: job.cwd } } } })
  const sec = assembly.sections.find(x => x.name === 'memory:index')
  result.section = sec ? sec.text : null
  result.section_bytes = sec ? Buffer.byteLength(sec.text, 'utf8') : 0
  result.all_sections = assembly.sections.map(x => ({ name: x.name, bytes: Buffer.byteLength(x.text || '', 'utf8') }))
  result.tools = assembly.tools.map(t => t.name)
  await fiber.dispose()
  result.manifest = manifest(job.memoryDir)
  out('@@DONE', result)
  await ctx.fiber.dispose?.()
  process.exit(0)
}

main().catch(e => { out('@@DONE', { fatal: String(e && e.stack || e) }); process.exit(1) })
