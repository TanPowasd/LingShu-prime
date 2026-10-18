# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""PerLTQA 中文检查集（PREREG_all.md §PerLTQA）。数据 CC BY-NC 4.0，不入库：$UMB_PERLTQA 指向 Dataset/zh 目录。
每个有题角色一个记忆库；单元 = profile 字段 / social_relationship 条 / events 条 / dialogues 条；金标 = Reference Memory。
split = md5(角色名) %2：0=dev，1=test。"""
import ast, datetime, hashlib, json, os, pathlib, re

SRC = "https://github.com/Elvin-Yiming-Du/PerLTQA"
COMMIT = "8d9e19868e239740ef701e603ec205cd581f221b"
SHA = {"perltqa.json": "aa19a0623312b5ffe1153ee5d04e20e0d054ba27eccc4f35baa9710a6e8ca9bd",
       "perltmem.json": "5869ee39e944cf835af5c163c5213723bd2d30c44eb6705271031a644ee0ab7b"}
FIELD_ZH = {"Gender": "性别", "Nickname": "昵称", "Title": "头衔", "Age": "年龄", "Occupation": "职业", "Nationality": "国籍",
            "Physical Characteristics": "外貌特征", "Hobbies": "爱好", "Achievements": "成就", "Ethnic Background": "种族背景",
            "Education Background": "教育背景", "Employer": "雇主", "Awards and Role Models": "奖项与榜样"}
_D1 = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_D2 = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?")
PRE = {"social_relationship": "S:", "events": "E:", "dialogues": "D:"}


def root():
    p = os.environ.get("UMB_PERLTQA")
    if not p:
        raise FileNotFoundError("存疑：未设 UMB_PERLTQA（指向 PerLTQA 的 Dataset/zh）")
    return pathlib.Path(p)


def _days(y, mo, d, hh=0, mm=0):
    try:
        return datetime.date(int(y), int(mo), int(d)).toordinal() + (int(hh) * 60 + int(mm)) / 1440.0
    except ValueError:
        return None


def parse_time(s):
    s = str(s or "")
    m = _D2.search(s)
    if m:
        return _days(*[x or 0 for x in m.groups()])
    m = _D1.search(s)
    return _days(*m.groups()) if m else None


def split_of(name):
    return "dev" if int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % 2 == 0 else "test"


def units(mem):
    """→ (ids, texts, times)。"""
    name = mem["profile"]["Protagonist"]
    ids, texts, times = [], [], []
    for k, v in mem["profile"].items():
        if k == "Protagonist":
            continue
        ids.append("P:" + k); texts.append(f"{name}的{FIELD_ZH.get(k, k)}：{v}"); times.append(None)
    for k, v in mem["social_relationship"].items():
        ids.append("S:" + k)
        texts.append(f"{name}与{v.get('Supporting Characters', '')}的关系：{v.get('Relationship', '')}。{v.get('Description', '')}")
        times.append(None)
    for k, v in mem["events"].items():
        ids.append("E:" + k)
        texts.append(f"{v.get('Creation Time', '')} {v.get('summary', '')}：{v.get('content', '')}")
        times.append(parse_time(v.get("Creation Time")))
    for k, v in mem["dialogues"].items():
        ids.append("D:" + k)
        cs = v.get("contents", {})
        flat = lambda xs: [y for x in xs for y in (flat(x) if isinstance(x, list) else [str(x)])]   # 78 轮是嵌套列表，展平
        texts.append("\n".join(f"{ts}\n" + "\n".join(flat(turns)) for ts, turns in cs.items()))
        times.append(parse_time(next(iter(cs), "")))
    return ids, texts, times


def load(check=True):
    """→ {角色: {"ids","texts","times","qs":[(qid, 问句, 金标单元号集合)]}}, 存疑列表。"""
    r = root()
    raw = {f: (r / f).read_bytes() for f in SHA}
    if check:
        for f, b in raw.items():
            if hashlib.sha256(b).hexdigest() != SHA[f]:
                raise ValueError(f"存疑：{f} sha256 不符，停")
    qa = json.loads(raw["perltqa.json"]); mem = json.loads(raw["perltmem.json"])
    M = {x["profile"]["Protagonist"]: x for x in mem}
    out, doubt = {}, []
    for blk in qa:
        for name, cats in blk.items():
            ids, texts, times = units(M[name])
            ix = {u: i for i, u in enumerate(ids)}
            qs, k = [], 0
            for cat in ("profile", "social_relationship", "events", "dialogues"):
                l = cats.get(cat, [])
                items = l if isinstance(l, list) else [z for _, zs in l.items() for z in zs]
                for z in items:
                    qid = f"{name}#{cat}#{k}"; k += 1
                    ref = z.get("Reference Memory")
                    if cat == "profile":
                        refs = ["P:" + str(ref)]
                    else:
                        try:
                            rr = ast.literal_eval(ref) if isinstance(ref, str) and ref.strip().startswith("[") else [ref]
                        except (ValueError, SyntaxError):
                            rr = [ref]
                        refs = [PRE[cat] + str(t) for t in rr]
                    gold = {ix[u] for u in refs if u in ix}
                    if not gold or len(gold) != len(refs):
                        doubt.append((qid, ref)); continue
                    qs.append((qid, z["Question"], gold))
            out[name] = {"ids": ids, "texts": texts, "times": times, "qs": qs}
    return out, doubt


def qids(split, data=None):
    data = data or load()[0]
    return [q for name in sorted(data) if split_of(name) == split for q, _, _ in data[name]["qs"]]
