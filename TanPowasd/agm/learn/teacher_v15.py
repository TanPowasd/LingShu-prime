# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""老师 v15：只读调用 Liyang/lingshu_ng 的零 LLM 版本链抽取（chain-r15），给自主学习当种子。
不修改 Liyang/，不开它的 LLM 臂（LINGSHU_NG_CHAIN_LLM 强制为 0），零网络。
输出对齐样本 (seq, 原句, 主体, 属性, 动作, 取值)：学习器据此把老师会抽、本模块不会抽的句子归纳成句框。"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("LEARN_LIYANG_ROOT") or pathlib.Path(__file__).resolve().parents[3] / "Liyang")
OPS = {"set": "set", "resolve": "resolve", "retire": "retire", "unresolve": "unresolved"}


def records(segs):
    os.environ["LINGSHU_NG_CHAIN_LLM"] = "0"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from lingshu_ng.chain.ledger import Ledger
    L, out = Ledger(), []
    for seq, sid, text in sorted(segs, key=lambda x: (x[0], x[1])):
        for r in L.add_text(text, sid, seq=seq, ns="doc"):
            if r.op in OPS and r.attr:
                out.append((seq, r.quote.strip().rstrip("。"), r.entity, r.attr, OPS[r.op], r.value))
    return out
