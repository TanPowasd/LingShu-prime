# 测试用环境模拟：等同于「装了 onnxruntime 但原生库加载失败」（Windows 上 DLL 被拒的同形异常）。
# 只在 PYTHONPATH 显式加入本目录时生效。
raise ImportError("DLL load failed while importing onnxruntime_pybind11_state: access denied "
                  "(simulated by tests_ng/_envsim/ort_broken)")
