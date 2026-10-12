# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""LLM+ 模式的老师：只在句框/动词表认不出的句子上问 LLM，答案当对齐样本学成句框（之后同句形不再问）。
默认关闭：Learner 不传 llm= 就永远不调用；默认 LLM 函数还要环境变量 LEARN_LLM=1 才肯发请求（防误用 key）。
防编造：主体、取值必须逐字出现在原句里，否则丢弃；属性句中没写出时，学习器只接受记忆里已有的属性名。有磁盘缓存：同一批句子不问第二次。"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re

OPS = ("set", "retire", "unresolved", "resolve")
PROMPT = """下面是记忆材料里的若干句子（带编号）。找出其中陈述「某个主体的某个属性在此刻被设定 / 撤销 / 出现两种并存取值 / 争议被裁定」的句子，逐句抽取。
只输出一个 JSON 对象：{{"items":[{{"i":编号,"s":"主体","a":"属性","op":"set|retire|unresolved|resolve","v":"取值","v2":"并存时的第二个取值","r":"原因"}}]}}
规则：主体、取值必须是原句里逐字出现的片段，不改写；属性只写属性名本身，不带「的」等虚词，句中没写出属性名时写最贴切的属性名；撤销没有取值，v 留空；r 是句中说明这次变化原因的短语（逐字），没有就留空；
回顾往事的句子（如「早先一度」「曾经是」）、不涉及属性取值的句子不要输出。没有就输出 {{"items":[]}}。

{body}"""


def default_llm(prompt):
    """任意 OpenAI 兼容的 chat/completions 接口：LEARN_LLM_URL、LEARN_LLM_MODEL、可选 LEARN_LLM_KEY（Bearer）。
    不设 URL 时用 Cline 代理（沙箱里凭据由网关按主机注入）。temperature=0，不限 max_tokens。"""
    if os.environ.get("LEARN_LLM") != "1":
        raise RuntimeError("LLM+ 默认关闭：设 LEARN_LLM=1 才允许调用真实 LLM")
    import time
    import urllib.request
    url = os.environ.get("LEARN_LLM_URL", "https://api.cline.bot/api/v1/chat/completions")
    model = os.environ.get("LEARN_LLM_MODEL", "cline-pass/deepseek-v4.1-flash")
    hdr = {"Content-Type": "application/json"}
    if os.environ.get("LEARN_LLM_KEY"):
        hdr["Authorization"] = "Bearer " + os.environ["LEARN_LLM_KEY"]
    body = json.dumps({"model": model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]}).encode()
    err = None
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=hdr), timeout=300) as r:
                d = json.loads(r.read())
            d = d.get("data", d)
            txt = d["choices"][0]["message"]["content"]
            if txt and txt.strip():
                return txt
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(3 * (k + 1))
    raise RuntimeError(f"LLM 调用失败: {err}")


class Teacher:
    def __init__(self, llm=None, cache=None, batch=40):
        self.llm = llm or default_llm
        self.cache = pathlib.Path(cache) if cache else None
        self.batch, self.calls, self.cached = batch, 0, 0
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)

    def _ask(self, prompt):
        key = hashlib.sha1(prompt.encode()).hexdigest()
        f = self.cache / f"{key}.txt" if self.cache else None
        if f and f.exists():
            self.cached += 1
            return f.read_text(encoding="utf-8")
        self.calls += 1
        txt = self.llm(prompt)
        if f:
            f.write_text(txt, encoding="utf-8")
        return txt

    def records(self, todo):
        """todo: [(seq, 句子)] → [(seq, 句子, 主体, 属性, 动作, 取值, 第二取值, 原因)]，逐字校验过。"""
        body = "\n".join(f"{i}. {s}" for i, (_q, s) in enumerate(todo))
        txt = self._ask(PROMPT.format(body=body))
        m = re.search(r"\{.*\}", txt, re.S)
        try:
            items = json.loads(m.group(0)).get("items", []) if m else []
        except ValueError:
            items = []
        out = []
        for it in items:
            try:
                seq, sent = todo[int(it["i"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            s, a, op = str(it.get("s") or "").strip(), str(it.get("a") or "").strip(), it.get("op")
            v, v2 = str(it.get("v") or "").strip(), str(it.get("v2") or "").strip()
            r = str(it.get("r") or "").strip()
            r = r if r and r in sent else ""
            if op not in OPS or not s or not a or len(a) > 12 or s not in sent:      # 属性可隐含（「移到了」⇒位置），由学习器核对
                continue
            if op != "retire" and (not v or v not in sent):
                continue
            if op == "unresolved" and (not v2 or v2 not in sent):
                continue
            out.append((seq, sent, s, a, op, v if op != "retire" else "", v2, r))
        return out
