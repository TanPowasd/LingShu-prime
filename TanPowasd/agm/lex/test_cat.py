# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""cat.py 守卫（PREREG_cat.md）。NLTK_DATA 指向 WordNet。  python -X utf8 test_cat.py [--mutate]"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cat, lex

FILL = ["Alice: I had a long day at the office today and the weather was grey.",
        "Bob: Lunch was a sandwich near the station, nothing special really.",
        "Alice: Traffic downtown was terrible after the meeting ran late.",
        "Bob: My neighbour painted his fence blue over the weekend.",
        "Alice: I need to renew my library card before Friday."] * 3


def mem(extra):
    m = lex.LexMemory(delta=1.0, stem=True, rm3=False)
    for t in extra + FILL:
        m.add_turn("user", t)
    return m


def checks():
    ok = []
    # C1 门控：类别题取到头词；非类别题 None
    ok.append(("C1", cat.head("Which cities has Jon visited?") == "city" and cat.head("What did John do?") is None
               and cat.head("What kind of tricks do pets know?") == "trick" and cat.head("How many pets does he have?") == "pet"))
    # C2 非类别题 ⇒ 原样返回 base 对象（TE 逐位相同）
    m = mem(["Jon: Took a short trip to Rome last week."])
    b = m.bm25("What did Jon do last week?")
    ok.append(("C2", cat.score(m, b, "What did Jon do last week?", ("wn", "fca"), 0.2) is b))
    # C3 WN 实例：问 city，记忆说 Rome ⇒ Rome 块得分提升到第一
    q = "Which city has Jon visited?"
    b = m.bm25(q); s = cat.score(m, b, q, ("wn",), 0.4)
    ok.append(("C3", max(s, key=s.get) == 0 and lex.stem("rome") in cat.expand(m, q, ("wn",))[1]))
    # C4 WN 同义：问 tournament，记忆说 tourney
    m4 = mem(["John: I held a gaming tourney with my buddies last night."])
    _, e, _ = cat.expand(m4, "How many tournaments has John organized?", ("wn",))
    ok.append(("C4", "tourney" in e))
    # C5 FCA：game 与 witcher 共享属性 L:play、R:night ⇒ witcher 为实例
    m5 = mem(["John: I play the game every night.", "John: I play Witcher every night now.",
              "James: you play chess too?", "Bob: we play cards on Sunday night."])
    _, e, why = cat.expand(m5, "What games does John play?", ("fca",))
    ok.append(("C5", "witcher" in e and why["witcher"][0] == "fca"))
    # C6 hub：本记忆 df/N>HUB 的实例词丢弃
    m6 = mem(["Jon: Rome trip."] + ["Jon: Rome is lovely."] * 8)
    _, e, _ = cat.expand(m6, "Which city has Jon visited?", ("wn",))
    ok.append(("C6", "rome" not in e and lex.stem("rome") not in e and len(e) == 0))
    return ok


MUT = {
    "M1 门控失效（一律当类别题）": lambda: setattr(cat, "head", (lambda f: (lambda q: f(q) or "city"))(cat.head)),
    "M2 hub 失效": lambda: setattr(cat, "HUB", 1.01),
    "M3 去掉同义词": lambda: setattr(cat.wn().synsets("tournament", "n")[0].__class__, "lemma_names", lambda self, *a: [self.name().split(".")[0]]),
    "M4 FCA 属性外延上限=1（无共享属性）": lambda: setattr(cat, "ATTR_MAX", 1),
}

if __name__ == "__main__":
    if "--mutate" in sys.argv:
        import importlib, subprocess
        dead = 0
        for k in MUT:
            r = subprocess.run([sys.executable, "-X", "utf8", __file__, "--one", k], capture_output=True, text=True)
            killed = r.returncode != 0
            dead += killed
            print(("杀死 " if killed else "存活 ") + k, r.stdout.strip().splitlines()[-1:] if r.stdout else "")
        print(f"变异 {dead}/{len(MUT)} 被杀"); sys.exit(0 if dead == len(MUT) else 1)
    if "--one" in sys.argv:
        MUT[sys.argv[sys.argv.index("--one") + 1]]()
    res = checks()
    for k, v in res:
        print(k, "通过" if v else "失败")
    print(f"{sum(v for _, v in res)}/{len(res)}")
    sys.exit(0 if all(v for _, v in res) else 1)
