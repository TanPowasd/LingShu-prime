# -*- coding: utf-8 -*-
"""_consts · 兼容门面类定义期用到的常量（stab-r13：冷 import 延迟加载）

``import lingshu_ng.compat`` 时 ``SpacetimeMemoryEngine`` 的类属性与缺省参数要用到下面几个值；
它们原本定义在 :mod:`lingshu_ng.exchange` / :mod:`lingshu_ng.self_model` / :mod:`lingshu_ng.compat_store`，
三者都会连带载入存储层与检索层。值移到这里（纯常量、无导入），原模块从这里再导出**同一对象**，
名字、取值与 ``is`` 关系都不变。非公开 API。
"""
from typing import Tuple

#: :data:`lingshu_ng.exchange.TABLES`（M13 全库导出 / 导入的表清单）
TABLES: Tuple[str, ...] = ("nodes", "edges", "blindspots", "skills", "promotion_proposals",
                           "protections", "rejected_paths", "verifier_standards",
                           "escalation_points", "entities",
                           # 上游 #270：OBS-REV1 持久化表（D 序列 / 行为日志 / 飞轮基线等）同样进全库备份
                           "gap_history", "action_logs", "engine_meta", "flywheel_reuse",
                           "self_snapshots", "activation_nodes")
#: :data:`lingshu_ng.self_model.SNAPSHOT_KEEP`
SNAPSHOT_KEEP = 200
#: :data:`lingshu_ng.compat_store.CAUSAL_MAX_PATHS`（上游 ``_CAUSAL_MAX_PATHS``，#327）
CAUSAL_MAX_PATHS = 1000
