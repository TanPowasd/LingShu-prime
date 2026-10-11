# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""旧路径兼容层：RRF3 已于 2026-10-11 改名为 TriCue，实现位于 ../tricue/tricue.py。

旧脚本里的 `sys.path += [agm/rrf3]; import rrf3` 依然可用，导出的内容与 tricue 完全相同。
新代码请直接 `import tricue` 并使用 TriCueMemory。
"""
import pathlib
import sys

_T = str(pathlib.Path(__file__).resolve().parent.parent / "tricue")
if _T not in sys.path:
    sys.path.insert(0, _T)
from tricue import *  # noqa: E402,F401,F403
from tricue import TriCueMemory, RRF3Memory, Hit, BM25_DF_CAP_V10, TEMPORAL_FAR, __all__  # noqa: E402,F401
import tricue as _tc  # noqa: E402

def __getattr__(name):  # 私有辅助（rrf、tokenize 等）同样转发
    return getattr(_tc, name)
