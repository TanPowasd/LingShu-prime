# -*- coding: utf-8 -*-
"""compat_txguard · 旧 ``lingshu.core.core`` 的两个模块级辅助名（上游 #184 / #267）

* :func:`_store_tx_guard` —— 给「直接用 ``store.conn`` 写裸 SQL」的扩展方法套事务边界：最外层调用
  开事务、异常整体回滚、正常提交；嵌套调用并入外层（内层异常被外层捕获时不回滚外层）。
  ng 自身的仓储写路径一律走 :meth:`Database.tx`（``BEGIN IMMEDIATE`` / ``ROLLBACK``），本守卫与之
  共用同一把锁和同一个嵌套深度计数，二者互相并入、不重复开事务。
* :func:`_loads_tags` —— tags 列容错解析（同 :func:`lingshu_ng.types.loads_tags`）。
"""
from __future__ import annotations

import functools
from typing import Any, Callable

from .types import loads_tags as _loads_tags

__all__ = ["_store_tx_guard", "_loads_tags"]


def _store_tx_guard(fn: Callable) -> Callable:
    """把 ``fn(self, ...)``（self 为兼容门面 LayeredStore）包进可嵌套的事务边界。"""

    @functools.wraps(fn)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        """最外层开事务 → 异常 ROLLBACK / 正常 COMMIT；嵌套并入外层。"""
        db = self.db
        with db.lock:
            outer = db._depth == 0 and not db.conn.in_transaction
            if outer:
                db.conn.execute("BEGIN")
            db._depth += 1
            try:
                result = fn(self, *args, **kwargs)
            except BaseException:
                if outer and db.conn.in_transaction:
                    db.conn.execute("ROLLBACK")
                raise
            finally:
                db._depth -= 1
            if outer and db.conn.in_transaction:
                db.conn.execute("COMMIT")
            return result

    wrapper.__lingshu_tx_guard__ = True
    return wrapper
