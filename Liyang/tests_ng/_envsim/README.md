# 环境模拟（测试确定性验收用）

把对应目录放到 `PYTHONPATH` 最前面即可模拟三种「可选依赖不可用」与一种「粗时钟」环境，子进程也会继承：

| 目录 | 模拟 | 用法 |
|---|---|---|
| `no_ort/` | 未安装 onnxruntime（`import onnxruntime` 抛 `ModuleNotFoundError`） | `PYTHONPATH=tests_ng/_envsim/no_ort python -m pytest tests_ng -q` |
| `ort_broken/` | 装了但 DLL 加载失败（`import onnxruntime` 抛 `ImportError: DLL load failed ...`，与 Windows 上损坏安装同形） | `PYTHONPATH=tests_ng/_envsim/ort_broken python -m pytest tests_ng -q` |
| `coarse_clock/` | Windows 式粗粒度墙钟（`time.time()` 量化到 1/64 s ≈ 15.6 ms） | `PYTHONPATH=tests_ng/_envsim/coarse_clock python -m pytest tests_ng -q` |

「无模型」不需要模拟目录：设 `LINGSHU_NG_SEM=off`（交叉编码 / 稠密件全部不可用），并且不设 `LINGSHU_NG_EMBED_MODEL`。

这些目录只在测试验收时手动加入路径；包本身与常规测试都不会导入它们。
