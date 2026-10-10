"""内置两臂：NullPlugin（底子分）与 BM25Plugin（朴素参照臂）。"""
from __future__ import annotations
import math, re, time
from collections import Counter

from .adapter import InstallResult, Plugin


class NullPlugin(Plugin):
    """不接任何插件：recall 恒返回空 → 生成器只看到题面（断点前·我说），即考卷契约的无记忆条件。"""
    name = "null"
    version = "1.0"
    kind = "python"

    def install(self, rec):
        rec.event("plugin.install", plugin=self.name, note="无安装动作")
        return InstallResult(ok=True, steps=0, errors=[])

    def ingest(self, sessions, rec):
        rec.event("plugin.ingest", plugin=self.name, sessions=len(sessions), note="丢弃（无记忆）")

    def recall(self, query, k, rec):
        return []

    def uninstall(self, rec):
        return {"residue_paths": []}


_TOK = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")


def tokens(s: str) -> list[str]:
    """中文字二元组 + 英数词（小写）。"""
    out, run = [], []
    for m in _TOK.finditer(s):
        t = m.group(0)
        if len(t) == 1 and "\u4e00" <= t <= "\u9fff":
            run.append(t)
        else:
            if len(run) >= 2:
                out += [run[i] + run[i + 1] for i in range(len(run) - 1)]
            elif run:
                out.append(run[0])
            run = []
            out.append(t.lower())
    if len(run) >= 2:
        out += [run[i] + run[i + 1] for i in range(len(run) - 1)]
    elif run:
        out.append(run[0])
    return out


class BM25Plugin(Plugin):
    """朴素 BM25：按轮次聚块（累计≥6,000 字符即成块，轮边界切分，行对齐），无筛选原文检索。
    参数固定：k1=1.5, b=0.75。块 source = '<文件>#L<s>-L<e>'，text 与语料逐行对齐。"""
    name = "bm25"
    version = "1.0"
    kind = "python"
    BLOCK_CHARS = 6000   # 16 份语料 → 1,595 块，对齐初测 v1.0 的 1,611 块量级
    K1, B = 1.5, 0.75

    def __init__(self):
        self.blocks = []

    def install(self, rec):
        rec.event("plugin.install", plugin=self.name, note="纯标准库，无安装动作")
        return InstallResult(ok=True, steps=0, errors=[])

    def ingest(self, sessions, rec):
        t0 = time.monotonic()
        self.blocks = []
        for s in sessions:
            cur = []
            size = 0
            for tr in s["turns"]:
                cur.append(tr); size += len(tr["text"]) + 1
                if size >= self.BLOCK_CHARS:
                    self._flush(s["session_id"], cur); cur, size = [], 0
            if cur:
                self._flush(s["session_id"], cur)
        self.N = len(self.blocks)
        self.avgdl = sum(b["dl"] for b in self.blocks) / max(1, self.N)
        rec.event("plugin.ingest", plugin=self.name, sessions=len(sessions),
                  turns=sum(len(s["turns"]) for s in sessions), blocks=self.N,
                  dur_s=round(time.monotonic() - t0, 3))

    def _flush(self, sid, turns):
        text = "\n".join(t["text"] for t in turns)
        self.blocks.append({"file": sid, "start": turns[0]["start_line"], "end": turns[-1]["end_line"],
                            "text": text, "low": text.lower(), "dl": len(tokens(text))})

    def recall(self, query, k, rec):
        q = Counter(tokens(query))
        if not q or not self.blocks:
            return []
        terms = list(q)
        tf = [[b["low"].count(t) for t in terms] for b in self.blocks]   # 子串计数（中文二元组/小写英数词）
        df = [sum(1 for row in tf if row[j] > 0) for j in range(len(terms))]
        scores = []
        for i, b in enumerate(self.blocks):
            s = 0.0
            for j, t in enumerate(terms):
                f = tf[i][j]
                if not f:
                    continue
                idf = math.log(1 + (self.N - df[j] + 0.5) / (df[j] + 0.5))
                s += idf * f * (self.K1 + 1) / (f + self.K1 * (1 - self.B + self.B * b["dl"] / self.avgdl))
            scores.append((s, i))
        scores.sort(key=lambda x: (-x[0], x[1]))
        out = []
        for s, i in scores[:k]:
            b = self.blocks[i]
            out.append({"text": b["text"], "source": f"{b['file']}#L{b['start']}-L{b['end']}", "score": round(s, 4)})
        return out

    def uninstall(self, rec):
        self.blocks = []
        return {"residue_paths": []}
