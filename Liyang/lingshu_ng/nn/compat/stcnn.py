# -*- coding: utf-8 -*-
"""compat.stcnn · 旧 ``lingshu.nn.stcnn`` 同名适配（委托 :mod:`lingshu_ng.nn.stcnn`）。

有意差异：``moving`` 与帧差/轨迹同一口径（存在 >2 变化像素的帧）；新增 ``motion_energy``
（均值，分辨率无关）；``frame_diff`` 期望归一化体素输入。
"""
from __future__ import annotations

from ..stcnn import (MOTION_KERNEL, SPATIAL_KERNEL, SpatiotemporalMemory, conv3d, detect_period,  # noqa: F401
                     extract_spatiotemporal_primitives, frame_diff, frames_to_voxel, max_pool3d, motion_direction,
                     motion_speed, synth_ball_rolling, synth_blinking, synth_static)
