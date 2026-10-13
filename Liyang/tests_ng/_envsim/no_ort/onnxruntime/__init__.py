# 测试用环境模拟：等同于「未安装 onnxruntime」。只在 PYTHONPATH 显式加入本目录时生效。
raise ModuleNotFoundError("No module named 'onnxruntime' (simulated by tests_ng/_envsim/no_ort)", name="onnxruntime")
