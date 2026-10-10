# [Docs] README「写入凭据」的令牌签发命令只有 Windows cmd 写法，Linux/macOS 原样照抄直接失败（rc=127）

> 状态：**草稿，未提交**。被测 sha `c8c3655`。
> **是否已有人报**：查 <https://github.com/FuRongJun-1999/dsh-memory/issues?q=is%3Aissue>（2026-10-10，共 81 条，4 页逐条看标题）未见同题。相近但不同：#19（Linux 解释器默认值写死 `python`）、#39/#57（Windows 特有问题）。

## 环境
见 `_公共环境.md`。

## 复现步骤
在 bash 中原样粘贴 README「写入凭据」节的代码块：
```
python -m md_cg.tokens issue --role designer --actor dsh-memory --clearance internal ^
  --ops-allow info,route,read,write,recent,goal,identity,whitebox,verify ^
  --layers-allow knowledge,contextual,structural,self,goals,unresolved,rejected
```

## 期望
README 给出 POSIX shell 可用的写法（或同时给出 cmd 与 bash 两种），照抄即可签发令牌；另外 Linux 上通常只有 `python3`。

## 实际
```
python -m md_cg.tokens: error: unrecognized arguments: ^
/bin/sh: 2: --ops-allow: not found
/bin/sh: 3: --layers-allow: not found
```
rc=127 ⟦录像:dsh_install@00:06#21⟧。改成单行 `python3 …` 后成功 ⟦录像:dsh_install@00:07#24⟧。
README 正文没有 bash 写法；只有 `init` 的输出里有一句"bash 把行尾 ^ 换成 \"⟦录像:dsh_install@00:07#38⟧——而 `init` 在 Linux 上本身静默空转（见 #97 / 草稿 01），用户看不到这句提示。另 README 中持久化环境变量用 `setx`（同为 Windows 专有）。

## 影响
Linux/macOS 用户在"写入凭据"这一步卡住；且第一行就把 `^` 当参数报错，容易误判为工具 bug。

## 建议
- README 代码块改为 bash 续行 `\` 与 `python3`，并并列给出 Windows cmd / PowerShell 写法；`setx` 旁给出 `export`／写入 shell 配置的等价写法。
- 文档 CI 可加一条：在 Linux 上抽取 README 代码块执行 `--help` 级冒烟。
