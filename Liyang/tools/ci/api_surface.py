# -*- coding: utf-8 -*-
"""公开 API 签名面（stab-r6 #4）：从代码里读出 lingshu_ng 承诺稳定的公开名字与签名，供
``tests_ng/test_api_snapshot.py``（与 ``tests_ng/api_snapshot.json`` 比对）和 ``tools/ci/gen_api_appendix.py``
（写 docs/STABILITY_ng.md 附录）共用。

签名只记参数名、参数种类与缺省值 repr，**不记类型注解**（注解的字符串形式随 Python 小版本变化，
会让 3.11 / 3.12 / 3.13 的快照不同）。只依赖标准库与 lingshu_ng 核心（最小 venv 可跑）。
"""
import enum
import dataclasses
import importlib
import inspect

#: 公开面：(模块, 名字)。改这个清单本身也算公开 API 变化（快照会变）。
PUBLIC = [
    ("lingshu_ng", ["__version__"]),
    ("lingshu_ng.engine", ["MemoryEngine"]),
    ("lingshu_ng.compat", ["SpacetimeMemoryEngine"]),
    ("lingshu_ng.types", ["Node", "Edge", "WriteResult", "MemoryLayer", "EdgeType", "Role", "ConditionSpace"]),
    ("lingshu_ng.capabilities", ["capabilities", "compat_methods", "probe_dependency"]),
    ("lingshu_ng.diag", ["fallbacks", "reset"]),
    ("lingshu_ng.plugins", ["GROUP", "Plugin", "CrossScorerBackend", "DenseEmbedderProtocol", "EmbeddingProvider", "CrossEncoder",
                            "PluginMissingError", "register", "unregister", "installed", "provider", "require", "hint", "refresh"]),
    ("lingshu_ng.layers", ["LayerViolation"]),
    ("lingshu_ng.governance", ["DesignerRequired"]),
    ("lingshu_ng.compat_engine", ["PromotionRejected"]),
    ("lingshu_ng.compat_stubs", ["NotSupportedError"]),
    ("lingshu_ng.store.schema", ["SchemaTooNewError", "SCHEMA_VERSION"]),
    ("lingshu_ng.store.db", ["DatabaseOpenError", "DatabaseLockedError", "EngineClosedError"]),
    ("lingshu_ng.inputs", ["MAX_QUERY_CHARS", "MAX_LIMIT"]),
    ("lingshu_ng.integrations.service", ["Service", "BadRequest"]),
    ("lingshu_ng.integrations.http", ["make_server", "serve", "Server", "MAX_BODY"]),
    ("lingshu_ng.integrations.mcp", ["McpServer", "run_stdio", "PROTOCOL_VERSIONS"]),
    ("lingshu_ng.integrations.cli", ["main"]),
]
#: 不是 API、只是「随版本变的值」：只记类型，不记取值
VALUE_EXEMPT = {"lingshu_ng.__version__"}


def sig(obj) -> str:
    """参数名 + 种类 + 缺省值 repr（不含注解）。"""
    try:
        s = inspect.signature(obj)
    except (TypeError, ValueError):
        return "<no signature>"
    out, star = [], False
    for p in s.parameters.values():
        if p.kind is p.VAR_POSITIONAL:
            out.append("*" + p.name); star = True
            continue
        if p.kind is p.VAR_KEYWORD:
            out.append("**" + p.name)
            continue
        if p.kind is p.KEYWORD_ONLY and not star:
            out.append("*"); star = True
        out.append(p.name + ("" if p.default is p.empty else "=" + _dr(p.default)) + ("/" if p.kind is p.POSITIONAL_ONLY else ""))
    return "(" + ", ".join(out) + ")"


def _dr(v) -> str:
    if isinstance(v, enum.Enum):
        return f"{type(v).__name__}.{v.name}"
    if callable(v):
        return f"<callable {getattr(v, '__name__', type(v).__name__)}>"
    return repr(v)


def _class(qual: str, cls, out: dict) -> None:
    out[qual] = "class(" + ", ".join(b.__name__ for b in cls.__bases__) + ")"
    if issubclass(cls, enum.Enum):
        out[qual + ".members"] = ", ".join(f"{m.name}={m.value!r}" for m in cls)
        return
    if dataclasses.is_dataclass(cls):
        out[qual + ".fields"] = ", ".join(f.name for f in dataclasses.fields(cls))
    if issubclass(cls, BaseException):
        return
    for name, member in sorted(vars(cls).items()):
        if name.startswith("_") and name != "__init__":
            continue
        if isinstance(member, (staticmethod, classmethod)):
            out[f"{qual}.{name}"] = type(member).__name__ + sig(member.__func__)
        elif isinstance(member, property):
            out[f"{qual}.{name}"] = "property"
        elif inspect.isfunction(member):
            out[f"{qual}.{name}"] = sig(member)
        elif not callable(member) and isinstance(member, (int, float, str, tuple, frozenset)):
            out[f"{qual}.{name}"] = "attr " + type(member).__name__
    # 兼容门面的方法有一部分来自 mixin / 运行期挂载：按 dir() 补齐公开可调用成员
    for name in sorted(dir(cls)):
        if name.startswith("_") or f"{qual}.{name}" in out:
            continue
        member = inspect.getattr_static(cls, name)
        if isinstance(member, property):
            out[f"{qual}.{name}"] = "property"
        elif callable(getattr(cls, name, None)):
            out[f"{qual}.{name}"] = sig(getattr(cls, name))


def surface() -> dict:
    """{限定名: 签名描述}，键已排序。"""
    out = {}
    for mod, names in PUBLIC:
        m = importlib.import_module(mod)
        for n in names:
            obj, qual = getattr(m, n), f"{mod}.{n}"
            if inspect.isclass(obj):
                _class(qual, obj, out)
            elif callable(obj):
                out[qual] = sig(obj)
            elif qual in VALUE_EXEMPT:
                out[qual] = "value " + type(obj).__name__
            else:
                out[qual] = f"const {type(obj).__name__} = {obj!r}"
    # 兼容门面不支持的方法由实例 __getattr__ 提供（类上查不到）：按 compat_methods() 补齐，并记每个方法的支持状态
    from lingshu_ng.capabilities import compat_methods
    base = "lingshu_ng.compat.SpacetimeMemoryEngine."
    for n, v in compat_methods().items():
        out.setdefault(base + n, "stub via __getattr__")
        out[f"compat_status.{n}"] = v["status"]
    return dict(sorted(out.items()))


def diff(old: dict, new: dict) -> dict:
    """{"removed": [...], "added": [...], "changed": [...]}（名字列表）。"""
    return {"removed": sorted(set(old) - set(new)), "added": sorted(set(new) - set(old)),
            "changed": sorted(k for k in set(old) & set(new) if old[k] != new[k])}
