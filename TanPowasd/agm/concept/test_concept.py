# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""概念链图守卫（PYTHONUTF8=1 python -X utf8 test_concept.py [--mutate]）。
C1 无环：引用环、上位环都被拒绝，且拒绝后图不变；「食物←f(水果) + 水果是一种食物」不误杀
C2 互斥冲突：raise 策略下抛 ConflictError；priority 策略只留第一个并在 trace 记存疑
C3 强化只排序：同一世界问 50 次，classify 结果与公式不变；多上位时走向随强化改变
C4 嵌套求值：苹果/草莓按大小区分，食物经水果嵌套为真
C5 归约路径：苹果 → 水果 → 食物；判定为假时路径为空且不强化
C6 未注册感知量/未知概念引用被拒
定点变异：M1 关掉环检查 → C1 红；M2 关掉冲突检查 → C2 红；M3 强化改阈值 → C3 红"""
import copy, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import concept as K
from concept import P, Eq, Ref, All, Any_

APPLE = {"size": 8, "color": "red", "shape": "round", "edible": True}
BERRY = {"size": 2, "color": "red", "shape": "round", "edible": True}


def c1():
    g = K.demo()
    ok = True
    try:
        g.add_parent("食物", "苹果"); ok = False
    except K.CycleError:
        ok = ok and ("苹果" not in g.concepts["食物"].parents)
    g2 = K.ConceptGraph(); g2.percept("x", lambda w: w["x"])
    g2.add("A", P("x", 0)); g2.add("B", Ref("A"))
    g2.concepts["A"].formula = Ref("B")          # 直接改公式造引用环，验证 _has_cycle 能查出
    ok = ok and g2._has_cycle()
    return ok and "食物" in g.concepts["水果"].parents


def c2():
    g = K.demo()
    bad = dict(APPLE); g.concepts["草莓"].formula = All((Ref("水果"), Eq("color", "red")))
    try:
        g.classify(bad); return False
    except K.ConflictError:
        pass
    g.policy = "priority"
    true, tr = g.classify(bad)
    return "苹果" in true and "草莓" not in true and any("存疑" in t for t in tr)


def c3():
    g = K.demo()
    before = g.classify(APPLE)[0]; f0 = copy.deepcopy({n: c.formula for n, c in g.concepts.items()})
    first = g.ask("苹果", APPLE)["path"][1]
    for _ in range(5):
        g.strength[("苹果", "红色物体")] += 10
    steered = g.ask("苹果", APPLE)["path"][1]
    for _ in range(50):
        g.ask("苹果", APPLE)
    same = g.classify(APPLE)[0] == before and {n: c.formula for n, c in g.concepts.items()} == f0
    return same and first == "水果" and steered == "红色物体" and g.classify(BERRY)[0].count("草莓") == 1


def c4():
    g = K.demo()
    a, b = g.classify(APPLE)[0], g.classify(BERRY)[0]
    return "苹果" in a and "草莓" not in a and "草莓" in b and "苹果" not in b and "食物" in a


def c5():
    g = K.demo()
    r = g.ask("苹果", APPLE)
    n = g.ask("苹果", BERRY)
    return r["path"] == ["苹果", "水果", "食物"] and not n["holds"] and n["path"] == [] and \
        g.strength[("苹果", "水果")] == 1


def c6():
    g = K.ConceptGraph()
    try:
        g.add("X", P("nope", 0)); return False
    except KeyError:
        pass
    g.percept("x", lambda w: w["x"])
    try:
        g.add("X", Ref("Y")); return False
    except KeyError:
        return "X" not in g.concepts


CHECKS = [("C1 无环", c1), ("C2 互斥冲突", c2), ("C3 强化只排序", c3), ("C4 嵌套求值", c4), ("C5 归约路径", c5), ("C6 引用校验", c6)]


def run():
    return {n: bool(f()) for n, f in CHECKS}


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        G = K.ConceptGraph; res = []
        o = G._has_cycle; G._has_cycle = lambda self: False
        res.append(("M1 关环检查", run()["C1 无环"])); G._has_cycle = o
        o = G.classify
        def nocheck(self, world, _o=o):
            m = self.mutex; self.mutex = []
            try:
                return _o(self, world)
            finally:
                self.mutex = m
        G.classify = nocheck
        res.append(("M2 关冲突检查", run()["C2 互斥冲突"])); G.classify = o
        o = G.ask
        def drift(self, name, world, reinforce=True, _o=o):
            r = _o(self, name, world, reinforce)
            c = self.concepts.get("苹果")
            if c and reinforce:
                c.formula = All((Ref("水果"), P("size", 1, 15), Eq("color", "red")))
            return r
        G.ask = drift
        res.append(("M3 强化改阈值", run()["C3 强化只排序"])); G.ask = o
        for n, alive in res:
            print(("SURVIVED " if alive else "killed ") + n)
        sys.exit(1 if any(a for _, a in res) else 0)
    r = run()
    for n, v in r.items():
        print("PASS" if v else "FAIL", n)
    sys.exit(0 if all(r.values()) else 1)
