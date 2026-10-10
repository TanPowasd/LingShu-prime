# [Release] npm 上的 0.8.1 仍是 #97 修复前的代码：README 推荐的 `npx … init` 在 Linux 上依旧静默空转、退出码 0

> 状态：**草稿，未提交**。被测 sha `c8c3655`。
> **已有人报**：[#97](https://github.com/FuRongJun-1999/dsh-memory/issues/97)（LarryE135，2026-10-09，已关闭；源码修复 `29e24da9` + `ff000dc2`）。本条不重复报根因，只补"修复未随 npm 发布"这一面。**建议以评论形式追加到 #97，而非新开 issue**（#97 维护者留言"若仍有未覆盖的面，欢迎在关闭后继续评论（我们会重开）"）。同类历史：#48/#49/#100（"出货面缺件"）。

## 环境
见 `_公共环境.md`。

## 复现步骤
```bash
export HOME=$(mktemp -d); cd $(mktemp -d)
npx @furongjun1999/dsh-memory init -- --end generic --root /tmp/m --python python3; echo "exit=$?"
ls lingshu-mcp-snippet.json
grep -n 'import.meta.url === entryUrl' $HOME/.npm/_npx/*/node_modules/@furongjun1999/dsh-memory/lib/cli.js
node $HOME/.npm/_npx/*/node_modules/@furongjun1999/dsh-memory/lib/cli.js init -- --end generic --root /tmp/m --python python3 | head -3
```

## 期望
README「一键配置（推荐）」所述：打印 mcp.json 片段并写出 `lingshu-mcp-snippet.json`；失败时非 0 退出码。

## 实际
- `npx … init`：stdout 0 行，exit 0，不生成 `lingshu-mcp-snippet.json` ⟦录像:dsh_install@00:06#12⟧ ⟦录像:dsh_install@00:07#35⟧。
- npx 缓存里的 `lib/cli.js:52` 仍是 `return import.meta.url === entryUrl`（修复前写法）⟦录像:dsh_install@00:07#35⟧。
- 直接 `node …/lib/cli.js init` 正常输出 37 行配置 ⟦录像:dsh_install@00:07#38⟧。
- npm registry：`dist-tags.latest = 0.8.1`，发布于 2026-10-07 06:05 CST，早于修复提交 `29e24da9`（2026-10-09）；版本号未变。

## 影响
新用户照 README 第一条推荐命令操作，得到"成功但什么都没发生"。源码已修但用户拿不到，#97 的关闭状态会让后来者以为已解决。

## 建议
1. 发布含 `29e24da9` 的新版本（版本号需递增，npm 不允许覆盖 0.8.1）。
2. 发布门禁加"打包 → 安装 → 经 `.bin` 符号链接调用 `init --help` 有输出"的冒烟（#97 原文建议过 CI 冒烟，此处强调要对**发布产物**跑）。
3. 修复 issue 关闭时注明"已在 vX.Y.Z 发布"或"待发布"。
