# -*- coding: utf-8 -*-
"""_pathguard · 导入期 cwd 解析护栏（上游 #156 v2 / #273 v3 口径的 ng 版）

``import lingshu_ng`` 时最先执行：在 ``sys.meta_path`` 首位装一个 finder——**标准库名**与
**由 lingshu_ng 包内发起**的顶层导入，不经 cwd 类 ``sys.path`` 条目（``''`` / ``.`` / 等于 cwd）
解析；宿主自己的导入原样放行，``sys.path`` 本身不被改写（#273）。

精确范围：消除 cwd/空串 ``sys.path`` 解析面。仍不覆盖：进程已被预置投毒（``sys.modules``
预置、进程内 ``sys.path.insert``、别名冒充）、逃生口 ``LINGSHU_ALLOW_CWD_IMPORTS`` 被显式打开。
纯标准库，只触碰 ``sys`` 与已加载的 ``os``。
"""
import sys as _sys

_os = _sys.modules.get("os")
ALLOW_ENV = "LINGSHU_ALLOW_CWD_IMPORTS"
_PKG = __name__.rsplit(".", 1)[0]
_STATE = {"applied": False, "escape": False, "warned": False}
_PathFinder = _sys.modules["_frozen_importlib_external"].PathFinder
_Frozen = getattr(_sys.modules.get("_frozen_importlib"), "FrozenImporter", None)
_STDLIB = frozenset(getattr(_sys, "stdlib_module_names", ()) or ())


def _pkg_home():
    """本包所在的 sys.path 目录（lingshu_ng 的父目录）。cwd 恰是它时，从这里解析与 lingshu_ng 本身同信任，
    不构成 cwd 遮蔽面（否则在仓库根运行时连同仓的伴随包 lingshu 也会被拦，见 world.compat 旧别名）。"""
    f = globals().get("__file__")
    if _os is None or not f:
        return None
    try:
        return _os.path.normcase(_os.path.dirname(_os.path.dirname(_os.path.abspath(f))))
    except (OSError, ValueError):
        return None


_HOME = _pkg_home()


def _escape_open() -> bool:
    v = _os.environ.get(ALLOW_ENV, "") if _os is not None else ""
    return v.strip().lower() in ("1", "true", "yes", "on")


def _is_cwd_entry(entry) -> bool:
    """``''`` / ``.`` / ``./`` / 归一后等于 cwd 的条目。"""
    if not isinstance(entry, str):
        return False
    if entry in ("", ".", "./", ".\\"):
        return True
    if _os is None:
        return False
    try:
        norm = _os.path.normcase
        return norm(_os.path.abspath(entry)) == norm(_os.path.abspath(_os.getcwd()))
    except (OSError, ValueError):
        return False


def _from_pkg() -> bool:
    """调用栈上是否有本包（lingshu_ng / lingshu_ng.*，本模块除外）的帧。"""
    f = _sys._getframe(1)
    while f is not None:
        n = f.f_globals.get("__name__")
        if isinstance(n, str) and (n == _PKG or n.startswith(_PKG + ".")) and n != __name__:
            return True
        f = f.f_back
    return False


def _cwd_is_home() -> bool:
    """cwd 是否就是本包所在目录（此时非标准库名从 cwd 解析与本包同源，放行；标准库名仍受护）。"""
    try:
        return _HOME is not None and _os.path.normcase(_os.path.abspath(_os.getcwd())) == _HOME
    except (OSError, ValueError):
        return False


class _CwdGuardFinder:
    """受护导入（标准库名 / 本包发起）在 cwd 类条目能解析到同名模块时，改只在安全条目上解析。"""

    def find_spec(self, fullname, path=None, target=None):
        """顶层受护名：能从 cwd 条目解析到同名 ⇒ 只在安全条目上解析（找不到即 ModuleNotFoundError）。"""
        if path is not None or "." in fullname or fullname in _sys.builtin_module_names:
            return None
        cwd = [e for e in list(_sys.path) if _is_cwd_entry(e)]
        if not cwd or (fullname not in _STDLIB and (not _from_pkg() or _cwd_is_home())):
            return None
        if _Frozen is not None and _Frozen.find_spec(fullname) is not None:
            return None
        if _PathFinder.find_spec(fullname, cwd) is None:
            return None
        spec = _PathFinder.find_spec(fullname, [e for e in list(_sys.path) if not _is_cwd_entry(e)])
        if spec is not None:
            return spec
        err = ModuleNotFoundError("No module named '%s'" % fullname)
        err.name = fullname
        raise err

    def invalidate_caches(self):
        """无缓存。"""
        return None


_GUARD = _CwdGuardFinder()


def scrub() -> bool:
    """装护栏（幂等）；逃生口打开时卸下并告警一次。返回护栏是否在位。"""
    _STATE["applied"] = True
    if _escape_open():
        _STATE["escape"] = True
        while _GUARD in _sys.meta_path:
            _sys.meta_path.remove(_GUARD)
        if not _STATE["warned"]:
            _STATE["warned"] = True
            _sys.stderr.write(f"WARNING: {ALLOW_ENV}=1 ⇒ cwd 解析护栏已放弃（cwd 同名模块仍可在本进程执行）\n")
        return False
    _STATE["escape"] = False
    if _GUARD not in _sys.meta_path:
        _sys.meta_path.insert(0, _GUARD)
    return True


def guard_active() -> bool:
    """护栏 finder 是否在 ``sys.meta_path`` 上。"""
    return _GUARD in _sys.meta_path


def pathguard_report() -> dict:
    """只读摘要（不含本机绝对路径）。"""
    return {"applied": _STATE["applied"], "cwd_scrub_active": guard_active(),
            "escape_hatch_env": ALLOW_ENV, "escape_hatch_open": _STATE["escape"],
            "cwd_entries_now": sum(1 for e in _sys.path if _is_cwd_entry(e)), "sys_path_mutated": False}


scrub()
