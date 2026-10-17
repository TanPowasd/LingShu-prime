# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""MemBench 读取（HF KaLM-Embedding/LMEB，Dialogue/MemBench/<子集>/，数据不入库）；格式同 ConvoMem，单位为「轮次」（一条含 User+Assistant，角色记 user）。
三分（PREREG_tree3.md 读数前固定）：md5("子集/场景")%3 == 0 dev，== 1 保留 A（TR3），== 2 保留 B（留给实体共指轮）。"""
import convomem as _C

SUBS = ("aggregative", "comparative", "emotion", "knowledge_updating", "multi_hop", "multi_session_assistant",
        "post_processing", "preference", "single_hop", "single_session_assistant")
PART = {"dev": 0, "A": 1, "B": 2}


def items(root, split):
    for sub, it in _C.items(root, split, subs=SUBS, nsplit=PART[split]):
        it["roles"] = ["user"] * len(it["turns"])
        yield sub, it
