# lingshu-ng-gen

灵枢 ng（`lingshu-ng`）的插件包：白箱文生图主干（文字 → 关系 → 合法窗摆位 → 层序渲染 → 读像素验证）。核心 `lingshu-ng` 自 1.24 起零外部依赖，本线依赖 numpy / Pillow，故拆为独立包。

```bash
pip install lingshu-ng            # 核心（零依赖）
pip install lingshu-ng-gen
```

## 导入路径不变

规范导入路径仍是 **`lingshu_ng.gen.*`**（与 1.22 相同）：核心的兼容入口（`lingshu_ng._alias`）把本包目录按旧名载入，
模块名、类的 `__module__`、pickle 路径都与 1.22 一致；模块源码与 1.22 逐字相同（只在 `__init__.py` 加了 `__version__`、新增描述对象 `plugin.py`）。
`lingshu_ng_gen` 只是发行包里的存放位置，请不要直接 `import lingshu_ng_gen.<模块>`（包内相对导入以旧名为准）。

没装本插件时，`import lingshu_ng.gen`（及其子模块）抛 `ModuleNotFoundError`，信息写明 `pip install lingshu-ng-gen`；
兼容门面 `SpacetimeMemoryEngine` 的相关外观方法照旧返回「组件不可导入」状态（与 1.22 无 numpy 时相同）。

依赖 `lingshu-ng-nn`（渲染 / 场景 / 文本解析件）。

核心通过入口点组 `lingshu_ng.plugins`（`gen = lingshu_ng_gen.plugin:PLUGIN`）发现本插件，`lingshu_ng.capabilities.capabilities()["plugins"]` 显示版本。

## 测试

```bash
pip install lingshu-ng lingshu-ng-gen pytest
python -m pytest plugins/lingshu-ng-gen/tests_gen
```
（与上游旧实现对照的用例需要仓库根的旧包 `lingshu/`，不在时 skip。）
