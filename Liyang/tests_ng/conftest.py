# -*- coding: utf-8 -*-
"""tests_ng 公共夹具（stab-r1：测试确定性）。

- 每个用例前后快照 / 还原进程内单例（semrank 的打分件 / 稠密件 / 判别头缓存与不可用原因、插件注册表）、``LINGSHU_*`` 环境变量
  与 :func:`lingshu_ng.types.now` 的时钟注入，杜绝跨文件状态泄漏；
- ``no_models``：把三个模型件固定为不可用（与机器上装了什么无关）；
- ``frozen_clock``：把引擎时钟冻结在用例开始时刻（:func:`lingshu_ng.types.now` 仍严格单调，按 ULP 递增），
  使「同一引擎上两次召回逐位相同」类断言不受两次调用间流逝的毫秒影响；
- 报告头打印可选依赖与中文语义通路的生效档位（本机实际跑的是哪一档）。
"""
import os
import time

import pytest

from lingshu_ng import plugins, semrank, types

_CACHES = ("_SCORERS", "_EMBEDDERS", "_DISC", "_REASONS")


@pytest.fixture(autouse=True)
def _ng_isolation():
    saved = {n: dict(getattr(semrank, n)) for n in _CACHES if hasattr(semrank, n)}
    env = {k: v for k, v in os.environ.items() if k.startswith("LINGSHU")}
    clock = types._clock
    reg = (dict(plugins._EXPLICIT), plugins._FOUND)   # split-r1：插件注册表（显式注册 / 发现结果）同样逐用例还原
    yield
    plugins._EXPLICIT.clear()
    plugins._EXPLICIT.update(reg[0])
    plugins._FOUND = reg[1]
    for n, d in saved.items():
        cur = getattr(semrank, n)
        cur.clear()
        cur.update(d)
    for k in [k for k in os.environ if k.startswith("LINGSHU") and k not in env]:
        del os.environ[k]
    for k, v in env.items():
        if os.environ.get(k) != v:
            os.environ[k] = v
    if types._clock is not clock:
        types.set_clock(clock)


@pytest.fixture
def no_models(monkeypatch):
    """交叉编码打分件、稠密件、复打件一律不可用（模拟无 onnxruntime / 无模型的机器）。"""
    monkeypatch.setattr(semrank, "get_scorer", lambda: None)
    monkeypatch.setattr(semrank, "get_embedder", lambda: None)
    monkeypatch.setattr(semrank, "get_casc_scorer", lambda: None)


@pytest.fixture
def frozen_clock():
    """引擎时钟冻结在用例开始的墙钟时刻（严格单调的 ULP 递增保留）。"""
    t0 = time.time()
    prev = types.set_clock(lambda: t0)
    yield t0
    types.set_clock(prev)


_TIER_LINES = []


def _tier_lines():
    """可选依赖与语义档位的展示行（会话内只探测一次；在任何用例改动单例 / 环境之前取）。"""
    if _TIER_LINES:
        return _TIER_LINES
    try:
        from lingshu_ng.capabilities import capabilities
        c = capabilities()
    except Exception as e:  # 只做展示：探测失败不影响测试，如实打印原因
        _TIER_LINES.append(f"lingshu_ng capabilities: 探测失败 {type(e).__name__}: {e}")
        return _TIER_LINES
    deps = ", ".join(f"{n}={'ok' if d['available'] else 'unavailable'}" for n, d in c["dependencies"].items())
    lines = [f"lingshu_ng optional deps: {deps}",
             f"lingshu_ng semantic tier (zh long requests): {c['semantic_tier']}"]
    for n, m in c["models"].items():
        if not m["available"]:
            lines.append(f"  {n}: unavailable — {m['reason']}")
    for n, d in c["dependencies"].items():
        if d["error"]:
            lines.append(f"  {n}: {d['error']}")
    _TIER_LINES.extend(lines)
    return _TIER_LINES


def pytest_report_header(config):
    return _tier_lines()


def pytest_sessionstart(session):
    _tier_lines()


def pytest_terminal_summary(terminalreporter):
    """-q 模式下报告头不显示：结尾再打印一次本机生效档位。"""
    terminalreporter.write_sep("-", "lingshu_ng 本机生效档位")
    for line in _tier_lines():
        terminalreporter.write_line(line)



#: 只有 world/ 与 nn/ 子树依赖这两个可选包（pyproject 的 world/nn/full extras）；核心测试必须在纯标准库下可收集。
_HEAVY_DIRS = (os.sep + "world" + os.sep, os.sep + "nn" + os.sep)
_HEAVY_DEPS = ("numpy", "PIL")


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    """最小环境（不装 numpy / Pillow）下，world/、nn/ 测试模块的导入失败改报为 skip（带原因），不再中断整个收集。

    只在「失败原因确为这两个包缺失」时改写；装了这两个包时本钩子不改变任何结果，其他目录与其他导入错误照常报错。
    """
    outcome = yield
    rep = outcome.get_result()
    if not rep.failed or not isinstance(collector, pytest.Module):
        return
    path = str(collector.path)
    if not any(d in path for d in _HEAVY_DIRS):
        return
    text = str(rep.longrepr)
    for dep in _HEAVY_DEPS:
        if f"No module named '{dep}'" in text:
            rep.outcome = "skipped"
            rep.longrepr = (path, 0, f"Skipped: 可选依赖 {dep} 未安装（world/nn 需要 pip install -e \".[full]\"）")
            return


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """同上，用例体内才导入 numpy / Pillow 的 world/、nn/ 用例：缺包导致的失败改报为 skip（其余失败照常）。"""
    outcome = yield
    rep = outcome.get_result()
    if not rep.failed or call.excinfo is None or not call.excinfo.errisinstance(ModuleNotFoundError):
        return
    if not any(d in str(item.path) for d in _HEAVY_DIRS):
        return
    name = getattr(call.excinfo.value, "name", None) or ""
    dep = name.split(".")[0]
    if dep in _HEAVY_DEPS:
        rep.outcome = "skipped"
        rep.longrepr = (str(item.path), item.location[1] or 0,
                        f"Skipped: 可选依赖 {dep} 未安装（world/nn 需要 pip install -e \".[full]\"）")
