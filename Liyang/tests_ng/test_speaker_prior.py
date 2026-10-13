# -*- coding: utf-8 -*-
"""gen r10 F4 说话人意图先验：判别器规则、缺省关时逐位不变、开时只在前 sp_n 名内把指向一致的轮前移。"""
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.speaker import doc_speaker, has_role, query_intent


def test_query_intent():
    assert query_intent("Can you remind me of the book you recommended for my sister?") == 1
    assert query_intent("What was your suggestion for the trip?") == 1
    assert query_intent("What was the move-in date for my new apartment?") == -1
    assert query_intent("Could you suggest some furniture stores for my place?") == -1
    assert query_intent("What did Caroline research?") == 0
    assert query_intent("") == 0


def test_doc_speaker():
    assert doc_speaker("assistant: anything") == 1 and doc_speaker("User: x") == -1
    assert has_role("user: hi") and not has_role("Caroline: hi")
    assert doc_speaker("Sure! Here are some ideas you might like:\n1. **Hiking**\n2. Biking. Let me know!") == 1
    assert doc_speaker("I just moved into my new place and my landlord is Bob.") == -1


DOCS = ["user: my landlord is called Bob Smith", "assistant: you should ask your landlord Bob about the lease",
        "user: the lease starts in May", "assistant: great, a May lease start is common for landlord contracts"]


class Fake:
    def __init__(self):
        self.ids, self.txt = [], {}

    def add(self, ids, texts):
        for i, t in zip(ids, texts):
            if i not in self.txt:
                self.ids.append(i)
            self.txt[i] = t

    def search(self, q, k):
        s = sorted(self.ids, key=lambda i: (-(("assistant" in self.txt[i]) + 0.1 * ("landlord" in self.txt[i])), self.txt[i]))
        return [(i, 0.9 - 0.1 * n) for n, i in enumerate(s[:k])]


def _run(**cfg):
    e = MemoryEngine(":memory:")
    e.auto_conflicts = False
    e.set_lexical(sf=1, sf_w=2.0, sf_k=10, sf_n=60, **cfg)
    e.set_embedding_provider(Fake())
    for d in DOCS:
        e.perceive(d)
    out = [n.content for n, _ in e.recall("what is my landlord's name?", 4)["hits"]]
    e.close()
    return out


def test_off_equals_default_and_on_promotes_user_turn():
    base = _run(sp=0.0)
    assert _run(sp=0.0, sp_n=20, sp_win=2) == base
    assert _run() == _run(sp=0.5, sp_n=20, sp_win=2)   # 缺省 = 冻结 F4
    on = _run(sp=2.0, sp_n=4)
    assert on[0].startswith("user:")
    assert sorted(on) == sorted(base)
