# -*- coding: utf-8 -*-
"""样本外泛化核查（非判定口径）：HMB e2e 逐轮续接支撑（prime-test item3_e2e_stream 口径，16 份对话、≈4041 轮查询 + 87 题卡），
只换 ng 臂的代码/配置。python e2e_ax.py <tag> <ng_root> '<LINGSHU_NG_ASSOC json>' <文件序号…>
输出 runs/e2e/<tag>/e2e_XX.json（与 item3 同结构；只 import item3 / 队友函数，不改）。"""
import os, sys
sys.path.insert(0, "/workspace/work/ls/prime-test/work")
import ptlib
import item3_e2e_stream as I3
tag, root, cfg = sys.argv[1], sys.argv[2], sys.argv[3]
ptlib.NG = root
I3.run_ng.__globals__["NG"] = root
os.environ["LINGSHU_NG_ASSOC"] = cfg
I3.D3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs", "e2e", tag)
os.makedirs(I3.D3, exist_ok=True)
for fi in map(int, sys.argv[4:]):
    I3.run_file(fi, ["ng"])
