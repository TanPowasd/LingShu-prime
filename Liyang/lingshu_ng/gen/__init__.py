# -*- coding: utf-8 -*-
"""lingshu_ng.gen · 白箱文生图主干（文字 → 关系 → 合法窗摆位 → 层序渲染 → 读像素验证）。

模块：
- ids     稳定 sha256 标识（取代内建 hash()）
- layout  合法位置窗 ``LegalWindow``（具名字段 dataclass）+ 同格多部件不相交摆位求解
- attrs   像素级属性读出（花纹/尺寸，旧 extract_attributes 口径）
- verify  构造性验证：只从成图像素读回落格/颜色/花纹/形状尺寸覆盖
- hexgen  编译、渲染、变换、端到端
- pack_certify  同格多件铺位穷举证书（研究脚本迁移，无语料部分）
- multi_seed    同 prompt 多次渲染量测的模板解析/选题/稳定 id/三件事统计
- align_probe   跨源对齐探针的命名映射/距离贡献/命中统计
"""
