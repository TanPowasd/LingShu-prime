# -*- coding: utf-8 -*-
"""plugins · 插件发现、显式注册与协议接口（split-r1，rel-v1.24 起；纯标准库）

核心 ``lingshu-ng`` 零外部依赖；凡需要第三方库的部分都在独立插件包里：

| 插件（发行包） | 顶层包 | 提供 | 依赖 |
|---|---|---|---|
| ``lingshu-ng-embed`` | ``lingshu_ng_embed`` | 交叉编码打分后端 / 稠密向量件 / 判别头（:mod:`lingshu_ng.semrank`）、``OnnxEmbedder`` / ``OnnxCrossEncoder``（:mod:`lingshu_ng.embed`） | numpy、onnxruntime、tokenizers |
| ``lingshu-ng-world`` | ``lingshu_ng_world`` | 旧路径 ``lingshu_ng.world.*`` | numpy、Pillow |
| ``lingshu-ng-nn`` | ``lingshu_ng_nn`` | 旧路径 ``lingshu_ng.nn.*`` | numpy、Pillow |
| ``lingshu-ng-gen`` | ``lingshu_ng_gen`` | 旧路径 ``lingshu_ng.gen.*`` | numpy、Pillow、lingshu-ng-nn |

发现顺序（同名插件先到先得）：

1. **显式注册**：:func:`register`（宿主 / 测试注入自己的打分件等）；
2. **入口点**：``importlib.metadata.entry_points(group="lingshu_ng.plugins")``，每个入口点指向插件对象（或返回插件对象的无参可调用）；
3. **源码树**：从仓库 / 发布目录直接运行（未 pip 安装）时，``<lingshu_ng 的上级>/plugins/lingshu-ng-*/src``
   下的 ``lingshu_ng_*/plugin.py`` 的 ``PLUGIN``（``LINGSHU_NG_SOURCE_PLUGINS=0`` 关闭）。

插件对象的约定（鸭子类型，见 :class:`Plugin`）：``name``、``distribution``、``version``、``provides``（能力名 → 工厂可调用或
``"模块:属性"`` 字符串）、``dependencies``（第三方模块名，供 :func:`lingshu_ng.capabilities.capabilities` 探测）、
可选 ``subpackages``（旧子包短名 → 顶层包名）。

缺插件时：需要模型的通路逐位退回无模型档（与缺依赖 / 缺模型时相同），进程内打一次 WARNING（登记 ``diag.fallbacks()``
``plugin_missing:<插件名>``），信息写明 ``pip install <发行包>``。
"""
from __future__ import annotations

import importlib
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from . import _alias, diag

_log = logging.getLogger(__name__)

__all__ = ["GROUP", "KNOWN", "Plugin", "CrossScorerBackend", "DenseEmbedderProtocol", "EmbeddingProvider", "CrossEncoder",
           "PluginMissingError", "register", "unregister", "installed", "provider", "require", "hint", "refresh"]

#: 入口点组名
GROUP = "lingshu_ng.plugins"

#: 已知插件：插件名 → (发行包名, 能力 / 旧子包说明)。只用于给出「该装哪个插件」的提示。
KNOWN: Dict[str, Tuple[str, str]] = {
    "embed": ("lingshu-ng-embed", "交叉编码重排 / 稠密向量 / 判别头 / OnnxEmbedder / OnnxCrossEncoder"),
    "world": ("lingshu-ng-world", "lingshu_ng.world"),
    "nn": ("lingshu-ng-nn", "lingshu_ng.nn"),
    "gen": ("lingshu-ng-gen", "lingshu_ng.gen"),
}

#: 能力名 → 提供它的已知插件名（提示用）
CAPABILITY_PLUGIN: Dict[str, str] = {
    "cross_backend": "embed", "dense_embedder": "embed", "disc_head": "embed",
    "onnx_embedder": "embed", "onnx_cross_encoder": "embed", "embed_internals": "embed",
}


# --------------------------------------------------------------------------- 协议接口
@runtime_checkable
class Plugin(Protocol):
    """插件对象（入口点 / :func:`register` 的参数）。"""
    name: str
    distribution: str
    version: str
    provides: Dict[str, Any]
    dependencies: Tuple[str, ...]


