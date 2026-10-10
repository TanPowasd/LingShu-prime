# 原始实验记录（2026-10-10）

本目录按字节保留发布前已完成实验的读数、参数、示例和验证，不把仓库迁移后的核对冒充一次新评测。

- `readings.json`：150 个随机 schema 预算任务、800 次时间 oracle 与 Hive 原文接口检查的完整读数。
- `summary.json`：实验汇总。
- `verification.json` / `test_output.txt`：原工作区 177 项测试的历史验证，包含此前算法套件；那些套件没有全部复制到本目录。
- `parameters.json`：原实验固定参数。
- `demo.json`：原运行示例输出。
- `frozen_sources/`：`readings.json` 中四个冻结输入的原始字节，用于 SHA256 核对；不是发布后的运行入口。

历史 JSON 与冻结脚本保留原工作区绝对路径；这些路径只是来源标识，不需要在读者电脑上存在。
使用上两级目录的脚本运行新代码；验证脚本把历史路径映射到 `frozen_sources/` 文件名。
发布文件与本次验证分别见上两级的 `publication_manifest.json` 和 `publication_verification.json`。
