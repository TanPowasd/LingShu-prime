# TanPowasd · 灵枢（Lingshu）工作目录

本目录由 TanPowasd 维护，存放我们针对上游 [FuRongJun-1999/lingshu](https://github.com/FuRongJun-1999/lingshu) 的自有想法、方案与实现。

约定：
- 每项提交附改动说明与验证方式（复跑命令与实测读数），结论以能被独立复跑为准；
- 与上游 issue/PR 相关的工作先查 `../Liyang/upstream-watch/tracker.json`，避免重复提交；
- 不改动其他贡献者的目录。

## 授权
本目录适用仓库根目录的[全局授权声明](../LICENSE)：**需授权使用**。可在 GitHub 浏览、fork；运行、复制、修改、分发、纳入其他项目、用于模型训练等须事先取得书面授权（在本仓库提 issue 申请）。引用的上游 lingshu 代码仍按其 MIT 协议。

## 记忆算法实验

- [通用判别记忆](discriminative_memory/README.md)：不可变原文、双时间修订、完整证据包与预算覆盖选择。包含代码、48 项离线测试、固定基准和原始读数。
- [实现与结论](discriminative_memory/IMPLEMENTATION_AND_RESULTS.md)：结构化证据选择有初步收益；自然语言抽取与问题绑定尚未实现，不能据此声称通用记忆优于 AGM/BM25/RRF3。
