"""枢接口（LSPI）· 灵枢插件框架原型。

纯标准库。本包**不 import 任何插件，也不 import lingshu.world / nn / gen**
（verify/lint_imports.py 是门禁）。对灵枢引擎只做鸭子类型访问。
"""
from .manifest import PluginManifest, LSPI_VERSION, ManifestError
from .gate import WriteGate, GateRejected, WriteRecord
from .context import CognitionContext
from .registry import Registry, ENTRY_POINT_GROUP
from .host import attach, install_shims

__all__ = [
    "PluginManifest", "LSPI_VERSION", "ManifestError",
    "WriteGate", "GateRejected", "WriteRecord",
    "CognitionContext", "Registry", "ENTRY_POINT_GROUP",
    "attach", "install_shims",
]
