"""行为探针包：导入即注册全部探针到 probes._base.REG。"""
from . import p_memory, p_layers, p_self, p_graph, p_gate, p_misc  # noqa: F401
from ._base import REG  # noqa: F401
