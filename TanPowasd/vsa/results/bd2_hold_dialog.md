# VSA 正文日期 BD2 · crossproj-zh-dialog 保留集读数（PREREG_body_date_v0.2.md §3.1，只跑一次）

sha256 `eac6a3d7dbaf14fdff5146f7b0e71b6b1ea679dd4dbb38aa44bd41885e6a6904`；用时 62.3 s

| 读数 | 题数 | L1 | BD2 | BD2 胜/负 | p |
|---|---:|---:|---:|---|---:|
| E1 r@10 | 176 | 0.9943 | 0.9943 | 逐位相同 | — |
| E2 时间解绑 | 144 | 0.3681 | 0.6875 | 47/1 | 3.48e-13 |

| 分型 | 题数 | L1 对 | BD2 对 | 胜/负 | p | L1 对→BD2 错 | BD2 来源 |
|---|---:|---:|---:|---|---:|---|---|
| body_echo | 40 | 7 | 27 | 20/0 | 1.91e-06 | 无 | {'TIME:bd': 40} |
| body_plain | 20 | 0 | 4 | 4/0 | 0.125 | 无 | {'TIME:bd': 20} |
| first_interf | 28 | 8 | 17 | 10/1 | 0.0117 | dg050 | {'TIME:bd': 27, 'TIME': 1} |
| first_plain | 24 | 6 | 19 | 13/0 | 0.000244 | 无 | {'TIME:bd': 22, 'TIME': 2} |
| short_time | 32 | 32 | 32 | 0/0 | 1 | 无 | {'TIME': 32} |

首日期类（§3.3）84 题：L1 46 对 → BD2 68 对；L1 对→BD2 错：dg050。
te10 命中证据 143/144；X4 否决 6 次；E2 标记子痕迹 24 条。
- echo_near：{'n': 25, 'L1': 5, 'BD2': 23, 'flagged_q': 24}
- echo_para：{'n': 15, 'L1': 2, 'BD2': 4, 'flagged_q': 0}
- body_head_form_False：{'n': 41, 'L1': 5, 'BD2': 24}
- body_head_form_True：{'n': 19, 'L1': 2, 'BD2': 7}
- interf：{'decoy_in_te10': 28, 'decoy_before_ev': 2, 'decoy_L1_doubt': 7, 'decoy_has_bd': 28, 'decoy_before_ev_and_doubt': 1}

本集读数：E1 逐位相同 ✓；ΔE2 = +0.3194（不降 ✓）；首日期类逐题不降 ✗；E2 显著上升 ✓（判定见 --decide，需两集合并）。