@runtime_checkable
class CrossScorerBackend(Protocol):
    """``cross_backend`` 工厂 ``(model_dir, onnx_name, model) -> 后端`` 的返回值：交叉编码器推理后端。
    缓存、分批次序、取整由核心 :class:`lingshu_ng.semrank.CrossScorer` 负责；后端只做推理。"""
    tag: str

    def encode_pairs(self, q: str, ps: Sequence[str]) -> Any:
        """(问句, 段落) 对分词（超长问句截断规则见插件实现）。"""

    def logits(self, q: str, ps: Sequence[str]) -> List[float]:
        """一批 (问句, 段落) 的相关度 logit（未取整，与 ps 同序）。"""


@runtime_checkable
class DenseEmbedderProtocol(Protocol):
    """``dense_embedder`` 工厂 ``(model_dir, onnx_name, cache_dir, model) -> 件`` 的返回值：稠密向量件。
    ``encode(texts)`` 返回 (n, d) 数组对象，须支持 ``M @ v``、``[i]``、``.mean()`` / ``.std()``（插件为 numpy float32）；
    核心只对它做这些运算，自身不导入数组库。"""

    def encode(self, texts: Sequence[str]) -> Any:
        """(n, d) 句向量数组（L2 归一）。"""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """语义检索提供者（:meth:`lingshu_ng.engine.MemoryEngine.set_embedding_provider`，自带索引形态）。"""

    def add(self, ids: Sequence[str], texts: Sequence[str]) -> None:
        """编码并加入索引（已有 id 覆盖）。"""

    def search(self, query: str, limit: int) -> Any:
        """前 limit 名：[(id, 分数)] 或 [id]。"""


@runtime_checkable
class CrossEncoder(Protocol):
    """交叉编码提供者（:meth:`lingshu_ng.engine.MemoryEngine.set_reranker`）。"""

    def score(self, query: str, texts: Sequence[str]) -> List[float]:
        """[(query, texts_i) 的相关分]，与 texts 同序。"""


class PluginMissingError(ImportError):
    """需要的插件未安装（:class:`ImportError` 子类：旧代码 ``except ImportError`` 照常捕获）。"""

    def __init__(self, capability: str, plugin: Optional[str] = None, what: str = "") -> None:
        plugin = plugin or CAPABILITY_PLUGIN.get(capability, capability)
        dist = KNOWN.get(plugin, (f"lingshu-ng-{plugin}", ""))[0]
        self.capability, self.plugin, self.distribution = capability, plugin, dist
        super().__init__(f"{what or capability} 需要插件 {dist}（自 lingshu-ng 1.24 起依赖第三方库的部分拆为独立插件包）："
                         f"pip install {dist}", name=dist)


# --------------------------------------------------------------------------- 注册表
_LOCK = threading.RLock()
_EXPLICIT: Dict[str, Any] = {}
_FOUND: Optional[Dict[str, Dict[str, Any]]] = None


