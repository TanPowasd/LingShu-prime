# -*- coding: utf-8 -*-
"""lingshu_ng_embed · 灵枢 ng 的本地 ONNX 语义件插件（发行包 ``lingshu-ng-embed``）

依赖 numpy、onnxruntime、tokenizers（都在构造 / 调用时才导入）；模型权重不随包发布（bge 系 ONNX 目录自备，见 README）。
核心 ``lingshu-ng`` 通过入口点组 ``lingshu_ng.plugins`` 发现本插件（:mod:`lingshu_ng.plugins`），提供：

- ``cross_backend`` → :class:`lingshu_ng_embed.semrank_backend.CrossBackend`（:class:`lingshu_ng.semrank.CrossScorer` 的推理后端）
- ``dense_embedder`` → :class:`lingshu_ng_embed.semrank_backend.DenseEmbedder`
- ``disc_head`` → :class:`lingshu_ng_embed.semrank_backend.DiscHead`
- ``onnx_embedder`` → :mod:`lingshu_ng_embed.onnx_embed`（旧路径 ``lingshu_ng.embed.OnnxEmbedder``）
- ``onnx_cross_encoder`` → :mod:`lingshu_ng_embed.cross`（旧路径 ``lingshu_ng.embed.cross.OnnxCrossEncoder``）
"""
__version__ = "1.29.0"
