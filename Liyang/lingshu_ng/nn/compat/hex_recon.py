# -*- coding: utf-8 -*-
"""compat.hex_recon · 旧 ``lingshu.nn.hex_recon`` 同名适配（委托 :mod:`lingshu_ng.nn.recon`）。

有意差异：连接描述带显式 ``z`` 与像素包围盒 ``bbox``；复原按 (z, −面积, id) 绘制，与列表顺序无关。
"""
from __future__ import annotations

from ..recon import (draw_order, extract_regions, pixel_accuracy, psnr, reconstruct,  # noqa: F401
                     regions_to_connections)

ALGO = "hex_recon-ng"
