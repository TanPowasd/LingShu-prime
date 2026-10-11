# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""零模型源图（不调 LLM）：说话人为主语，句中连续实词串（≤3 词）为宾语，谓词记为“提到”。供汇流零 key 验证。"""
import re
from confluence import STOP
EXTRA = set("just really so very too also like get got going know think yeah yes oh wow thanks thank much lot lots one things thing been have has had will would can could did does do what when where how why there here about from into out up all not no but if than then".split())


def triples(turn):
    sp, _, txt = turn.partition(": ")
    words = re.findall(r"[A-Za-z][A-Za-z'\-]+", txt)
    out, run = [], []
    for w in words + ["."]:
        lw = w.lower()
        if lw in STOP or lw in EXTRA or len(lw) < 3:
            if run:
                for k in range(0, len(run), 3):
                    out.append([sp, "提到", " ".join(run[k:k + 3])])
                run = []
        else:
            run.append(lw)
    return out
