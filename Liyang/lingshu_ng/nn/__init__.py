# -*- coding: utf-8 -*-
"""lingshu_ng.nn · 蜂窝 CNN 线重写（纯 numpy + Pillow）。

模块：
- hexgrid  轴坐标晶格唯一来源（画幅内构造、Voronoi 采样）
- conv     六边形卷积 im2col + 单次 GEMM、解析反向、朴素参考
- net      参数仓（原子更新）、浅层/层级两种拓扑、增量扰动求值
- train    符号更新训练（seq/par）、解析梯度对照、plan 执行
- infogap  信息差门控递归训练（生长/验证/撤销）、掩码重建预训练
- text     文本 → 属性解析（词表分类先行、最长匹配、互斥消解）
- render   部件栅格化与显式层序合成
- recon    区域 → 关系连接（显式 z）→ 复原
- stcnn    归一化体素 3D 卷积、时空原语、时间锚点、写入日志自校验记忆
- scenes   合成场景（显式 RNG）
- multimodal / search  图文融合四态、递归四态搜索
- compat   旧 ``lingshu.nn.*`` 同名适配 + 导入钩子
"""
