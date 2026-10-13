# -*- coding: utf-8 -*-
"""插件描述对象（入口点 ``lingshu_ng.plugins: gen = lingshu_ng_gen.plugin:PLUGIN``）。只用标准库，导入不加载第三方库。

本插件提供旧路径 ``lingshu_ng.gen.*``（核心 :mod:`lingshu_ng._alias` 把它别名到 ``lingshu_ng_gen.*``，同一模块对象）。依赖：numpy、Pillow、lingshu-ng-nn。
"""
from . import __version__


class _Plugin:
    name = "gen"
    distribution = "lingshu-ng-gen"
    version = __version__
    dependencies = ("numpy", "PIL")
    subpackages = {"gen": "lingshu_ng_gen"}
    provides = {"subpackage:gen": "lingshu_ng_gen"}

    def __repr__(self):
        return f"<lingshu-ng plugin {self.distribution} {self.version}>"


PLUGIN = _Plugin()
