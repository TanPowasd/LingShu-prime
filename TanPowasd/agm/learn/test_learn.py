# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""自主学习守卫：learn.py（零模型、零网络、确定性；自带小语料）。
  python -X utf8 test_learn.py            # 正向 L1–L13
  python -X utf8 test_learn.py --mutate   # 定点变异：每条恰好点红其目标判据
退出码：0 全绿；1 失败 / 变异未恰好点红；2 锚点不唯一。"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
PASS, FAIL, FAILS = 0, 0, []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  OK   {name}")
    else:
        FAIL += 1; FAILS.append(name); print(f"  FAIL {name}  {detail}")


SEGS = [
    (1, "d#1", "甲仓 的容量首次确立为 100。乙仓 的容量首次确立为 200。丙仓 的容量首次确立为 300。阿福 移到了 渡口。阿禄 移到了 码头。"),
    (2, "d#2", "甲仓 的容量被改动成 200。"),
    (3, "d#3", "乙仓 的容量被改动成 300。丙仓 的容量据说要看 下周。丙仓 的容量悄悄成了 100。"),
    (4, "d#4", "甲仓 的容量据说要看 下周。阿福 挪去了 码头。阿禄 挪去了 渡口。"),
    (6, "d#6", "早先一度，甲仓 的容量偷改作 300。早先一度，乙仓 的容量偷改作 100。"),
    (10, "d#10", "甲仓 的容量换算作 300。乙仓 的容量换算作 100。"),
]


def run():
    from learn import Learner
    F = Learner(learn=False).ingest(SEGS)
    L = Learner().ingest(SEGS)
    H = Learner(learn_until=5).ingest(SEGS)
    got = {c: k for c, k, *_ in L.learned}
    q = "截至第 9 次，乙仓 的容量当前是什么值？"
    check("L1 冻结抽不到表外说法、学习后能", F.answer(q)["value"] == "200" and L.answer(q)["value"] == "300",
          f"{F.answer(q)['value']},{L.answer(q)['value']}")
    check("L2 两槽以上、取值在池 ⇒ 晋升", got.get("被改动成") == "set", f"{got}")
    check("L3 只见于一个槽 ⇒ 不晋升", "悄悄成了" not in got, f"{got}")
    check("L4 取值不在池 ⇒ 不晋升（噪声连接词）", "据说要看" not in got, f"{got}")
    a = L.answer("在第 2 次时，甲仓 的容量是什么值？")
    check("L5 巩固重放：晋升前的早期句也补进链", a["value"] == "200" and a["at"] == 2.0, f"{a['value']}")
    hl = {c for c, *_ in H.learned}
    check("L6 前学后测：截止序号之后的说法不学", "换算作" in got and "换算作" not in hl and "被改动成" in hl, f"{hl}")
    a = L.answer("截至第 9 次，阿福 的位置当前是什么值？")
    check("L7 隐含属性说法可学（挪去了 ⇒ 位置）", got.get("挪去了") == "imp:位置" and a["value"] == "码头", f"{got},{a['value']}")
    check("L8 原表能抽全的语料不学任何东西", Learner().ingest(SEGS[:1]).learned == [])
    check("L9 回顾句不作学习种子", "偷改作" not in got, f"{got}")
    import json as _j, tempfile as _t
    p = os.path.join(_t.mkdtemp(), "lex.json"); Learner.save(p, L.lexicon())
    G = Learner(learn=False, lexicon=Learner.load(p)).ingest(SEGS)
    check("L10 存盘的说法表在新实例上不学也能用", G.answer(q)["value"] == "300" and G.learned == [], f"{G.answer(q)['value']}")
    S2 = [(1, "d#1", "甲仓 的容量首次确立为 100。乙仓 的容量首次确立为 200。丙仓 的口令首次确立为 alpha。"),
          (2, "d#2", "甲仓 的容量调整为 300。"),
          (3, "d#3", "说到容量，甲仓 这回定为 200。说到容量，乙仓 这回定为 300。"),
          (4, "d#4", "听说口令，丙仓 那边记作 alpha。")]
    FR = Learner(frames=True).ingest(S2)
    a, f0 = FR.answer(q)["value"], Learner(learn=False).ingest(S2).answer(q)["value"]
    check("L11 句框自举：主体挪位的新句形可学（两槽、取值在池）", a == "300" and f0 == "200"
          and ("说到⟨A⟩，⟨S⟩ 这回定为", "set") in FR.frames, f"{f0},{a},{FR.frames}")
    check("L12 句框只见于一个槽 ⇒ 不晋升", not any("那边记作" in t for t, _ in FR.frames), f"{FR.frames}")
    S3 = [(1, "d#1", "说到容量，甲仓 这回定为 100。说到容量，乙仓 这回定为 200。"), (2, "d#2", "说到容量，甲仓 这回定为 300。")]
    q3 = "截至第 9 次，甲仓 的容量当前是什么值？"
    T0, T1 = Learner(frames=True).ingest(S3), Learner(frames=True, teacher="v15").ingest(S3)
    check("L13 没有种子时自举学不到；v15 老师给种子后学到", T0.answer(q3)["value"] is None and T1.answer(q3)["value"] == "300",
          f"{T0.answer(q3)['value']},{T1.answer(q3)['value']}")


