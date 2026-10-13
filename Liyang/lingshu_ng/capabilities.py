# -*- coding: utf-8 -*-
"""capabilities · 当前生效档位查询（stab-r1）

ng 的可选依赖全部「缺了逐位退回」。:func:`capabilities` 回答「此刻这台机器上实际跑的是哪一档」：
已发现的插件及其版本（1.24 起，:mod:`lingshu_ng.plugins`）、插件声明的第三方依赖能否导入（含导入失败的异常原文，例如 Windows 上
onnxruntime DLL 加载被拒）、各模型件是否可用及原因、中文长请求语义通路的生效档位，以及本进程迄今已发生的退回（:mod:`lingshu_ng.diag`）。
核心本身不导入任何第三方库：``dependencies`` 只列已发现插件声明的依赖（未装插件时为空字典）。

调用会按需构造模型件单例（与召回时用的是同一个单例，不另起会话）；不改变任何行为。
"""
from __future__ import annotations

import logging
import importlib
from typing import Any, Dict, Optional

from . import diag, plugins, semrank
from .assoc import AssocConfig

_log = logging.getLogger(__name__)

__all__ = ["capabilities", "semantic_tier", "probe_dependency", "compat_methods"]



def probe_dependency(name: str) -> Dict[str, Any]:
    """能否导入 ``name``：{available, version, error}。装了但原生库加载失败也记为不可用（error 带异常原文）。"""
    try:
        mod = importlib.import_module(name)
    except Exception as e:  # 第三方包导入期的失败类型不可枚举（ImportError / OSError / DLL 拒绝等），原文如实上报
        _log.debug("可选依赖探测：导入失败即「不可用」，原因原文已写入返回值", exc_info=True)
        return {"available": False, "version": None, "error": f"{type(e).__name__}: {e}"}
    return {"available": True, "version": getattr(mod, "__version__", None), "error": None}


def semantic_tier(cfg: Optional[AssocConfig] = None, scorer=None, embedder=None, casc=None) -> str:
    """中文长请求语义通路的生效档位（按交付默认配置或给定 ``cfg``）：
    ``v4``（无交叉编码件，sem_v4fb 退回）/ ``v7.1``（交叉编码，无稠密补入）/ ``v11c``（+ 自适应稠密补入）/ ``v13``（+ 复打）；
    配置里语义通路关闭 → ``off``。"""
    cfg = cfg or AssocConfig()
    if cfg.sem_n <= 0:
        return "off"
    if scorer is None:
        return "v4" if cfg.sem_v4fb else "v4-equivalent"
    tier = "v7.1"
    if cfg.sem_dense > 0 and embedder is not None:
        tier = "v11c"
    if cfg.sem_casc > 0 and casc is not None:
        tier = "v13" if tier == "v11c" else tier + "+casc"
    return tier


def capabilities(cfg: Optional[AssocConfig] = None) -> Dict[str, Any]:
    """当前生效档位快照（纯数据，可 JSON 序列化）。"""
    sc = semrank.get_scorer()
    em = semrank.get_embedder()
    cs = semrank.get_casc_scorer() if (cfg or AssocConfig()).sem_casc > 0 else None
    models = {
        "cross_scorer": {"available": sc is not None, "reason": None if sc is not None else semrank.unavailable_reason("scorer")},
        "dense_embedder": {"available": em is not None, "reason": None if em is not None else semrank.unavailable_reason("dense")},
        "casc_scorer": {"available": cs is not None,
                        "reason": None if cs is not None else (semrank.unavailable_reason("casc") or "交付默认未启用（sem_casc 0）")},
    }
    found = plugins.installed()
    deps = list(dict.fromkeys(d for p in found.values() for d in p["dependencies"]))   # 插件名序、声明序、去重
    return {
        "plugins": found,
        "dependencies": {n: probe_dependency(n) for n in deps},
        "models": models,
        "semantic_tier": semantic_tier(cfg, sc, em, cs),
        "fallbacks": diag.fallbacks(),
    }


def compat_methods() -> Dict[str, Dict[str, Any]]:
    """兼容门面 ``SpacetimeMemoryEngine`` 每个公开方法的支持状态（不构造引擎）：
    ``{"status": "supported"}``，或 ``{"status": "unsupported", "on_call", "organ", "upstream_default", "reason"}``。
    ``on_call`` 为 ``upstream_default``（返回上游缺省值）或 ``raise NotSupportedError``（``LINGSHU_NG_STRICT_UNSUPPORTED=1``）。
    与 ``SpacetimeMemoryEngine(...).capabilities()["compat_methods"]`` 相同。"""
    from .compat_engine import SpacetimeMemoryEngine
    from .compat_stubs import support_table
    return support_table(SpacetimeMemoryEngine)
