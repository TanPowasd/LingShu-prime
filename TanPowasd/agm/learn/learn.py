# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""自主学习 Learn：零模型、零网络、零判官的说法自举（在线扩充动词表 + 巩固重放）。

推理模块的硬伤是动词表：表外说法（「被改动成」「挪去了」）一句也抽不出来，句式扰动下全部掉到 .40。
人会从已经懂的句子里学会新说法：知道「甲 的口令」是一个槽、知道 alpha 是口令的取值，
看到「甲 的口令被改动成 alpha」时就能猜出「被改动成」是一种「改成」。本模块把这件事做成机械规则：

  1. 种子：用现有动词表抽一遍，得到已知槽（主体, 属性）、已知取值池（按属性）、已知主体。
  2. 候选：没抽出事件的句子里，若出现「已知主体 的 已知属性 <连接词> 值」，或「已知主体 <连接词> 值」
     （后者是隐含属性句），把 <连接词> 记为候选。连接词在汉字串里逐位试切，取能让「值」落进取值池的切法。
  3. 晋升：候选须在 ≥ min_slots 个不同槽上出现，且其中 ≥ min_hits 次的值落在该属性的已知取值池里
     （隐含属性句：值须落在该隐含属性的取值池里）。晋升后作「改成」类动词并入动词表。
  4. 巩固：晋升后从原始记忆整库重放（编年链是只追加的，重放才能把早先漏抽的句子补进链里），迭代到不动点。
  在线口径：learn_until 只用序号 ≤ 它的记忆学说法，之后的记忆只用已学到的表抽取（前学后测，不偷看未来）。
跨语料保存：lexicon() 导出学到的说法，Learner(lexicon=…) 在别的语料上直接用（Learner.save/load 存盘）。
不读答案键、不读生成器日志、不调用模型。只学「改成」类；撤销/并存/裁定类说法不学（边界，见 README）。
"""
from __future__ import annotations

import collections
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reason"))
from reason import Reason, VERBS, IMPLICIT, RETRO, SPLIT, _value  # noqa: E402

CJK_RUN = re.compile(r"^([\u4e00-\u9fff]{1,8})\s*(.*)$")
DEF = dict(min_slots=2, min_hits=1, max_rounds=4, value_check=True)


class Learner:
    def __init__(self, learn=True, learn_until=math.inf, lexicon=None, **p):
        self.p = {**DEF, **p}
        self.learn, self.learn_until = learn, learn_until
        self.verbs = {k: tuple(v) for k, v in VERBS.items()}
        self.implicit = {k: tuple(v) for k, v in IMPLICIT.items()}
        self.learned = []                    # [(连接词, 类型, 支持槽数, 取值命中数)]
        self.R = None
        if lexicon:                          # 跨语料保存：载入以前学到的说法
            for row in lexicon:
                self._add(row["conn"], row["kind"])

    def _add(self, conn, kind):
        if kind == "set":
            if conn not in self.verbs["set"]:
                self.verbs["set"] = self.verbs["set"] + (conn,)
        else:
            f = kind.split(":", 1)[1]
            if conn not in self.implicit.get(f, ()):
                self.implicit[f] = self.implicit.get(f, ()) + (conn,)

    def lexicon(self, prior=()):
        """学到的说法（可存盘、可在别的语料上载入）；prior 是先前载入的表，合并去重。"""
        seen, out = set(), []
        for row in list(prior) + [dict(conn=c, kind=k, slots=ns, hits=nh) for c, k, ns, nh in self.learned]:
            if (row["conn"], row["kind"]) not in seen:
                seen.add((row["conn"], row["kind"])); out.append(row)
        return out

    @staticmethod
    def load(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save(path, lexicon):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(lexicon, f, ensure_ascii=False, indent=1)

    def _build(self, segs):
        R = Reason(verbs=self.verbs, implicit=self.implicit)
        R.ingest(segs)
        return R

    def _split(self, tail, pool):
        """tail = 连接词+值……；在汉字串里逐位试切，优先让值落进取值池。"""
        m = CJK_RUN.match(tail)
        if not m:
            return None
        run, rest = m.group(1), m.group(2)
        cands = []
        for k in range(1, len(run) + 1):
            conn = run[:k]
            val = _value((run[k:] + " " + rest).strip()) if k < len(run) else _value(rest)
            if val:
                cands.append((val in pool, k == len(run), conn, val))
        if not cands:
            return None
        cands.sort(key=lambda x: (not x[0], not x[1], -len(x[2])))
        return cands[0]

    def _induce(self, R, segs):
        vals = collections.defaultdict(set)
        for e in R.mem._events.values():
            if e.value is not None:
                vals[e.facet].add(e.value)
            if e.alternative is not None:
                vals[e.facet].add(e.alternative)
        known_verbs = {v for vs in self.verbs.values() for v in vs} | {v for vs in self.implicit.values() for v in vs}
        ents = sorted(R.entities, key=len, reverse=True)
        slots_of = collections.defaultdict(set)
        for (s, a) in R.mem._by_slot:
            slots_of[s].add(a)
        sup = collections.defaultdict(lambda: [set(), 0, None])     # (类型, 连接词) → [槽集, 取值命中, 隐含属性]
        for seq, _sid, text in segs:
            if seq > self.learn_until:
                continue
            for sent in SPLIT.split(text):
                sent = sent.strip()
                if not sent or any(r in sent for r in RETRO) or any(v in sent for v in known_verbs):
                    continue
                for s in ents:
                    m = re.search(r"(?:^|[，；：])\s*" + re.escape(s) + r"\s*", sent)
                    if not m:
                        continue
                    tail = sent[m.end():]
                    if tail.startswith("的"):
                        tail = tail[1:].lstrip()
                        for a in sorted(slots_of.get(s, ()), key=len, reverse=True):
                            if tail.startswith(a):
                                got = self._split(tail[len(a):].lstrip(), vals[a])
                                if got:
                                    hit, _, conn, _v = got
                                    x = sup[("set", conn)]; x[0].add((s, a)); x[1] += hit
                                break
                    else:
                        for fac in self.implicit:
                            got = self._split(tail, vals[fac])
                            if got and got[0]:
                                hit, _, conn, _v = got
                                x = sup[("imp", conn)]; x[0].add((s, fac)); x[1] += hit; x[2] = fac
                    break
        new = []
        P = self.p
        for (kind, conn), (slots, hits, fac) in sorted(sup.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            if len(slots) >= P["min_slots"] and (hits >= P["min_hits"] or not P["value_check"]) and conn not in known_verbs:
                new.append((conn, kind if kind == "set" else f"imp:{fac}", len(slots), hits))
        return new

    def ingest(self, segments):
        segs = sorted(segments, key=lambda x: (x[0], x[1]))
        self.R = self._build(segs)
        if not self.learn:
            return self
        for _ in range(self.p["max_rounds"]):
            new = self._induce(self.R, segs)
            if not new:
                break
            for conn, kind, ns, nh in new:
                self.learned.append((conn, kind, ns, nh))
                self._add(conn, kind)
            self.R = self._build(segs)               # 巩固：整库重放
        return self

    def answer(self, q):
        return self.R.answer(q)
