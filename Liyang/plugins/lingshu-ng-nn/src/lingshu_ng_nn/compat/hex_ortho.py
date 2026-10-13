# -*- coding: utf-8 -*-
"""compat.hex_ortho · 旧 ``lingshu.nn.hex_ortho`` 同名适配（委托 :mod:`lingshu_ng.nn.ortho`）。"""
from __future__ import annotations

from ..ortho import (DEAD_ZONE, KERNEL_NAMES, MAX_LAYERS, ORTHO_TOL, gram_schmidt_kernels, kname,  # noqa: F401
                     orthogonal_pool, pyramid_report, residual_pyramid)
from .hex_cnn import hex_conv  # noqa: F401

ALGO = "hex_ortho-ng"
