# -*- coding: utf-8 -*-
"""插件描述对象（入口点 ``lingshu_ng.plugins: world = lingshu_ng_world.plugin:PLUGIN``）。只用标准库，导入不加载第三方库。

本插件提供旧路径 ``lingshu_ng.world.*``（核心 :mod:`lingshu_ng._alias` 把它别名到 ``lingshu_ng_world.*``，同一模块对象）。依赖：numpy、Pillow。
"""
from . import __version__


class _Plugin:
    name = "world"
    distribution = "lingshu-ng-world"
    version = __version__
    dependencies = ("numpy", "PIL")
    subpackages = {"world": "lingshu_ng_world"}
    provides = {"subpackage:world": "lingshu_ng_world"}

    def __repr__(self):
        return f"<lingshu-ng plugin {self.distribution} {self.version}>"


PLUGIN = _Plugin()
