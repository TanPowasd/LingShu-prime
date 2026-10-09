# -*- coding: utf-8 -*-
"""[兼容薄壳] 结构层任务台账已拆到独立包 brain-agenda（任务书 v0.3 · M3）。

替换原 md_cg/tasks.py。内核里仍有 3 处库内调用（mdcos 上下文装配、mdcg 问题身份 slugify、
blindspot_tickets 落任务卡）以 `from . import tasks` 取用——本薄壳让它们解析到同一模块对象。
未装 brain-agenda 时 import 抛 ImportError：mdcos 上下文装配本有 try/except，会把 "tasks"
记入 degraded；另两处的处置见 lspi/README「M3 · 迁移账本」。
"""
import sys

try:
    from brain_agenda import tasks as _impl
except ImportError as e:  # pragma: no cover
    raise ImportError("任务台账已拆为独立包：pip install brain-agenda（或 npm 默认插件集合）") from e

sys.modules[__name__] = _impl