MUTATIONS = [
    ("M1 关巩固重放", "self.R = self._build(segs)               # 巩固：整库重放", "pass"),
    ("M2 关槽数门", 'len(slots) >= P["min_slots"]', "True"),
    ("M3 关取值校验", '(hits >= P["min_hits"] or not P["value_check"])', "True"),
    ("M4 偷看未来", "if seq > self.learn_until:", "if False:"),
    ("M5 关隐含属性学习", "if got and got[0]:", "if False:"),
    ("M7 不载入存盘说法", 'self._add(row["conn"], row["kind"])', "pass"),
    ("M8 关句框槽数门", 'len(slots) >= self.p["min_slots"] and (tpl', "True and (tpl"),
    ("M9 不用老师", 'if self.teacher == "v15":', "if False:"),
    ("M6 回顾句当种子", "if not sent or any(r in sent for r in RETRO) or any(", "if not sent or any("),
]
WANT = {
    # 学到了却不重放：表外句仍在链外，L1/L5/L7/L11/L13 的作答一起错
    "M1 关巩固重放": {"L1 冻结抽不到表外说法、学习后能", "L5 巩固重放：晋升前的早期句也补进链", "L7 隐含属性说法可学（挪去了 ⇒ 位置）",
                     "L11 句框自举：主体挪位的新句形可学（两槽、取值在池）", "L13 没有种子时自举学不到；v15 老师给种子后学到"},
    "M2 关槽数门": {"L3 只见于一个槽 ⇒ 不晋升"},
    "M3 关取值校验": {"L4 取值不在池 ⇒ 不晋升（噪声连接词）"},
    "M4 偷看未来": {"L6 前学后测：截止序号之后的说法不学"},
    "M5 关隐含属性学习": {"L7 隐含属性说法可学（挪去了 ⇒ 位置）"},
    "M6 回顾句当种子": {"L9 回顾句不作学习种子"},
    "M7 不载入存盘说法": {"L10 存盘的说法表在新实例上不学也能用"},
    "M8 关句框槽数门": {"L12 句框只见于一个槽 ⇒ 不晋升"},
    "M9 不用老师": {"L13 没有种子时自举学不到；v15 老师给种子后学到"},
}


def mutate(list_only=False):
    src = open(os.path.join(HERE, "learn.py"), encoding="utf-8").read()
    if list_only:
        for n, *_ in MUTATIONS:
            print(n, sorted(WANT[n]))
        return 0
    bad = 0
    for name, anchor, repl in MUTATIONS:
        if src.count(anchor) != 1:
            print(f"ANCHOR-MISS {name}: {src.count(anchor)}"); return 2
        tmp = tempfile.mkdtemp(prefix="learn_mut_")
        try:
            base = os.path.join(tmp, "TanPowasd")
            d = os.path.join(base, "agm", "learn"); os.makedirs(d)
            shutil.copytree(os.path.join(HERE, "..", "reason"), os.path.join(base, "agm", "reason"),
                            ignore=shutil.ignore_patterns("results", "__pycache__"))
            shutil.copytree(os.path.join(HERE, "..", "..", "chronicle"), os.path.join(base, "chronicle"),
                            ignore=shutil.ignore_patterns("results", "__pycache__"))
            shutil.copy(os.path.join(HERE, "test_learn.py"), d)
            shutil.copy(os.path.join(HERE, "teacher_v15.py"), d)
            os.environ["LEARN_LIYANG_ROOT"] = os.path.join(HERE, "..", "..", "..", "Liyang")
            open(os.path.join(d, "learn.py"), "w", encoding="utf-8").write(src.replace(anchor, repl))
            p = subprocess.run([sys.executable, "-X", "utf8", "test_learn.py", "--json-fails"], cwd=d,
                               capture_output=True, text=True, encoding="utf-8")
            reds = {ln[8:] for ln in p.stdout.splitlines() if ln.startswith("REDLIST ")}
            ok = reds == WANT[name]; bad += not ok
            print(f"  {'OK  ' if ok else 'FAIL'} {name}: 红 {sorted(reds)}" + ("" if ok else f"  期望 {sorted(WANT[name])}"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"变异 {len(MUTATIONS)} 条，未恰好点红 {bad} 条")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        sys.exit(mutate("--list" in sys.argv))
    run()
    if "--json-fails" in sys.argv:
        for f in FAILS:
            print("REDLIST " + f)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
