# -*- coding: utf-8 -*-
"""插件描述对象（入口点 ``lingshu_ng.plugins: nn = lingshu_ng_nn.plugin:PLUGIN``）。只用标准库，导入不加载第三方库。

本插件提供旧路径 ``lingshu_ng.nn.*``（核心 :mod:`lingshu_ng._alias` 把它别名到 ``lingshu_ng_nn.*``，同一模块对象）。依赖：numpy、Pillow。
"""
from . import __version__


class _Plugin:
    name = "nn"
    distribution = "lingshu-ng-nn"
    version = __version__
    dependencies = ("numpy", "PIL")
    subpackages = {"nn": "lingshu_ng_nn"}
    provides = {"subpackage:nn": "lingshu_ng_nn"}

    def __repr__(self):
        return f"<lingshu-ng plugin {self.distribution} {self.version}>"


PLUGIN = _Plugin()
