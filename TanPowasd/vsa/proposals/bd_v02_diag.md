# body_date v0.2 dev 诊断（描述性；不是判定）

诊断 ≠ 判定：规则事后写成（看过 RESULTS_body_date 三类失败题），阈值网格只为看敏感度，不据此选值；保留集 crossproj-zh-bodydate 未打开。

## perltqa（54 时间题）

L1 答对题的来源：{"body|skip_via_interference": 1, "first|rank1": 15, "first|skip_via_interference": 2}

| 规则 | 对 | 胜/负 vs L1 | 修 BD 错 | 伤 BD 对 | first 类 L1 对→错 |
|---|---:|---|---|---|---|
| L1 | 18 | 0/0 | 冯伟#events#191, 徐佳#dialogues#145, 韩刚#events#80 | 孙晓明#dialogues#149, 龙美丽#events#47 | — |
| BD | 17 | 2/3 | — | — | 冯伟#events#191, 韩刚#events#80 |
| X1 | 18 | 0/0 | 冯伟#events#191, 徐佳#dialogues#145, 韩刚#events#80 | 孙晓明#dialogues#149, 龙美丽#events#47 | — |
| X2(δ=0.02) | 16 | 1/3 | — | 孙晓明#dialogues#149 | 冯伟#events#191, 韩刚#events#80 |
| X2(δ=0.05) | 17 | 1/2 | 冯伟#events#191 | 孙晓明#dialogues#149 | 韩刚#events#80 |
| X2(δ=0.1) | 17 | 1/2 | 冯伟#events#191 | 孙晓明#dialogues#149 | 韩刚#events#80 |
| X3 | 16 | 3/5 | 冯伟#events#191, 李华#events#116 | 何峰#events#77, 田洋#dialogues#261, 田洋#events#138 | 何峰#events#77, 田洋#dialogues#261, 田洋#events#138, 韩刚#events#80 |
| E1-J≥0.3 | 18 | 2/2 | 徐佳#dialogues#145 | — | 冯伟#events#191, 韩刚#events#80 |
| E1-J≥0.4 | 18 | 2/2 | 徐佳#dialogues#145 | — | 冯伟#events#191, 韩刚#events#80 |
| E1-J≥0.5 | 18 | 2/2 | 徐佳#dialogues#145 | — | 冯伟#events#191, 韩刚#events#80 |
| E1-J≥0.6 | 17 | 2/3 | — | — | 冯伟#events#191, 韩刚#events#80 |
| E2-J≥0.5+问句形+无本句日期 | 18 | 2/2 | 徐佳#dialogues#145 | — | 冯伟#events#191, 韩刚#events#80 |
| E3-J≥0.5+问句形→下一句 | 18 | 2/2 | 徐佳#dialogues#145 | — | 冯伟#events#191, 韩刚#events#80 |
| E1-C≥0.3 | 17 | 2/3 | 田洋#dialogues#210 | 龙美丽#events#47 | 冯伟#events#191, 韩刚#events#80 |
| E1-C≥0.4 | 17 | 1/2 | 徐佳#dialogues#145 | 龙美丽#events#47 | 冯伟#events#191, 韩刚#events#80 |
| E1-C≥0.5 | 17 | 1/2 | 徐佳#dialogues#145 | 龙美丽#events#47 | 冯伟#events#191, 韩刚#events#80 |
| E1-C≥0.6 | 18 | 2/2 | 徐佳#dialogues#145 | — | 冯伟#events#191, 韩刚#events#80 |
| E2-C≥0.5+问句形+无本句日期 | 18 | 2/2 | 徐佳#dialogues#145 | — | 冯伟#events#191, 韩刚#events#80 |
| E3-C≥0.5+问句形→下一句 | 18 | 2/2 | 徐佳#dialogues#145 | — | 冯伟#events#191, 韩刚#events#80 |
| X4 | 19 | 2/1 | 冯伟#events#191, 韩刚#events#80 | — | — |
| E4-问句形+无本句日期(无相似度门槛) | 18 | 2/2 | 徐佳#dialogues#145 | — | 冯伟#events#191, 韩刚#events#80 |
| X4+E2-J | 20 | 2/0 | 冯伟#events#191, 徐佳#dialogues#145, 韩刚#events#80 | — | — |
| X4+E3-J | 20 | 2/0 | 冯伟#events#191, 徐佳#dialogues#145, 韩刚#events#80 | — | — |
| X4+E4 | 20 | 2/0 | 冯伟#events#191, 徐佳#dialogues#145, 韩刚#events#80 | — | — |
| X1+E2-J | 18 | 0/0 | 冯伟#events#191, 徐佳#dialogues#145, 韩刚#events#80 | 孙晓明#dialogues#149, 龙美丽#events#47 | — |
| X1+E3-J | 18 | 0/0 | 冯伟#events#191, 徐佳#dialogues#145, 韩刚#events#80 | 孙晓明#dialogues#149, 龙美丽#events#47 | — |
| X2(δ=0.05)+E2-J | 18 | 1/1 | 冯伟#events#191, 徐佳#dialogues#145 | 孙晓明#dialogues#149 | 韩刚#events#80 |

## locomo（50 时间题）

L1 答对题的来源：{"-|rank1": 20, "-|skip_via_no_time": 8}

| 规则 | 对 | 胜/负 vs L1 | 修 BD 错 | 伤 BD 对 | first 类 L1 对→错 |
|---|---:|---|---|---|---|
| L1 | 28 | 0/0 | — | — | — |
| BD | 28 | 0/0 | — | — | — |
| X1 | 28 | 0/0 | — | — | — |
| X2(δ=0.02) | 28 | 0/0 | — | — | — |
| X2(δ=0.05) | 28 | 0/0 | — | — | — |
| X2(δ=0.1) | 28 | 0/0 | — | — | — |
| X3 | 29 | 1/0 | conv-47_21 | — | — |
| E1-J≥0.3 | 28 | 0/0 | — | — | — |
| E1-J≥0.4 | 28 | 0/0 | — | — | — |
| E1-J≥0.5 | 28 | 0/0 | — | — | — |
| E1-J≥0.6 | 28 | 0/0 | — | — | — |
| E2-J≥0.5+问句形+无本句日期 | 28 | 0/0 | — | — | — |
| E3-J≥0.5+问句形→下一句 | 28 | 0/0 | — | — | — |
| E1-C≥0.3 | 28 | 0/0 | — | — | — |
| E1-C≥0.4 | 28 | 0/0 | — | — | — |
| E1-C≥0.5 | 28 | 0/0 | — | — | — |
| E1-C≥0.6 | 28 | 0/0 | — | — | — |
| E2-C≥0.5+问句形+无本句日期 | 28 | 0/0 | — | — | — |
| E3-C≥0.5+问句形→下一句 | 28 | 0/0 | — | — | — |
| X4 | 28 | 0/0 | — | — | — |
| E4-问句形+无本句日期(无相似度门槛) | 28 | 0/0 | — | — | — |
| X4+E2-J | 28 | 0/0 | — | — | — |
| X4+E3-J | 28 | 0/0 | — | — | — |
| X4+E4 | 28 | 0/0 | — | — | — |
| X1+E2-J | 28 | 0/0 | — | — | — |
| X1+E3-J | 28 | 0/0 | — | — | — |
| X2(δ=0.05)+E2-J | 28 | 0/0 | — | — | — |

