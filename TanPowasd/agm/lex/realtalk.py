# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""REALTALK 读取（danny911kr/REALTALK@b903e06a，data/Chat_*.json；数据不入库，按 README 自行下载）。
与 confluence/extract.items 同格式：turns = "说话人: 文本"（有 blip_caption 时追加 [image: …]），ids = dia_id，sess = 会话序号。
注意 REALTALK 的 dia_id 前缀与会话号不对齐（session_4 从 D3:30 起），会话号取 session_N 的 N。"""
import glob, json, os


def items(root):
    out = []
    for f in sorted(glob.glob(os.path.join(root, "Chat_*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        ns = sorted(int(k.split("_")[1]) for k in d if k.startswith("session_") and k.split("_")[1].isdigit() and len(k.split("_")) == 2)
        turns, ids, sess = [], [], []
        for i in ns:
            for t in d[f"session_{i}"]:
                txt = f"{t['speaker']}: {t.get('clean_text') or ''}"
                if t.get("blip_caption"):
                    txt += f" [image: {t['blip_caption']}]"
                turns.append(txt); ids.append(t["dia_id"]); sess.append(i)
        out.append({"sid": os.path.basename(f)[:-5], "turns": turns, "ids": ids, "sess": sess, "qa": d["qa"]})
    return out
