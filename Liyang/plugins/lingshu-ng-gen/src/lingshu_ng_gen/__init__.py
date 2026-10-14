# -*- coding: utf-8 -*-
"""lingshu_ng.gen（插件 lingshu-ng-gen，顶层包 lingshu_ng_gen）· 白箱文生图主干（文字 → 关系 → 合法窗摆位 → 层序渲染 → 读像素验证）。

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

__version__ = "1.29.0"   # 插件 lingshu-ng-gen 的版本（独立于核心；首个独立发布与核心 1.24.0 同号）


#: 对外入口（stab-r5 登记）：研究脚本 / 评测按名使用、包内其它模块不 import 的子模块。
#: ``lingshu_ng.gen.<名>`` 属性访问时懒加载（文生图件依赖 PIL，不随 ``import lingshu_ng.gen`` 载入）。
ENTRY_MODULES = ("hexgen", "composite", "pack_certify", "align_probe")


_LOADING = set()


def __getattr__(name):
    # 重入（``from . import`` 的 fromlist 处理先 hasattr(包, 名)）⇒ AttributeError，交还导入系统去载入子模块
    if name not in ENTRY_MODULES or name in _LOADING:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    _LOADING.add(name)
    try:
        if name == "hexgen":
            from . import hexgen as m
        elif name == "composite":
            from . import composite as m
        elif name == "pack_certify":
            from . import pack_certify as m
        elif name == "align_probe":
            from . import align_probe as m
    finally:
        _LOADING.discard(name)
    return m


def __dir__():
    return sorted(set(globals()) | set(ENTRY_MODULES))
