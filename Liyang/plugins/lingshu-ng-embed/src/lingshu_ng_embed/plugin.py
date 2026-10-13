# -*- coding: utf-8 -*-
"""插件描述对象（入口点 ``lingshu_ng.plugins: embed = lingshu_ng_embed.plugin:PLUGIN``）。只用标准库，导入不加载第三方库。"""
from . import __version__


class _EmbedPlugin:
    name = "embed"
    distribution = "lingshu-ng-embed"
    version = __version__
    dependencies = ("numpy", "onnxruntime", "tokenizers")
    provides = {
        "cross_backend": "lingshu_ng_embed.semrank_backend:CrossBackend",
        "dense_embedder": "lingshu_ng_embed.semrank_backend:DenseEmbedder",
        "disc_head": "lingshu_ng_embed.semrank_backend:DiscHead",
        "onnx_embedder": "lingshu_ng_embed.onnx_embed",
        "onnx_cross_encoder": "lingshu_ng_embed.cross",
    }

    def __repr__(self):
        return f"<lingshu-ng plugin {self.distribution} {self.version}>"


PLUGIN = _EmbedPlugin()
