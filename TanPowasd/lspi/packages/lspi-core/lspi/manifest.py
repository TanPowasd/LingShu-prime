"""插件清单：插件对底座的全部声明。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Tuple

LSPI_VERSION = (1, 0)          # 本底座实现的协议版本
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_RANGE = re.compile(r"^\s*>=\s*(\d+)\s*,\s*<\s*(\d+)\s*$")


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class PluginManifest:
    name: str                          # 插件名＝能力名（二段式：能力 + action）
    version: str                       # 插件自身版本
    lspi: str                          # 兼容协议区间，形如 ">=1,<2"
    actions: Tuple[str, ...]           # 本能力支持的 action
    requires: Tuple[str, ...] = ()     # 依赖的其他能力名（不按包名）
    reads: Tuple[str, ...] = ()        # 读哪些层：knowledge / context / structure …
    writes: Tuple[str, ...] = ()       # 写入的记录种类（写入闸按此授权）
    extras: Tuple[str, ...] = ()       # 声明的重依赖（审计/安装提示用）
    summary: str = ""

    def validate(self) -> None:
        if not _NAME.match(self.name):
            raise ManifestError(f"非法插件名 {self.name!r}")
        m = _RANGE.match(self.lspi)
        if not m:
            raise ManifestError(f"{self.name}: lspi 区间须形如 '>=1,<2'，得 {self.lspi!r}")
        if not self.actions:
            raise ManifestError(f"{self.name}: actions 不能为空")
        for k in self.writes:
            if not re.match(r"^[a-z]+\.[a-z_]+$", k):
                raise ManifestError(f"{self.name}: 写入种类须为 '域.种类'，得 {k!r}")
        if self.name in self.requires:
            raise ManifestError(f"{self.name}: 不能依赖自身")

    def compatible(self, host=LSPI_VERSION) -> bool:
        lo, hi = (int(x) for x in _RANGE.match(self.lspi).groups())
        return lo <= host[0] < hi

    @property
    def provenance(self) -> str:
        return f"plugin://{self.name}@{self.version}"
