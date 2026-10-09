# -*- coding: utf-8 -*-
"""[兼容薄壳] 图像 Skill 已拆到独立包 brain-imgskill（任务书 v0.3 · M2）。

内核里只留这一个文件，替换原 md_cg/imgskill.py，保住两个公开面：
  · `from md_cg import imgskill`  —— 解析到 brain_imgskill.imgskill（同一模块对象）；
  · `python -m md_cg.imgskill …`  —— CLI 照旧（转 brain_imgskill.imgskill.cli_main）。
未装 brain-imgskill 时：import 抛 ImportError 并给出安装提示——不静默降级。
"""
import sys

try:
    from brain_imgskill import imgskill as _impl
except ImportError as e:  # pragma: no cover
    raise ImportError("图像 Skill 已拆为独立包：pip install brain-imgskill（或 npm 默认插件集合）") from e

if __name__ == "__main__":                      # CLI 入口钩子
    sys.exit(_impl.cli_main())
else:
    sys.modules[__name__] = _impl
