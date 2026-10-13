# lingshu-ng-embed

灵枢 ng（`lingshu-ng`）的本地 ONNX 语义件插件。核心 `lingshu-ng` 自 1.24 起零外部依赖；需要 numpy / onnxruntime / tokenizers 的部分在本包。

```bash
pip install lingshu-ng            # 核心（零依赖）
pip install lingshu-ng-embed      # 本插件：numpy、onnxruntime、tokenizers
```

## 提供什么

核心通过入口点组 `lingshu_ng.plugins`（`embed = lingshu_ng_embed.plugin:PLUGIN`）发现本插件：

| 能力 | 实现 | 核心里的使用者 / 旧路径 |
|---|---|---|
| `cross_backend` | `lingshu_ng_embed.semrank_backend.CrossBackend` | `lingshu_ng.semrank.CrossScorer`（中文长请求 v7.1 交叉编码重排；缓存 / 分批 / 取整在核心） |
| `dense_embedder` | `lingshu_ng_embed.semrank_backend.DenseEmbedder` | `semrank.get_embedder()`（v11c 稠密补入）；旧名 `lingshu_ng.semrank.DenseEmbedder` |
| `disc_head` | `lingshu_ng_embed.semrank_backend.DiscHead` | `semrank.get_disc()`（v9 判别头，交付默认未启用） |
| `onnx_embedder` | `lingshu_ng_embed.onnx_embed.OnnxEmbedder` | `from lingshu_ng.embed import OnnxEmbedder`（`LINGSHU_NG_EMBED_MODEL`） |
| `onnx_cross_encoder` | `lingshu_ng_embed.cross.OnnxCrossEncoder` | `from lingshu_ng.embed.cross import OnnxCrossEncoder`（`LINGSHU_NG_RERANK_MODEL`） |

代码自 lingshu-ng 1.22 原样迁出，读数逐位不变（核心 + 本插件 与 1.22 带模型读数逐题相同，见 `CHANGELOG_rel-v1.24.md`）。

## 模型

权重不随包发布。中文语义件默认在 `~/.cache/lingshu_ng/models`（或 `$XDG_CACHE_HOME/lingshu_ng/models`、`LINGSHU_NG_SEM=<目录>`）下找
`bge-reranker-base/{tokenizer.json, onnx/model_quantized.onnx}` 与 `bge-small-zh-v1.5/{tokenizer.json, onnx/model.onnx}`；
`LINGSHU_NG_SEM=off` 关闭。详见核心文档 `docs/API_ng.md`「可选依赖」。

## 没装 / 装坏了会怎样

- 没装本插件：核心逐位退回无模型档（中文长请求 = v4 词面档），进程内打一次 WARNING（`diag.fallbacks()["plugin_missing:embed"]`），
  提示 `pip install lingshu-ng-embed`；`from lingshu_ng.embed import OnnxEmbedder` 抛 `PluginMissingError`（`ImportError` 子类）。
- 装了但 onnxruntime 加载失败（如 Windows DLL 被拒）或模型缺失：同 1.22，`capabilities()["models"]` 写明原因，逐位退回。

`lingshu_ng.capabilities.capabilities()["plugins"]` 列出已发现插件、版本与来源。

## 测试

```bash
pip install lingshu-ng lingshu-ng-embed pytest
python -m pytest plugins/lingshu-ng-embed/tests_embed
```
有本地模型时跑带模型用例，否则这些用例 skip。
