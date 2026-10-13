# -*- coding: utf-8 -*-
"""旧子包路径的兼容入口（split-r1，rel-v1.24 拆包）。

``lingshu_ng.world`` / ``lingshu_ng.nn`` / ``lingshu_ng.gen`` 依赖 numpy / Pillow，自 1.24 起拆成独立插件包
（``lingshu-ng-world`` / ``lingshu-ng-nn`` / ``lingshu-ng-gen``，顶层包名 ``lingshu_ng_world`` 等）。核心不再携带它们的源码；
本模块在 ``sys.meta_path`` 首位挂一个只认这三个前缀的查找器：

- 插件已安装（或源码树 ``plugins/lingshu-ng-*/src`` 可见，见 :func:`source_plugin_paths`）：把插件的包目录以旧名
  ``lingshu_ng.world`` 载入，子模块经包 ``__path__`` 照常找到——模块名、类的 ``__module__``、pickle 路径都与 1.22 相同；
  旧名是规范导入路径（插件内部的相对导入也都解析到旧名下）；``lingshu_ng_world`` 顶层名只是发行包的存放位置（入口点
  ``lingshu_ng_world.plugin`` 只载入描述对象）；
- 未安装：抛 :class:`ModuleNotFoundError`（:class:`ImportError` 子类），信息写明需要安装哪个插件。

只用标准库；``import lingshu_ng`` 时只做一次 ``sys.meta_path.insert``，不探测文件系统。
"""
import os
import sys

#: 旧子包短名 → (插件顶层包名, 发行包名)
SUBPACKAGES = {
    "world": ("lingshu_ng_world", "lingshu-ng-world"),
    "nn": ("lingshu_ng_nn", "lingshu-ng-nn"),
    "gen": ("lingshu_ng_gen", "lingshu-ng-gen"),
}

_PKG = __name__.rsplit(".", 1)[0]          # "lingshu_ng"
_SRC_DONE = []


def source_plugin_paths():
    """源码树布局（仓库 / 发布目录 ``Liyang/``）下的插件源码目录：``<lingshu_ng 的上级>/plugins/lingshu-ng-*/src``，
    且其中有 ``lingshu_ng_*/__init__.py``。``LINGSHU_NG_SOURCE_PLUGINS=0`` 关闭。只在首次调用时扫描并把目录追加到
    ``sys.path`` 末尾（已安装的同名插件在前，优先）。返回追加的目录列表。"""
    if _SRC_DONE:
        return _SRC_DONE[0]
    found = []
    _SRC_DONE.append(found)
    if os.environ.get("LINGSHU_NG_SOURCE_PLUGINS", "1").strip() == "0":
        return found
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins")
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return found
    for d in names:
        src = os.path.join(root, d, "src")
        if not d.startswith("lingshu-ng-") or not os.path.isfile(os.path.join(root, d, "pyproject.toml")):
            continue
        top = d.replace("-", "_")
        if os.path.isfile(os.path.join(src, top, "__init__.py")):
            if src not in sys.path:
                sys.path.append(src)
            found.append(src)
    return found


class _AliasFinder:
    """``lingshu_ng.{world,nn,gen}`` → 插件目录的查找器：把插件包目录当作旧名包载入（``__name__`` / 类的 ``__module__``
    仍是 ``lingshu_ng.world.*`` 等，与 1.22 相同；子模块经包 ``__path__`` 照常查找）。"""

    @staticmethod
    def find_spec(fullname, path=None, target=None):
        """只认 ``lingshu_ng.world`` / ``nn`` / ``gen`` 三个名字；其余返回 None 交给后续查找器。"""
        if not fullname.startswith(_PKG + "."):
            return None
        ent = SUBPACKAGES.get(fullname[len(_PKG) + 1:])
        if ent is None:
            return None
        top, dist = ent
        import importlib.util
        spec = _top_spec(top)
        if spec is None and source_plugin_paths():
            importlib.invalidate_caches()
            spec = _top_spec(top)
        if spec is None or not spec.origin or not spec.submodule_search_locations:
            raise ModuleNotFoundError(
                f"{fullname} 自 lingshu-ng 1.24 起拆为独立插件包 {dist}（依赖 numpy / Pillow），当前环境未安装："
                f"pip install {dist}", name=fullname)
        return importlib.util.spec_from_file_location(fullname, spec.origin,
                                                      submodule_search_locations=list(spec.submodule_search_locations))


def _top_spec(top):
    import importlib.util
    try:
        return importlib.util.find_spec(top)      # 顶层名：只查找，不导入
    except (ImportError, ValueError):
        return None


def install():
    """在 ``sys.meta_path`` 首位挂上别名查找器（幂等）。"""
    if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder())