def _attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _info(obj, source: str, error: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
    return {"name": name or _attr(obj, "name"), "distribution": _attr(obj, "distribution"),
            "version": _attr(obj, "version"), "source": source, "obj": obj, "error": error,
            "provides": sorted(dict(_attr(obj, "provides", {}) or {})),
            "dependencies": tuple(_attr(obj, "dependencies", ()) or ()),
            "subpackages": dict(_attr(obj, "subpackages", {}) or {})}


def _load_entry(obj):
    if not hasattr(obj, "provides") and not isinstance(obj, dict) and callable(obj):
        obj = obj()
    return obj


def _discover() -> Dict[str, Dict[str, Any]]:
    found: Dict[str, Dict[str, Any]] = {}
    for name, obj in _EXPLICIT.items():
        found[name] = _info(obj, "register")
    for name, info in _discover_external().items():
        found.setdefault(name, info)
    return found


def _discover_external() -> Dict[str, Dict[str, Any]]:
    """入口点 + 源码树（显式注册之外的来源）。"""
    found: Dict[str, Dict[str, Any]] = {}
    try:
        from importlib.metadata import entry_points
        eps = list(entry_points(group=GROUP))
    except Exception:  # 元数据损坏的环境：入口点不可读 ⇒ 只用显式注册与源码树，原因记日志
        _log.warning("读取入口点组 %s 失败 → 跳过入口点发现", GROUP, exc_info=True)
        eps = []
    for ep in sorted(eps, key=lambda e: e.name):
        if ep.name in found:
            continue
        try:
            obj = _load_entry(ep.load())
            found[_attr(obj, "name") or ep.name] = _info(obj, "entry_point")
        except Exception as e:  # 第三方插件导入期失败类型不可枚举：记为该插件不可用，原文进 capabilities()["plugins"]
            _log.warning("插件入口点 %s 加载失败 → 视为未安装", ep.value, exc_info=True)
            found[ep.name] = _info({}, "entry_point", f"{type(e).__name__}: {e}", name=ep.name)
    for src in _alias.source_plugin_paths():
        import os
        for top in sorted(os.listdir(src)):
            if not top.startswith("lingshu_ng_") or not os.path.isfile(os.path.join(src, top, "plugin.py")):
                continue
            short = top[len("lingshu_ng_"):]
            if short in found:
                continue
            try:
                obj = importlib.import_module(f"{top}.plugin").PLUGIN
                found[_attr(obj, "name") or short] = _info(obj, "source_tree")
            except Exception as e:  # 同上：源码树插件导入失败 ⇒ 视为未安装并上报原因
                _log.warning("源码树插件 %s 加载失败 → 视为未安装", top, exc_info=True)
                found[short] = _info({}, "source_tree", f"{type(e).__name__}: {e}", name=short)
    return found


def _registry() -> Dict[str, Dict[str, Any]]:
    global _FOUND
    with _LOCK:
        if _FOUND is None:
            _FOUND = _discover()
        return _FOUND


def refresh() -> None:
    """丢弃发现结果（下次查询重新发现）。安装 / 卸载插件或改环境变量后调用。"""
    global _FOUND
    with _LOCK:
        _FOUND = None


def register(plugin: Any, replace: bool = True) -> None:
    """显式注册插件对象（优先于入口点与源码树）。``plugin`` 需有 ``name`` 与 ``provides``。"""
    name = _attr(plugin, "name")
    if not name:
        raise ValueError("插件对象缺少 name")
    with _LOCK:
        if name in _EXPLICIT and not replace:
            raise ValueError(f"插件 {name!r} 已注册")
        _EXPLICIT[name] = plugin
        refresh()


def unregister(name: str) -> bool:
    """撤除显式注册；返回是否撤除了。"""
    with _LOCK:
        hit = _EXPLICIT.pop(name, None) is not None
        refresh()
        return hit


def installed() -> Dict[str, Dict[str, Any]]:
    """已发现的插件：{名: {distribution, version, source, provides, dependencies, error}}（可 JSON 序列化）。"""
    return {n: {k: v for k, v in i.items() if k not in ("obj", "subpackages")} for n, i in sorted(_registry().items())}


def provider(capability: str) -> Optional[Callable]:
    """提供 ``capability`` 的工厂 / 对象；没有已加载的插件提供它 → None。"""
    for name, info in _registry().items():
        if info["error"] is not None:
            continue
        prov = dict(_attr(info["obj"], "provides", {}) or {})
        if capability in prov:
            p = prov[capability]
            if isinstance(p, str):
                mod, _, attr = p.partition(":")
                obj = importlib.import_module(mod)
                p = getattr(obj, attr) if attr else obj
            return p
    return None


def hint(capability: str) -> str:
    """缺 ``capability`` 时的安装提示。"""
    plugin = CAPABILITY_PLUGIN.get(capability, capability)
    dist = KNOWN.get(plugin, (f"lingshu-ng-{plugin}", ""))[0]
    return f"未安装插件 {dist}（pip install {dist}）"


def require(capability: str, what: str = "") -> Callable:
    """同 :func:`provider`，没有则抛 :class:`PluginMissingError`（信息写明该装哪个插件）。"""
    p = provider(capability)
    if p is None:
        raise PluginMissingError(capability, what=what)
    return p


def warn_missing(capability: str, detail: str = "") -> None:
    """缺插件 ⇒ 进程内只打一次 WARNING（diag ``plugin_missing:<插件名>``）。"""
    plugin = CAPABILITY_PLUGIN.get(capability, capability)
    diag.warn_once(f"plugin_missing:{plugin}",
                   f"{hint(capability)} → {detail or '依赖该插件的通路'}逐位退回无模型档")
