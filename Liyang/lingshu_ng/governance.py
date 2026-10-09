# -*- coding: utf-8 -*-
"""governance · 设计者终裁（D-007）的唯一校验点

不变量：
  G1 密钥只来自环境变量 ``AEIS_DESIGNER_KEY``；未配置或不匹配 ⇒ 拒绝（fail-closed）。
  G2 比较在 UTF-8 字节上做，非 ASCII 密钥不会抛 TypeError（#51）。
  G3 需要终裁的操作**在仓储层**调用 :func:`require_designer`，而不是只在门面上调用
     （根除 #222「门面加锁、store 直通」）。
"""
from __future__ import annotations

import hmac
import os
from typing import Optional

__all__ = ["designer_key_configured", "verify_designer", "require_designer", "DesignerRequired"]

ENV_KEY = "AEIS_DESIGNER_KEY"


class DesignerRequired(PermissionError):
    """缺少有效设计者密钥。"""


def designer_key_configured() -> bool:
    """是否已配置设计者密钥。"""
    return bool(os.environ.get(ENV_KEY))


def verify_designer(designer_key: Optional[object]) -> bool:
    """校验设计者密钥（fail-closed，字节级恒时比较）。

    事实边界（与上游 #156 修订同口径）：
    - 成立：判据 = 调用方传入值 == **本进程**环境变量 ``AEIS_DESIGNER_KEY``；密钥不在仓库与代码中。
    - 不成立：「模型/自动化永远无法读取密钥」——**同进程**代码（构造期装入的组件、被劫持的裸名导入）
      可读 ``os.environ``，对同进程这一表述不成立。
    - 本包的精确防护范围＝**消除** cwd/空串 ``sys.path`` 解析（``lingshu_ng._pathguard``）；仍不覆盖
      进程已被预置投毒（``sys.modules`` 预置 / 进程内 ``sys.path.insert`` / 别名冒充）与逃生口
      ``LINGSHU_ALLOW_CWD_IMPORTS`` 被显式打开。同进程可信性属**设计级**事项（D-007 后续裁定）。
    """
    expected = os.environ.get(ENV_KEY)
    if not expected or not designer_key:
        return False
    return hmac.compare_digest(str(designer_key).encode("utf-8"), expected.encode("utf-8"))


def require_designer(designer_key: Optional[object], action: str = "终裁") -> None:
    """校验失败即抛 :class:`DesignerRequired`。"""
    if not verify_designer(designer_key):
        raise DesignerRequired(
            f"D-007 设计者认证失败（{action}）：密钥无效或未配置 {ENV_KEY}（fail-closed）")
