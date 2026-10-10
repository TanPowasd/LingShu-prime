# dsh-memory 隔离安装 · 录像时间轴 · · dsh_install

源：`install.jsonl`，共 81 个事件。时间轴为单调钟 mm:ss（续跑累加），墙钟见右列。

| mm:ss | #seq | 墙钟(CST) | 事件 | 摘要 |
|:--|--:|:--|:--|:--|
| 00:00 | 1 | 00:51:34.360 | rec_start | {"mmss": "00:00", "title": "dsh-memory 隔离安装"} |
| 00:00 | 2 | 00:51:34.360 | env | {"mmss": "00:00", "base": "/tmp/pes-dshm", "HOME": "/tmp/pes-dshm/home", "MDCG_ROOT": "/tmp/pes-dshm/root", "venv": "/tmp/pes-dshm/venv", "sha": "c8c3655234d572 |
| 00:00 | 3 | 00:51:34.362 | snapshot | {"mmss": "00:00", "which": "before", "files": 0} |
| 00:00 | 4 | 00:51:34.362 | step | {"mmss": "00:00", "name": "S0 建 venv（隔离用，非 README 步骤）", "doc": ""} |
| 00:00 | 5 | 00:51:34.362 | cmd_start | {"mmss": "00:00", "step": "S0 建 venv（隔离用，非 README 步骤）", "cmd": "/usr/local/bin/python3 -m venv /tmp/pes-dshm/venv", "cwd": "/tmp/pes-dshm/work"} |
| 00:01 | 6 | 00:51:36.076 | cmd_end | {"mmss": "00:01", "step": "S0 建 venv（隔离用，非 README 步骤）", "rc": 0, "secs": 1.714, "stdout": "", "stderr": ""} |
| 00:01 | 7 | 00:51:36.077 | step | {"mmss": "00:01", "name": "S1 git clone（README 手工步骤①）", "doc": "README §快速开始 ①"} |
| 00:01 | 8 | 00:51:36.077 | cmd_start | {"mmss": "00:01", "step": "S1 git clone（README 手工步骤①）", "cmd": "git clone https://github.com/FuRongJun-1999/dsh-memory.git && cd dsh-memory && git checkout -q c |
| 00:04 | 9 | 00:51:38.604 | cmd_end | {"mmss": "00:04", "step": "S1 git clone（README 手工步骤①）", "rc": 0, "secs": 2.528, "stdout": "c8c3655234d57214ae990ab2c7590f7ba590d901\n", "stderr": "Cloning into  |
| 00:04 | 10 | 00:51:38.605 | step | {"mmss": "00:04", "name": "S2 npx init（README「一键配置（推荐）」，非交互，--end generic）", "doc": "README §一键配置"} |
| 00:04 | 11 | 00:51:38.605 | cmd_start | {"mmss": "00:04", "step": "S2 npx init（README「一键配置（推荐）」，非交互，--end generic）", "cmd": "npx @furongjun1999/dsh-memory init -- --end generic --root /tmp/pes-dshm/ro |
| 00:06 | 12 | 00:51:40.999 | cmd_end | {"mmss": "00:06", "step": "S2 npx init（README「一键配置（推荐）」，非交互，--end generic）", "rc": 0, "secs": 2.394, "stdout": "", "stderr": "npm notice\nnpm notice New major v |
| 00:06 | 13 | 00:51:40.999 | step | {"mmss": "00:06", "name": "S2b 本地仓内 init CLI（lib/ 是否随仓提供）", "doc": ""} |
| 00:06 | 14 | 00:51:40.999 | cmd_start | {"mmss": "00:06", "step": "S2b 本地仓内 init CLI（lib/ 是否随仓提供）", "cmd": "ls lib 2>&1 \| head; ls lib/init.js 2>&1", "cwd": "/tmp/pes-dshm/work/dsh-memory"} |
| 00:06 | 15 | 00:51:41.006 | cmd_end | {"mmss": "00:06", "step": "S2b 本地仓内 init CLI（lib/ 是否随仓提供）", "rc": 2, "secs": 0.007, "stdout": "ls: cannot access 'lib': No such file or directory\nls: cannot ac |
| 00:06 | 16 | 00:51:41.006 | step | {"mmss": "00:06", "name": "S3 python3 -m md_cg.mcp_server --show-config（README 装后验证/写入凭据节）", "doc": ""} |
| 00:06 | 17 | 00:51:41.006 | cmd_start | {"mmss": "00:06", "step": "S3 python3 -m md_cg.mcp_server --show-config（README 装后验证/写入凭据节）", "cmd": "python3 -m md_cg.mcp_server --show-config", "cwd": "/tmp/pe |
| 00:06 | 18 | 00:51:41.261 | cmd_end | {"mmss": "00:06", "step": "S3 python3 -m md_cg.mcp_server --show-config（README 装后验证/写入凭据节）", "rc": 0, "secs": 0.254, "stdout": "{\"server\": \"mdcg-mcp\", \"ver |
| 00:06 | 19 | 00:51:41.261 | step | {"mmss": "00:06", "name": "S4 README 令牌命令原样照抄（Windows 续行符 ^）", "doc": "README §写入凭据 的代码块为 Windows cmd 语法"} |
| 00:06 | 20 | 00:51:41.261 | cmd_start | {"mmss": "00:06", "step": "S4 README 令牌命令原样照抄（Windows 续行符 ^）", "cmd": "python -m md_cg.tokens issue --role designer --actor dsh-memory --clearance internal ^\n  |
| 00:06 | 21 | 00:51:41.325 | cmd_end | {"mmss": "00:06", "step": "S4 README 令牌命令原样照抄（Windows 续行符 ^）", "rc": 127, "secs": 0.065, "stdout": "", "stderr": "usage: python -m md_cg.tokens [-h] [--token-fi |
| 00:06 | 22 | 00:51:41.326 | step | {"mmss": "00:06", "name": "S5 令牌签发 designer（README 参数，Linux 单行）", "doc": ""} |
| 00:06 | 23 | 00:51:41.326 | cmd_start | {"mmss": "00:06", "step": "S5 令牌签发 designer（README 参数，Linux 单行）", "cmd": "python3 -m md_cg.tokens issue --role designer --actor dsh-memory --clearance internal  |
| 00:07 | 24 | 00:51:41.385 | cmd_end | {"mmss": "00:07", "step": "S5 令牌签发 designer（README 参数，Linux 单行）", "rc": 0, "secs": 0.059, "stdout": "rc=0\n{\n \"ok\": true,\n \"token\": \"<REDACTED>\",\n \"to |
| 00:07 | 25 | 00:51:41.385 | step | {"mmss": "00:07", "name": "S6 令牌签发 recorder（README 所称最小权限版）", "doc": ""} |
| 00:07 | 26 | 00:51:41.385 | cmd_start | {"mmss": "00:07", "step": "S6 令牌签发 recorder（README 所称最小权限版）", "cmd": "python3 -m md_cg.tokens issue --role recorder --actor pes-recorder > /tmp/pes-dshm/secrets |
| 00:07 | 27 | 00:51:41.446 | cmd_end | {"mmss": "00:07", "step": "S6 令牌签发 recorder（README 所称最小权限版）", "rc": 0, "secs": 0.061, "stdout": "rc=0\n{\n \"ok\": true,\n \"token\": \"<REDACTED>\",\n \"token_ |
| 00:07 | 28 | 00:51:41.447 | token_saved | {"mmss": "00:07", "role": "designer", "path": "/tmp/pes-dshm/secrets/designer.token", "shown": "<REDACTED>"} |
| 00:07 | 29 | 00:51:41.447 | token_saved | {"mmss": "00:07", "role": "recorder", "path": "/tmp/pes-dshm/secrets/recorder.token", "shown": "<REDACTED>"} |
| 00:07 | 30 | 00:51:41.447 | step | {"mmss": "00:07", "name": "S7 tokens list + 令牌库位置/权限", "doc": ""} |
| 00:07 | 31 | 00:51:41.447 | cmd_start | {"mmss": "00:07", "step": "S7 tokens list + 令牌库位置/权限", "cmd": "python3 -m md_cg.tokens list 2>&1 \| sed -E 's/mdcg1\\.[A-Za-z0-9._-]+/<REDACTED>/g' \| head -40; l |
| 00:07 | 32 | 00:51:41.509 | cmd_end | {"mmss": "00:07", "step": "S7 tokens list + 令牌库位置/权限", "rc": 0, "secs": 0.062, "stdout": "{\n \"tokens\": [\n  {\n   \"token_id\": \"tk_cdb88cf25e89\",\n   \"ro |
| 00:07 | 33 | 00:51:41.509 | step | {"mmss": "00:07", "name": "S2c npx init 是否产出（README 承诺打印片段并写 lingshu-mcp-snippet.json）", "doc": ""} |
| 00:07 | 34 | 00:51:41.509 | cmd_start | {"mmss": "00:07", "step": "S2c npx init 是否产出（README 承诺打印片段并写 lingshu-mcp-snippet.json）", "cmd": "ls -la lingshu-mcp-snippet.json 2>&1; echo '--- npx 缓存里的包版本 --- |
| 00:07 | 35 | 00:51:41.513 | cmd_end | {"mmss": "00:07", "step": "S2c npx init 是否产出（README 承诺打印片段并写 lingshu-mcp-snippet.json）", "rc": 0, "secs": 0.004, "stdout": "ls: cannot access 'lingshu-mcp-snipp |
| 00:07 | 36 | 00:51:41.513 | step | {"mmss": "00:07", "name": "S2d 绕过：直接 node 执行 npx 缓存里的 lib/cli.js（证明是符号链接入口判定 bug，源码 29e24da9 已修、npm 包未发）", "doc": ""} |
| 00:07 | 37 | 00:51:41.513 | cmd_start | {"mmss": "00:07", "step": "S2d 绕过：直接 node 执行 npx 缓存里的 lib/cli.js（证明是符号链接入口判定 bug，源码 29e24da9 已修、npm 包未发）", "cmd": "node $HOME/.npm/_npx/*/node_modules/@furongju |
| 00:07 | 38 | 00:51:41.550 | cmd_end | {"mmss": "00:07", "step": "S2d 绕过：直接 node 执行 npx 缓存里的 lib/cli.js（证明是符号链接入口判定 bug，源码 29e24da9 已修、npm 包未发）", "rc": 0, "secs": 0.036, "stdout": "\n灵枢（Lingshu）一键配置  |
| 00:07 | 39 | 00:51:41.550 | step | {"mmss": "00:07", "name": "S8 按 init 片段（surface=kernel，README designer 令牌）握手", "doc": ""} |
| 00:07 | 40 | 00:51:41.550 | cmd_start | {"mmss": "00:07", "step": "S8 按 init 片段（surface=kernel，README designer 令牌）握手", "cmd": "python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py handshake --b |
| 00:08 | 41 | 00:51:43.311 | cmd_end | {"mmss": "00:08", "step": "S8 按 init 片段（surface=kernel，README designer 令牌）握手", "rc": 0, "secs": 1.761, "stdout": "initialize 1.70s {\"name\": \"mdcg-mcp\", \"ve |
| 00:08 | 42 | 00:51:43.311 | step | {"mmss": "00:08", "name": "S9 同上，surface=full（DSH 插件运行时自身用 full）", "doc": ""} |
| 00:08 | 43 | 00:51:43.311 | cmd_start | {"mmss": "00:08", "step": "S9 同上，surface=full（DSH 插件运行时自身用 full）", "cmd": "python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py handshake --base /tmp/pes |
| 00:10 | 44 | 00:51:44.935 | cmd_end | {"mmss": "00:10", "step": "S9 同上，surface=full（DSH 插件运行时自身用 full）", "rc": 0, "secs": 1.624, "stdout": "initialize 1.54s {\"name\": \"mdcg-mcp\", \"version\": \"0 |
| 00:10 | 45 | 00:51:44.946 | step | {"mmss": "00:10", "name": "S10 README designer 令牌（clearance internal）走会话摄取 cg(op=ingest,jsonl)，连做两次看水位", "doc": ""} |
| 00:10 | 46 | 00:51:44.946 | cmd_start | {"mmss": "00:10", "step": "S10 README designer 令牌（clearance internal）走会话摄取 cg(op=ingest,jsonl)，连做两次看水位", "cmd": "python3 /workspace/work/pes/plugins/dsh-memory/ |
| 00:12 | 47 | 00:51:46.446 | cmd_end | {"mmss": "00:12", "step": "S10 README designer 令牌（clearance internal）走会话摄取 cg(op=ingest,jsonl)，连做两次看水位", "rc": 0, "secs": 1.501, "stdout": "initialize 1.45s {\" |
| 00:12 | 48 | 00:51:46.447 | step | {"mmss": "00:12", "name": "S10b 同一 README 令牌改走细粒度工具 mdcg_ingest（ops 白名单不含 ingest，看是否同样被闸）连做两次", "doc": ""} |
| 00:12 | 49 | 00:51:46.447 | cmd_start | {"mmss": "00:12", "step": "S10b 同一 README 令牌改走细粒度工具 mdcg_ingest（ops 白名单不含 ingest，看是否同样被闸）连做两次", "cmd": "python3 /workspace/work/pes/plugins/dsh-memory/probe_cli |
| 00:13 | 50 | 00:51:47.939 | cmd_end | {"mmss": "00:13", "step": "S10b 同一 README 令牌改走细粒度工具 mdcg_ingest（ops 白名单不含 ingest，看是否同样被闸）连做两次", "rc": 0, "secs": 1.492, "stdout": "initialize 1.44s {\"name\": \ |
| 00:13 | 51 | 00:51:47.939 | step | {"mmss": "00:13", "name": "S11 recorder 令牌（README 所称最小权限）走会话摄取", "doc": ""} |
| 00:13 | 52 | 00:51:47.939 | cmd_start | {"mmss": "00:13", "step": "S11 recorder 令牌（README 所称最小权限）走会话摄取", "cmd": "python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest --base /tmp/pes-dshm |
| 00:15 | 53 | 00:51:49.436 | cmd_end | {"mmss": "00:15", "step": "S11 recorder 令牌（README 所称最小权限）走会话摄取", "rc": 0, "secs": 1.497, "stdout": "initialize 1.45s {\"name\": \"mdcg-mcp\", \"version\": \"0.8 |
| 00:15 | 54 | 00:51:49.437 | step | {"mmss": "00:15", "name": "S12 按服务端 hint 补签 designer --clearance private（+ops ingest,session）", "doc": ""} |
| 00:15 | 55 | 00:51:49.437 | cmd_start | {"mmss": "00:15", "step": "S12 按服务端 hint 补签 designer --clearance private（+ops ingest,session）", "cmd": "python3 -m md_cg.tokens issue --role designer --actor pe |
| 00:15 | 56 | 00:51:49.509 | cmd_end | {"mmss": "00:15", "step": "S12 按服务端 hint 补签 designer --clearance private（+ops ingest,session）", "rc": 0, "secs": 0.073, "stdout": "rc=0\n{\n \"ok\": true,\n \"t |
| 00:15 | 57 | 00:51:49.510 | step | {"mmss": "00:15", "name": "S13 private designer 令牌走会话摄取（新库）", "doc": ""} |
| 00:15 | 58 | 00:51:49.510 | cmd_start | {"mmss": "00:15", "step": "S13 private designer 令牌走会话摄取（新库）", "cmd": "python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest --base /tmp/pes-dshm -- |
| 00:17 | 59 | 00:51:51.381 | cmd_end | {"mmss": "00:17", "step": "S13 private designer 令牌走会话摄取（新库）", "rc": 0, "secs": 1.871, "stdout": "initialize 1.45s {\"name\": \"mdcg-mcp\", \"version\": \"0.8.1\ |
| 00:17 | 60 | 00:51:51.381 | step | {"mmss": "00:17", "name": "S13b 同一令牌对 S10 已被拒的库重试（水位是否已被拒绝事件推进）", "doc": ""} |
| 00:17 | 61 | 00:51:51.381 | cmd_start | {"mmss": "00:17", "step": "S13b 同一令牌对 S10 已被拒的库重试（水位是否已被拒绝事件推进）", "cmd": "python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest --base /tmp/pes-dsh |
| 00:18 | 62 | 00:51:53.286 | cmd_end | {"mmss": "00:18", "step": "S13b 同一令牌对 S10 已被拒的库重试（水位是否已被拒绝事件推进）", "rc": 0, "secs": 1.905, "stdout": "initialize 1.50s {\"name\": \"mdcg-mcp\", \"version\": \"0. |
| 00:18 | 63 | 00:51:53.286 | step | {"mmss": "00:18", "name": "S13c 对 S11（recorder 被拒 50/50）的库用 private 令牌重试：被拒事件是否已推进水位", "doc": ""} |
| 00:18 | 64 | 00:51:53.286 | cmd_start | {"mmss": "00:18", "step": "S13c 对 S11（recorder 被拒 50/50）的库用 private 令牌重试：被拒事件是否已推进水位", "cmd": "python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py inges |
| 00:20 | 65 | 00:51:54.773 | cmd_end | {"mmss": "00:20", "step": "S13c 对 S11（recorder 被拒 50/50）的库用 private 令牌重试：被拒事件是否已推进水位", "rc": 0, "secs": 1.487, "stdout": "initialize 1.44s {\"name\": \"mdcg-mcp |
| 00:20 | 66 | 00:51:54.774 | step | {"mmss": "00:20", "name": "S13d 对 S10b 的库用 private 令牌重试", "doc": ""} |
| 00:20 | 67 | 00:51:54.774 | cmd_start | {"mmss": "00:20", "step": "S13d 对 S10b 的库用 private 令牌重试", "cmd": "python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest --base /tmp/pes-dshm --clon |
| 00:21 | 68 | 00:51:56.279 | cmd_end | {"mmss": "00:21", "step": "S13d 对 S10b 的库用 private 令牌重试", "rc": 0, "secs": 1.505, "stdout": "initialize 1.44s {\"name\": \"mdcg-mcp\", \"version\": \"0.8.1\"}\n |
| 00:21 | 69 | 00:51:56.279 | step | {"mmss": "00:21", "name": "S14 DSH 运行时自动记忆缺省通道 mdcg_remember(gated) 逐条写 25 条用户消息：闸门四态+时延", "doc": ""} |
| 00:21 | 70 | 00:51:56.279 | cmd_start | {"mmss": "00:21", "step": "S14 DSH 运行时自动记忆缺省通道 mdcg_remember(gated) 逐条写 25 条用户消息：闸门四态+时延", "cmd": "python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py r |
| 00:23 | 71 | 00:51:57.852 | cmd_end | {"mmss": "00:23", "step": "S14 DSH 运行时自动记忆缺省通道 mdcg_remember(gated) 逐条写 25 条用户消息：闸门四态+时延", "rc": 0, "secs": 1.573, "stdout": "initialize 1.46s {\"name\": \"mdcg |
| 00:23 | 72 | 00:51:57.930 | snapshot | {"mmss": "00:23", "which": "after_install"} |
| 00:23 | 73 | 00:51:57.930 | step | {"mmss": "00:23", "name": "U1 卸载（README 无卸载说明；删 clone 与 venv）", "doc": ""} |
| 00:23 | 74 | 00:51:57.930 | cmd_start | {"mmss": "00:23", "step": "U1 卸载（README 无卸载说明；删 clone 与 venv）", "cmd": "rm -rf /tmp/pes-dshm/work/dsh-memory /tmp/pes-dshm/venv; echo done", "cwd": "/tmp/pes-ds |
| 00:23 | 75 | 00:51:57.975 | cmd_end | {"mmss": "00:23", "step": "U1 卸载（README 无卸载说明；删 clone 与 venv）", "rc": 0, "secs": 0.045, "stdout": "done\n", "stderr": ""} |
| 00:23 | 76 | 00:51:57.975 | step | {"mmss": "00:23", "name": "U2 残留检查：HOME / MDCG_ROOT / 临时目录", "doc": ""} |
| 00:23 | 77 | 00:51:57.975 | cmd_start | {"mmss": "00:23", "step": "U2 残留检查：HOME / MDCG_ROOT / 临时目录", "cmd": "cd /tmp/pes-dshm/home && find . -type f \| sort \| head -80; echo '--- /tmp/md_cg_servers --- |
| 00:23 | 78 | 00:51:57.994 | cmd_end | {"mmss": "00:23", "step": "U2 残留检查：HOME / MDCG_ROOT / 临时目录", "rc": 0, "secs": 0.019, "stdout": "8457f879db267dcad46306b20a64b06dc43c05ac3e93b20c68da0db025c9a96a |
| 00:23 | 79 | 00:51:58.053 | residue | {"mmss": "00:23", "by_top": {"~/.dsh/.dsh-memory": [18, 1995586], "~/.mdcg/_tokens.json": [1, 2201], "~/.mdcg/_tokens.json.lock": [1, 0], "~/.mdcg/master.key":  |
| 00:23 | 80 | 00:51:58.053 | summary | {"mmss": "00:23", "steps": [{"name": "S0 建 venv（隔离用，非 README 步骤）", "cmd": "/usr/local/bin/python3 -m venv /tmp/pes-dshm/venv", "rc": 0, "secs": 1.714}, {"name": |
| 00:23 | 81 | 00:51:58.053 | rec_end | {"mmss": "00:23"} |

---

## 命令输出明细

> 源：`install.jsonl`（JSONL 事件流；mm:ss = 自录像开始的单调钟）

- **[00:00] #1** `rec_start` {"title": "dsh-memory 隔离安装"}
- **[00:00] #2** `env` {"base": "/tmp/pes-dshm", "HOME": "/tmp/pes-dshm/home", "MDCG_ROOT": "/tmp/pes-dshm/root", "venv": "/tmp/pes-dshm/venv", "sha": "c8c3655234d57214ae990ab2c7590f7ba590d901", "note": "按 README「其它 MCP 宿主 → 直接挂载大脑」+「一键配置（推荐）」+「写入凭据」三节走；本机无 DSH 宿主，DSH 专属步骤（dsh plugin add / cordis.yml）不适用，如实标注"}
- **[00:00] #3** `snapshot` {"which": "before", "files": 0}
- **[00:00] #4** `step` {"name": "S0 建 venv（隔离用，非 README 步骤）", "doc": ""}
- **[00:00] #5** `cmd_start` step=S0 建 venv（隔离用，非 README 步骤） ：`/usr/local/bin/python3 -m venv /tmp/pes-dshm/venv`
- **[00:01] #6** `cmd_end` step=S0 建 venv（隔离用，非 README 步骤） rc=0 用时 1.714s
- **[00:01] #7** `step` {"name": "S1 git clone（README 手工步骤①）", "doc": "README §快速开始 ①"}
- **[00:01] #8** `cmd_start` step=S1 git clone（README 手工步骤①） ：`git clone https://github.com/FuRongJun-1999/dsh-memory.git && cd dsh-memory && git checkout -q c8c3655234d57214ae990ab2c7590f7ba590d901 && git log -1 --format=%H`
- **[00:04] #9** `cmd_end` step=S1 git clone（README 手工步骤①） rc=0 用时 2.528s
  <details><summary>stdout（41 字符）</summary>

```
c8c3655234d57214ae990ab2c7590f7ba590d901
```
</details>
  <details><summary>stderr（29 字符）</summary>

```
Cloning into 'dsh-memory'...
```
</details>
- **[00:04] #10** `step` {"name": "S2 npx init（README「一键配置（推荐）」，非交互，--end generic）", "doc": "README §一键配置"}
- **[00:04] #11** `cmd_start` step=S2 npx init（README「一键配置（推荐）」，非交互，--end generic） ：`npx @furongjun1999/dsh-memory init -- --end generic --root /tmp/pes-dshm/root --python /tmp/pes-dshm/venv/bin/python`
- **[00:06] #12** `cmd_end` step=S2 npx init（README「一键配置（推荐）」，非交互，--end generic） rc=0 用时 2.394s
  <details><summary>stderr（208 字符）</summary>

```
npm notice
npm notice New major version of npm available! 10.9.9 -> 12.2.0
npm notice Changelog: https://github.com/npm/cli/releases/tag/v12.2.0
npm notice To update run: npm install -g npm@12.2.0
npm notice
```
</details>
- **[00:06] #13** `step` {"name": "S2b 本地仓内 init CLI（lib/ 是否随仓提供）", "doc": ""}
- **[00:06] #14** `cmd_start` step=S2b 本地仓内 init CLI（lib/ 是否随仓提供） ：`ls lib 2>&1 | head; ls lib/init.js 2>&1`
- **[00:06] #15** `cmd_end` step=S2b 本地仓内 init CLI（lib/ 是否随仓提供） rc=2 用时 0.007s
  <details><summary>stdout（110 字符）</summary>

```
ls: cannot access 'lib': No such file or directory
ls: cannot access 'lib/init.js': No such file or directory
```
</details>
- **[00:06] #16** `step` {"name": "S3 python3 -m md_cg.mcp_server --show-config（README 装后验证/写入凭据节）", "doc": ""}
- **[00:06] #17** `cmd_start` step=S3 python3 -m md_cg.mcp_server --show-config（README 装后验证/写入凭据节） ：`python3 -m md_cg.mcp_server --show-config`
- **[00:06] #18** `cmd_end` step=S3 python3 -m md_cg.mcp_server --show-config（README 装后验证/写入凭据节） rc=0 用时 0.254s
  <details><summary>stdout（208 字符）</summary>

```
{"server": "mdcg-mcp", "version": "0.8.1", "policy": {"source": "package_default", "path": "/tmp/pes-dshm/work/dsh-memory/data/policy.json", "available": true, "forbidden": 12, "required": 6, "error": null}}
```
</details>
- **[00:06] #19** `step` {"name": "S4 README 令牌命令原样照抄（Windows 续行符 ^）", "doc": "README §写入凭据 的代码块为 Windows cmd 语法"}
- **[00:06] #20** `cmd_start` step=S4 README 令牌命令原样照抄（Windows 续行符 ^） ：`python -m md_cg.tokens issue --role designer --actor dsh-memory --clearance internal ^
  --ops-allow info,route,read,write,recent,goal,identity,whitebox,verify ^
  --layers-allow knowledge,contextual,structural,self,goals,unresolved,rejected`
- **[00:06] #21** `cmd_end` step=S4 README 令牌命令原样照抄（Windows 续行符 ^） rc=127 用时 0.065s
  <details><summary>stderr（270 字符）</summary>

```
usage: python -m md_cg.tokens [-h] [--token-file TOKEN_FILE]
                              {issue,derive,orch,verify,revoke,list,roles} ...
python -m md_cg.tokens: error: unrecognized arguments: ^
/bin/sh: 2: --ops-allow: not found
/bin/sh: 3: --layers-allow: not found
```
</details>
- **[00:06] #22** `step` {"name": "S5 令牌签发 designer（README 参数，Linux 单行）", "doc": ""}
- **[00:06] #23** `cmd_start` step=S5 令牌签发 designer（README 参数，Linux 单行） ：`python3 -m md_cg.tokens issue --role designer --actor dsh-memory --clearance internal --ops-allow info,route,read,write,recent,goal,identity,whitebox,verify --layers-allow knowledge,contextual,structural,self,goals,unresolved,rejected > /tmp/pes-dshm/secrets/designer.out 2>&1; echo rc=$?; sed -E 's/mdcg1\.[A-Za-z0-9._-]+/<REDACTED>/g' /tmp/pes-dshm/secrets/designer.out`
- **[00:07] #24** `cmd_end` step=S5 令牌签发 designer（README 参数，Linux 单行） rc=0 用时 0.059s
  <details><summary>stdout（468 字符）</summary>

```
rc=0
{
 "ok": true,
 "token": "<REDACTED>",
 "token_id": "tk_cdb88cf25e89",
 "role": "designer",
 "actor": "dsh-memory",
 "clearance": "internal",
 "layers_allow": [
  "knowledge",
  "contextual",
  "structural",
  "self",
  "goals",
  "unresolved",
  "rejected"
 ],
 "ops_allow": [
  "info",
  "route",
  "read",
  "write",
  "recent",
  "goal",
  "identity",
  "whitebox",
  "verify"
 ],
 "expires_at": null,
 "token_file": "/tmp/pes-dshm/home/.mdcg/_tokens.json"
}
```
</details>
- **[00:07] #25** `step` {"name": "S6 令牌签发 recorder（README 所称最小权限版）", "doc": ""}
- **[00:07] #26** `cmd_start` step=S6 令牌签发 recorder（README 所称最小权限版） ：`python3 -m md_cg.tokens issue --role recorder --actor pes-recorder > /tmp/pes-dshm/secrets/recorder.out 2>&1; echo rc=$?; sed -E 's/mdcg1\.[A-Za-z0-9._-]+/<REDACTED>/g' /tmp/pes-dshm/secrets/recorder.out`
- **[00:07] #27** `cmd_end` step=S6 令牌签发 recorder（README 所称最小权限版） rc=0 用时 0.061s
  <details><summary>stdout（512 字符）</summary>

```
rc=0
{
 "ok": true,
 "token": "<REDACTED>",
 "token_id": "tk_80d4c1e3171a",
 "role": "record",
 "actor": "pes-recorder",
 "clearance": "internal",
 "layers_allow": [
  "knowledge",
  "contextual",
  "structural",
  "unresolved",
  "rejected",
  "goals"
 ],
 "ops_allow": [
  "info",
  "route",
  "read",
  "write",
  "goal",
  "task",
  "recent",
  "session",
  "ingest",
  "maintain",
  "insight",
  "ccg",
  "status",
  "edges"
 ],
 "expires_at": null,
 "token_file": "/tmp/pes-dshm/home/.mdcg/_tokens.json"
}
```
</details>
- **[00:07] #28** `token_saved` {"role": "designer", "path": "/tmp/pes-dshm/secrets/designer.token", "shown": "<REDACTED>"}
- **[00:07] #29** `token_saved` {"role": "recorder", "path": "/tmp/pes-dshm/secrets/recorder.token", "shown": "<REDACTED>"}
- **[00:07] #30** `step` {"name": "S7 tokens list + 令牌库位置/权限", "doc": ""}
- **[00:07] #31** `cmd_start` step=S7 tokens list + 令牌库位置/权限 ：`python3 -m md_cg.tokens list 2>&1 | sed -E 's/mdcg1\.[A-Za-z0-9._-]+/<REDACTED>/g' | head -40; ls -la /tmp/pes-dshm/home/.mdcg 2>&1`
- **[00:07] #32** `cmd_end` step=S7 tokens list + 令牌库位置/权限 rc=0 用时 0.062s
  <details><summary>stdout（915 字符）</summary>

```
{
 "tokens": [
  {
   "token_id": "tk_cdb88cf25e89",
   "role": "designer",
   "actor": "dsh-memory",
   "tenant": "default",
   "clearance": "internal",
   "can_write": true,
   "can_admin": true,
   "layers_allow": [
    "knowledge",
    "contextual",
    "structural",
    "self",
    "goals",
    "unresolved",
    "rejected"
   ],
   "ops_allow": [
    "info",
    "route",
    "read",
    "write",
    "recent",
    "goal",
    "identity",
    "whitebox",
    "verify"
   ],
   "delegable": true,
   "parent": null,
   "label": "",
   "issued_at": 1791564701.3771164,
   "expires_at": null,
   "revoked_at": null
  },
  {
   "token_id": "tk_80d4c1e3171a",
   "role": "record",
total 4
drwxr-xr-x 2 sandbox sandbox   80 Oct  9 16:51 .
drwxr-xr-x 4 sandbox sandbox   80 Oct  9 16:51 ..
-rw------- 1 sandbox sandbox 1480 Oct  9 16:51 _tokens.json
-rw-r--r-- 1 sandbox sandbox    0 Oct  9 16:51 _tokens.json.lock
```
</details>
- **[00:07] #33** `step` {"name": "S2c npx init 是否产出（README 承诺打印片段并写 lingshu-mcp-snippet.json）", "doc": ""}
- **[00:07] #34** `cmd_start` step=S2c npx init 是否产出（README 承诺打印片段并写 lingshu-mcp-snippet.json） ：`ls -la lingshu-mcp-snippet.json 2>&1; echo '--- npx 缓存里的包版本 ---'; grep -m1 '"version"' $HOME/.npm/_npx/*/node_modules/@furongjun1999/dsh-memory/package.json; grep -n 'import.meta.url === entryUrl' $HOME/.npm/_npx/*/node_modules/@furongjun1999/dsh-memory/lib/cli.js`
- **[00:07] #35** `cmd_end` step=S2c npx init 是否产出（README 承诺打印片段并写 lingshu-mcp-snippet.json） rc=0 用时 0.004s
  <details><summary>stdout（161 字符）</summary>

```
ls: cannot access 'lingshu-mcp-snippet.json': No such file or directory
--- npx 缓存里的包版本 ---
  "version": "0.8.1",
52:        return import.meta.url === entryUrl
```
</details>
- **[00:07] #36** `step` {"name": "S2d 绕过：直接 node 执行 npx 缓存里的 lib/cli.js（证明是符号链接入口判定 bug，源码 29e24da9 已修、npm 包未发）", "doc": ""}
- **[00:07] #37** `cmd_start` step=S2d 绕过：直接 node 执行 npx 缓存里的 lib/cli.js（证明是符号链接入口判定 bug，源码 29e24da9 已修、npm 包未发） ：`node $HOME/.npm/_npx/*/node_modules/@furongjun1999/dsh-memory/lib/cli.js init -- --end generic --root /tmp/pes-dshm/root --python /tmp/pes-dshm/venv/bin/python; echo; cat lingshu-mcp-snippet.json | head -30`
- **[00:07] #38** `cmd_end` step=S2d 绕过：直接 node 执行 npx 缓存里的 lib/cli.js（证明是符号链接入口判定 bug，源码 29e24da9 已修、npm 包未发） rc=0 用时 0.036s
  <details><summary>stdout（2172 字符）</summary>

```
灵枢（Lingshu）一键配置 · 端=通用 MCP 宿主
  记忆根目录 MDCG_ROOT：/tmp/pes-dshm/root
  Python 解释器：/tmp/pes-dshm/venv/bin/python

① 把下面的 mcp.json 片段放到：宿主的 MCP server 配置处（command/args/env 三元组，按宿主文档挂载 stdio server）
{
  "mcpServers": {
    "mdcg": {
      "command": "/tmp/pes-dshm/venv/bin/python",
      "args": [
        "-m",
        "md_cg.mcp_server"
      ],
      "env": {
        "PYTHONPATH": "/tmp/pes-dshm/home/.npm/_npx/a583088fe421c43b/node_modules/@furongjun1999/dsh-memory",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "MDCG_ROOT": "/tmp/pes-dshm/root",
        "MDCG_PYTHON": "/tmp/pes-dshm/venv/bin/python",
        "MDCG_MCP_SURFACE": "kernel",
        "MDCG_ACTOR": "generic
…（截断，全文见 JSONL）…
，建议换成 git clone 的常驻仓库绝对路径（免疫 npx 缓存清理）。
init 只生成配置：未创建目录、未启动服务、未写库；重跑输出一致。

{
  "mcpServers": {
    "mdcg": {
      "command": "/tmp/pes-dshm/venv/bin/python",
      "args": [
        "-m",
        "md_cg.mcp_server"
      ],
      "env": {
        "PYTHONPATH": "/tmp/pes-dshm/home/.npm/_npx/a583088fe421c43b/node_modules/@furongjun1999/dsh-memory",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "MDCG_ROOT": "/tmp/pes-dshm/root",
        "MDCG_PYTHON": "/tmp/pes-dshm/venv/bin/python",
        "MDCG_MCP_SURFACE": "kernel",
        "MDCG_ACTOR": "generic",
        "MDCG_TENANT": "default",
        "MDCG_CLEARANCE": "private",
        "MDCG_TOKEN": ""
      }
    }
  }
}
```
</details>
- **[00:07] #39** `step` {"name": "S8 按 init 片段（surface=kernel，README designer 令牌）握手", "doc": ""}
- **[00:07] #40** `cmd_start` step=S8 按 init 片段（surface=kernel，README designer 令牌）握手 ：`python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py handshake --base /tmp/pes-dshm --clone /tmp/pes-dshm/work/dsh-memory --root /tmp/pes-dshm/root --surface kernel --token /tmp/pes-dshm/secrets/designer.token`
- **[00:08] #41** `cmd_end` step=S8 按 init 片段（surface=kernel，README designer 令牌）握手 rc=0 用时 1.761s
  <details><summary>stdout（209 字符）</summary>

```
initialize 1.70s {"name": "mdcg-mcp", "version": "0.8.1"}
tools/list (2): ['cg', 'stg']
principal: {"role": null, "clearance": null, "can_write": null, "can_admin": null, "auth_mode": null, "ops_allow": null}
```
</details>
- **[00:08] #42** `step` {"name": "S9 同上，surface=full（DSH 插件运行时自身用 full）", "doc": ""}
- **[00:08] #43** `cmd_start` step=S9 同上，surface=full（DSH 插件运行时自身用 full） ：`python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py handshake --base /tmp/pes-dshm --clone /tmp/pes-dshm/work/dsh-memory --root /tmp/pes-dshm/root --surface full --token /tmp/pes-dshm/secrets/designer.token`
- **[00:10] #44** `cmd_end` step=S9 同上，surface=full（DSH 插件运行时自身用 full） rc=0 用时 1.624s
  <details><summary>stdout（857 字符）</summary>

```
initialize 1.54s {"name": "mdcg-mcp", "version": "0.8.1"}
tools/list (33): ['cg', 'stg', 'mdcg_remember', 'mdcg_recall', 'mdcg_search', 'mdcg_get', 'mdcg_reflect', 'mdcg_verify', 'mdcg_flywheel', 'mdcg_mine_fix_pairs', 'mdcg_rejected', 'mdcg_unresolved', 'mdcg_propose', 'mdcg_review_list', 'mdcg_review_decide', 'mdcg_review_records', 'mdcg_forget', 'mdcg_protect', 'mdcg_forgetting_history', 'mdcg_identity', 'mdcg_consistency', 'mdcg_metacognition', 'mdcg_self_state', 'mdcg_predict', 'mdcg_causal', 'mdcg_evolution', 'mdcg_restore', 'mdcg_health', 'mdcg_whoami', 'mdcg_ingest', 'mdcg_watermarks', 'mdcg_whitebox', 'mdcg_service_info']
principal: {"role": "designer", "clearance": "internal", "can_write": true, "can_admin": true, "auth_mode": "token", "ops_allow": ["info", "route", "read", "write", "recent", "goal", "identity", "whitebox", "verify"]}
```
</details>
- **[00:10] #45** `step` {"name": "S10 README designer 令牌（clearance internal）走会话摄取 cg(op=ingest,jsonl)，连做两次看水位", "doc": ""}
- **[00:10] #46** `cmd_start` step=S10 README designer 令牌（clearance internal）走会话摄取 cg(op=ingest,jsonl)，连做两次看水位 ：`python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest --base /tmp/pes-dshm --clone /tmp/pes-dshm/work/dsh-memory --root /tmp/pes-dshm/probe_root_a --token /tmp/pes-dshm/secrets/designer.token --jsonl /tmp/pes-dshm/probe_session.jsonl --repeat 2`
- **[00:12] #47** `cmd_end` step=S10 README designer 令牌（clearance internal）走会话摄取 cg(op=ingest,jsonl)，连做两次看水位 rc=0 用时 1.501s
  <details><summary>stdout（928 字符）</summary>

```
initialize 1.45s {"name": "mdcg-mcp", "version": "0.8.1"}
ingest#1 0.00s isError=True {"new_events": null, "written": null, "denied": null, "sensitivity": null, "last_error": null, "hint": "当前令牌（actor=dsh-memory，角色 designer）的 ops 白名单不含 ingest，属正常闸门不是故障。可：①换用含该 op 的角色令牌；②由签发者以 --ops-allow 补授权后重新签发（python -m md_cg.tokens issue …，README「写入凭据」一节）。", "error": "AccessDenied: 角色 designer 无权执行 op=ingest（作用域 ['info', 'route', 'read', 'write', 'recent', 'goal', 'identity', 'whitebox', 'verify']）"}
ingest#2 0.00s isError=True {"new_events": null, "written": null, "denied": null, "sensitivity": null, "last_error": null, "hint": "当前令牌（actor=dsh-memory，角色 designer）的 ops 白名单不含 ingest，属正常闸门不是故障。可：①换用含该 op 的角色令牌；②由签发者以 --ops-allow 补授权后重新签发（python -m md_cg.tokens issue …，README「写入凭据」一节）。", "error": "AccessDenied: 角色 designer 无权执行 op=ingest（作用域 ['info', 'route', 'read', 'write', 'recent', 'goal', 'identity', 'whitebox', 'verify']）"}
```
</details>
- **[00:12] #48** `step` {"name": "S10b 同一 README 令牌改走细粒度工具 mdcg_ingest（ops 白名单不含 ingest，看是否同样被闸）连做两次", "doc": ""}
- **[00:12] #49** `cmd_start` step=S10b 同一 README 令牌改走细粒度工具 mdcg_ingest（ops 白名单不含 ingest，看是否同样被闸）连做两次 ：`python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest_fine --base /tmp/pes-dshm --clone /tmp/pes-dshm/work/dsh-memory --root /tmp/pes-dshm/probe_root_e --token /tmp/pes-dshm/secrets/designer.token --jsonl /tmp/pes-dshm/probe_session.jsonl --repeat 2`
- **[00:13] #50** `cmd_end` step=S10b 同一 README 令牌改走细粒度工具 mdcg_ingest（ops 白名单不含 ingest，看是否同样被闸）连做两次 rc=0 用时 1.492s
  <details><summary>stdout（387 字符）</summary>

```
initialize 1.44s {"name": "mdcg-mcp", "version": "0.8.1"}
mdcg_ingest#1 0.00s isError=False {"new_events": 50, "written": 0, "denied": 50, "sensitivity": "private", "last_error": "AccessDenied: 写入敏感度 private 超出 clearance internal", "error": null}
mdcg_ingest#2 0.00s isError=False {"new_events": 0, "written": 0, "denied": 0, "sensitivity": "private", "last_error": null, "error": null}
```
</details>
- **[00:13] #51** `step` {"name": "S11 recorder 令牌（README 所称最小权限）走会话摄取", "doc": ""}
- **[00:13] #52** `cmd_start` step=S11 recorder 令牌（README 所称最小权限）走会话摄取 ：`python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest --base /tmp/pes-dshm --clone /tmp/pes-dshm/work/dsh-memory --root /tmp/pes-dshm/probe_root_b --token /tmp/pes-dshm/secrets/recorder.token --jsonl /tmp/pes-dshm/probe_session.jsonl`
- **[00:15] #53** `cmd_end` step=S11 recorder 令牌（README 所称最小权限）走会话摄取 rc=0 用时 1.497s
  <details><summary>stdout（313 字符）</summary>

```
initialize 1.45s {"name": "mdcg-mcp", "version": "0.8.1"}
ingest#1 0.00s isError=False {"new_events": 50, "written": 0, "denied": 50, "sensitivity": "private", "last_error": "AccessDenied: 写入敏感度 private 超出 clearance internal", "hint": "会话内容默认 sensitivity=private；调用方需 MDCG_CLEARANCE=private 才能写入", "error": null}
```
</details>
- **[00:15] #54** `step` {"name": "S12 按服务端 hint 补签 designer --clearance private（+ops ingest,session）", "doc": ""}
- **[00:15] #55** `cmd_start` step=S12 按服务端 hint 补签 designer --clearance private（+ops ingest,session） ：`python3 -m md_cg.tokens issue --role designer --actor pes-dsh --clearance private --ops-allow info,route,read,write,recent,goal,identity,whitebox,verify,ingest,session --layers-allow knowledge,contextual,structural,self,goals,unresolved,rejected > /tmp/pes-dshm/secrets/designer_private.out 2>&1; echo rc=$?; sed -E 's/mdcg1\.[A-Za-z0-9._-]+/<REDACTED>/g' /tmp/pes-dshm/secrets/designer_private.out | head -8`
- **[00:15] #56** `cmd_end` step=S12 按服务端 hint 补签 designer --clearance private（+ops ingest,session） rc=0 用时 0.073s
  <details><summary>stdout（162 字符）</summary>

```
rc=0
{
 "ok": true,
 "token": "<REDACTED>",
 "token_id": "tk_5d367dc8f831",
 "role": "designer",
 "actor": "pes-dsh",
 "clearance": "private",
 "layers_allow": [
```
</details>
- **[00:15] #57** `step` {"name": "S13 private designer 令牌走会话摄取（新库）", "doc": ""}
- **[00:15] #58** `cmd_start` step=S13 private designer 令牌走会话摄取（新库） ：`python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest --base /tmp/pes-dshm --clone /tmp/pes-dshm/work/dsh-memory --root /tmp/pes-dshm/probe_root_c --token /tmp/pes-dshm/secrets/designer_private.token --jsonl /tmp/pes-dshm/probe_session.jsonl`
- **[00:17] #59** `cmd_end` step=S13 private designer 令牌走会话摄取（新库） rc=0 用时 1.871s
  <details><summary>stdout（209 字符）</summary>

```
initialize 1.45s {"name": "mdcg-mcp", "version": "0.8.1"}
ingest#1 0.35s isError=False {"new_events": 50, "written": 50, "denied": 0, "sensitivity": "private", "last_error": null, "hint": null, "error": null}
```
</details>
- **[00:17] #60** `step` {"name": "S13b 同一令牌对 S10 已被拒的库重试（水位是否已被拒绝事件推进）", "doc": ""}
- **[00:17] #61** `cmd_start` step=S13b 同一令牌对 S10 已被拒的库重试（水位是否已被拒绝事件推进） ：`python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest --base /tmp/pes-dshm --clone /tmp/pes-dshm/work/dsh-memory --root /tmp/pes-dshm/probe_root_a --token /tmp/pes-dshm/secrets/designer_private.token --jsonl /tmp/pes-dshm/probe_session.jsonl`
- **[00:18] #62** `cmd_end` step=S13b 同一令牌对 S10 已被拒的库重试（水位是否已被拒绝事件推进） rc=0 用时 1.905s
  <details><summary>stdout（209 字符）</summary>

```
initialize 1.50s {"name": "mdcg-mcp", "version": "0.8.1"}
ingest#1 0.35s isError=False {"new_events": 50, "written": 50, "denied": 0, "sensitivity": "private", "last_error": null, "hint": null, "error": null}
```
</details>
- **[00:18] #63** `step` {"name": "S13c 对 S11（recorder 被拒 50/50）的库用 private 令牌重试：被拒事件是否已推进水位", "doc": ""}
- **[00:18] #64** `cmd_start` step=S13c 对 S11（recorder 被拒 50/50）的库用 private 令牌重试：被拒事件是否已推进水位 ：`python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest --base /tmp/pes-dshm --clone /tmp/pes-dshm/work/dsh-memory --root /tmp/pes-dshm/probe_root_b --token /tmp/pes-dshm/secrets/designer_private.token --jsonl /tmp/pes-dshm/probe_session.jsonl`
- **[00:20] #65** `cmd_end` step=S13c 对 S11（recorder 被拒 50/50）的库用 private 令牌重试：被拒事件是否已推进水位 rc=0 用时 1.487s
  <details><summary>stdout（207 字符）</summary>

```
initialize 1.44s {"name": "mdcg-mcp", "version": "0.8.1"}
ingest#1 0.00s isError=False {"new_events": 0, "written": 0, "denied": 0, "sensitivity": "private", "last_error": null, "hint": null, "error": null}
```
</details>
- **[00:20] #66** `step` {"name": "S13d 对 S10b 的库用 private 令牌重试", "doc": ""}
- **[00:20] #67** `cmd_start` step=S13d 对 S10b 的库用 private 令牌重试 ：`python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py ingest --base /tmp/pes-dshm --clone /tmp/pes-dshm/work/dsh-memory --root /tmp/pes-dshm/probe_root_e --token /tmp/pes-dshm/secrets/designer_private.token --jsonl /tmp/pes-dshm/probe_session.jsonl`
- **[00:21] #68** `cmd_end` step=S13d 对 S10b 的库用 private 令牌重试 rc=0 用时 1.505s
  <details><summary>stdout（207 字符）</summary>

```
initialize 1.44s {"name": "mdcg-mcp", "version": "0.8.1"}
ingest#1 0.00s isError=False {"new_events": 0, "written": 0, "denied": 0, "sensitivity": "private", "last_error": null, "hint": null, "error": null}
```
</details>
- **[00:21] #69** `step` {"name": "S14 DSH 运行时自动记忆缺省通道 mdcg_remember(gated) 逐条写 25 条用户消息：闸门四态+时延", "doc": ""}
- **[00:21] #70** `cmd_start` step=S14 DSH 运行时自动记忆缺省通道 mdcg_remember(gated) 逐条写 25 条用户消息：闸门四态+时延 ：`python3 /workspace/work/pes/plugins/dsh-memory/probe_cli.py remember --base /tmp/pes-dshm --clone /tmp/pes-dshm/work/dsh-memory --root /tmp/pes-dshm/probe_root_d --token /tmp/pes-dshm/secrets/designer.token --jsonl /tmp/pes-dshm/probe_session.jsonl --n 25`
- **[00:23] #71** `cmd_end` step=S14 DSH 运行时自动记忆缺省通道 mdcg_remember(gated) 逐条写 25 条用户消息：闸门四态+时延 rc=0 用时 1.573s
  <details><summary>stdout（143 字符）</summary>

```
initialize 1.46s {"name": "mdcg-mcp", "version": "0.8.1"}
remember n=25 verdicts={'ACCEPT': 8, 'DEFER': 17}  mean=0.002s p50=0.000s p95=0.005s
```
</details>
- **[00:23] #72** `snapshot` {"which": "after_install"}
- **[00:23] #73** `step` {"name": "U1 卸载（README 无卸载说明；删 clone 与 venv）", "doc": ""}
- **[00:23] #74** `cmd_start` step=U1 卸载（README 无卸载说明；删 clone 与 venv） ：`rm -rf /tmp/pes-dshm/work/dsh-memory /tmp/pes-dshm/venv; echo done`
- **[00:23] #75** `cmd_end` step=U1 卸载（README 无卸载说明；删 clone 与 venv） rc=0 用时 0.045s
  <details><summary>stdout（5 字符）</summary>

```
done
```
</details>
- **[00:23] #76** `step` {"name": "U2 残留检查：HOME / MDCG_ROOT / 临时目录", "doc": ""}
- **[00:23] #77** `cmd_start` step=U2 残留检查：HOME / MDCG_ROOT / 临时目录 ：`cd /tmp/pes-dshm/home && find . -type f | sort | head -80; echo '--- /tmp/md_cg_servers ---'; ls -la /tmp/md_cg_servers 2>&1 | head -20; echo '--- MDCG_ROOT ---'; find /tmp/pes-dshm/root -type f | head`
- **[00:23] #78** `cmd_end` step=U2 残留检查：HOME / MDCG_ROOT / 临时目录 rc=0 用时 0.019s
  <details><summary>stdout（9163 字符）</summary>

```
8457f879db267dcad46306b20a64b06dc43c05ac3e93b20c68da0db025c9a96ae553d8e39ca2bf21d86
./.npm/_cacache/content-v2/sha512/bc/6a/4ba3d9bde6b6dd7d1d649defa039f90676f23de3292b847e7a52afbd3b372fd464d8d93fdce36cf2aca4f7371876d319f614003d4a7c3733c5408f6228fe
./.npm/_cacache/content-v2/sha512/d8/73/e9d86deb5f8060761464a1e207f780fafe7861b0d9fad230f53b80955b15e4439e0fcff33bfe5f883ba6b3db18a89707d4d93af8ecc69d75f9519e646c4e
./.npm/_cacache/content-v2/sha512/e0/e3/da2d885425e53a6eef9c0bca9fcaa735360c6cf2e31e7247bec9d4088876cd08b4d9d812c03e116273fe8153864ef36ab57fa5032e8014b828eba322a9d6
./.npm/_cacache/content-v2/sha512/ea/6c/838c7f314360a8efe2b55fefe81b3f896b7c880a8384a572c4b779e4b201bdd81ade5f9ef5d060bf0
…（截断，全文见 JSONL）…
ct  9 16:34 1741.json
-rw-r--r-- 1 sandbox sandbox 523 Oct  9 16:34 1745.json
-rw-r--r-- 1 sandbox sandbox 524 Oct  9 16:34 1749.json
-rw-r--r-- 1 sandbox sandbox 524 Oct  9 16:34 1753.json
-rw-r--r-- 1 sandbox sandbox 524 Oct  9 16:34 1761.json
-rw-r--r-- 1 sandbox sandbox 524 Oct  9 16:34 1765.json
-rw-r--r-- 1 sandbox sandbox 524 Oct  9 16:34 1769.json
-rw-r--r-- 1 sandbox sandbox 524 Oct  9 16:35 1895.json
-rw-r--r-- 1 sandbox sandbox 524 Oct  9 16:35 1905.json
-rw-r--r-- 1 sandbox sandbox 523 Oct  9 16:35 1915.json
-rw-r--r-- 1 sandbox sandbox 524 Oct  9 16:35 1919.json
--- MDCG_ROOT ---
/tmp/pes-dshm/root/_heartbeat.jsonl
/tmp/pes-dshm/root/_keys.json
/tmp/pes-dshm/root/_keys.json.lock
```
</details>
- **[00:23] #79** `residue` {"by_top": {"~/.dsh/.dsh-memory": [18, 1995586], "~/.mdcg/_tokens.json": [1, 2201], "~/.mdcg/_tokens.json.lock": [1, 0], "~/.mdcg/master.key": [1, 44], "~/.mdcg/sustain": [1, 0], "~/.mdcg/theory.json": [1, 238], "~/.npm/_cacache": [42, 27186608], "~/.npm/_logs": [1, 9430], "~/.npm/_npx": [1600, 44437809], "~/.npm/_update-notifier-last-checked": [1, 0], "$MDCG_ROOT": [13, 442]}, "n_new": 1680}
- **[00:23] #80** `summary` {"steps": [{"name": "S0 建 venv（隔离用，非 README 步骤）", "cmd": "/usr/local/bin/python3 -m venv /tmp/pes-dshm/venv", "rc": 0, "secs": 1.714}, {"name": "S1 git clone（README 手工步骤①）", "cmd": "git clone https://github.com/FuRongJun-1999/dsh-memory.git && cd dsh-memory && git checkout -q c8c3655234d57214ae990ab2c7590f7ba590d901 && git log -1 --format=%H", "rc": 0, "secs": 2.528}, {"name": "S2 npx init（README「一键配置（推荐）」，非交互，--end generic）", "cmd": "npx @furongjun1999/dsh-memory init -- --end generic --root /tmp/pes-dshm/root --python /tmp/pes-dshm/venv/bin/python", "rc": 0, "secs": 2.394}, {"name": "S2b 本地仓…
- **[00:23] #81** `rec_end`
