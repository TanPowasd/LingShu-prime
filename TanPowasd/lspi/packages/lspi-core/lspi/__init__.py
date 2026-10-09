"""枢接口（LSPI）· 灵枢插件框架原型。

纯标准库。同一协议挂两种宿主：身体库引擎（BodyHost，内置）与大脑库认知图（BrainHost，见 lspi-brain-host）。本包**不 import 任何插件，也不 import lingshu.world / nn / gen**
（verify/lint_imports.py 是门禁）。对灵枢引擎只做鸭子类型访问。
"""
from .manifest import PluginManifest, LSPI_VERSION, ManifestError
from .gate import WriteGate, GateRejected, WriteRecord, check_write, COND_FIELDS
from .hosts import BodyHost, as_host
from .envelope import call, from_request
from .context import CognitionContext
from .registry import Registry, ENTRY_POINT_GROUP
from .host import attach, install_shims

__all__ = [
    "PluginManifest", "LSPI_VERSION", "ManifestError",
    "WriteGate", "GateRejected", "WriteRecord",
    "CognitionContext", "Registry", "ENTRY_POINT_GROUP",
    "attach", "install_shims",
    "check_write", "COND_FIELDS", "BodyHost", "as_host", "call", "from_request",
]
