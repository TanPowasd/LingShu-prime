# -*- coding: utf-8 -*-
"""lingshu_ng.world · 世界模型线重写（numpy）。

模块：
- camera   位姿/投影/反投影/深度（全栈唯一来源）
- geometry 基本体网格、法线、背面剔除、平直着色
- raster   z-buffer 光栅化（替代画家算法）
- skeleton 正向运动学（矩阵/四元数两路，父→根一致累积）
- scene    实体、关系谓词、确定性 RNG、推断边取代
- sim      seek/follow 到达判据 + 阻尼
- validate 判据入口 isfinite 校验
- catalog  类别视觉先验 / 部件形状库（纯数据）
- voxel    体素世界（稠密 numpy 网格 + 实体轨迹）
- scene_sim 旧 SceneSimulator + 确定性行为纯函数（世界与影子共用的唯一公式）
- spacetime 时空一致性验证（影子重放 = scene_sim 同一公式）
- world_model / world_learner / curiosity / seven_layer_loop  世界模型、自监督学习、好奇探索、七层闭环
- prediction 预测引擎（D-006 判据如实、命中标签/置信度 isfinite）
- scene_relations 语义关系边 → 空间约束求解（left_of/right_of 修正）
- multiview 多视角射线三角化（按几何分轨）；anchor_graph / anchor_verify 语义锚点图与多感知机验证
- compat   旧 lingshu.world.* 同名适配（含 scene_model 惰性派生）
"""
