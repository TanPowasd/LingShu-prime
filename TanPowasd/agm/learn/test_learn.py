# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""自主学习守卫：learn.py（零模型、零网络、确定性；自带小语料）。
  python -X utf8 test_learn.py            # 正向 L1–L24（L14–L24 是 LLM+ 模式，用离线假 LLM，零网络）
  python -X utf8 test_learn.py --mutate   # 定点变异：每条恰好点红其目标判据
退出码：0 全绿；1 失败 / 变异未恰好点红；2 锚点不唯一。"""
import json
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

    # ---------- LLM+ 模式（假 LLM：按句形规则作答，外加一条编造取值，测逐字校验） ----------
    import re as _re, teacher_llm
    seen = []

    def fake(prompt):
        items = []
        for ln in prompt.splitlines():
            m = _re.match(r"^(\d+)\. (.*)$", ln)
            if not m:
                continue
            i, sent = int(m.group(1)), m.group(2); seen.append(sent)
            for pat, op in ((r"说到(\S+?)，(\S+) 这回定为 (\S+)", "set"), (r"听说(\S+?)，(\S+) 那边记作 (\S+)", "set")):
                g = _re.search(pat, sent)
                if g:
                    items.append(dict(i=i, a=g.group(1), s=g.group(2), op=op, v=g.group(3)))
            if "这回作废了" in sent:
                g = _re.search(r"说到(\S+?)，(\S+) 这回作废了", sent); items.append(dict(i=i, a=g.group(1), s=g.group(2), op="retire", v=""))
            if "风闻" in sent:
                items.append(dict(i=i, s="丁仓", a="容量", op="set", v="999"))
        return json.dumps({"items": items}, ensure_ascii=False)

    S4 = [(1, "d#1", "说到容量，甲仓 这回定为 100。说到容量，乙仓 这回定为 200。"),
          (2, "d#2", "说到容量，甲仓 这回定为 300。说到容量，乙仓 这回作废了。丁仓 的容量首次确立为 5。"),
          (3, "d#3", "说到容量，丙仓 这回定为 400。听说口令，丙仓 那边记作 beta。丁仓 的容量风闻有变。")]
    base = Learner(frames=True).ingest(S4)
    check("L14 默认不调用 LLM：不传 llm 时冷启动句一条也抽不出，且假 LLM 未被调用",
          base.answer(q3)["value"] is None and not seen, f"{base.answer(q3)['value']},{len(seen)}")
    try:
        teacher_llm.default_llm("x"); gate = False
    except RuntimeError as e:
        gate = "LEARN_LLM" in str(e)
    except Exception:
        gate = False
    check("L14b 默认 LLM 函数无 LEARN_LLM=1 拒绝发请求", gate)
    T = teacher_llm.Teacher(llm=fake, batch=2)
    P = Learner(llm=T).ingest(S4)
    check("L15 LLM+ 冷启动：问过之后能答主体挪位句", P.answer(q3)["value"] == "300", f"{P.answer(q3)['value']}")
    check("L16 第一批学成句框后，同句形的后续句不再问 LLM",
          "说到容量，丙仓 这回定为 400" not in seen and ("说到⟨A⟩，⟨S⟩ 这回定为", "set") in P.frames and T.calls == 3,
          f"calls={T.calls},{P.frames}")
    a = P.answer("截至第 9 次，丙仓 的口令当前是什么值？")
    check("L17 只见一个槽、学不成句框的句子：LLM 答案改写成规范句直接入链", a["value"] == "beta", f"{a['value']}")
    a = P.answer("截至第 9 次，丁仓 的容量当前是什么值？")
    check("L18 LLM 编造原句里没有的取值 ⇒ 丢弃", a["value"] == "5", f"{a['value']}")
    cd = tempfile.mkdtemp()
    T1 = teacher_llm.Teacher(llm=fake, cache=cd, batch=2); Learner(llm=T1).ingest(S4)
    T2 = teacher_llm.Teacher(llm=fake, cache=cd, batch=2); Learner(llm=T2).ingest(S4)
    check("L19 磁盘缓存：同一批句子不问第二次", T1.calls > 0 and T2.calls == 0, f"{T1.calls},{T2.calls}")
    n0 = len(seen)
    G2 = Learner(learn=False, lexicon=P.lexicon()).ingest(S4)
    check("L20 LLM+ 学到的句框存盘后冻结可用、零调用", G2.answer(q3)["value"] == "300" and len(seen) == n0,
          f"{G2.answer(q3)['value']}")

    def fake2(prompt):
        items = []
        for ln in prompt.splitlines():
            m = _re.match(r"^(\d+)\. (.*)$", ln)
            if not m:
                continue
            i, sent = int(m.group(1)), m.group(2); seen.append(sent)
            g = _re.search(r"听闻(\S+?)，(\S+) 记作 (\S+?)（暂定）", sent)
            if g:
                items.append(dict(i=i, a=g.group(1), s=g.group(2), op="set", v=g.group(3)))
            g = _re.search(r"因(\S+?)，(\S+) 移到了 (\S+)", sent)
            if g:
                items.append(dict(i=i, s=g.group(2), a="位置", op="set", v=g.group(3), r=g.group(1)))
                items.append(dict(i=i, s=g.group(2), a="天气", op="set", v=g.group(1)))
            g = _re.search(r"(\S+) 自第 \d+ 次起改名为 (\S+)", sent)
            if g:
                items.append(dict(i=i, s=g.group(1), a="名", op="set", v=g.group(2)))
        return json.dumps({"items": items}, ensure_ascii=False)

    S5 = [(1, "e#1", "听闻容量，甲仓 记作 100（暂定）。听闻容量，乙仓 记作 200（暂定）。阿福 移到了 渡口。"),
          (2, "e#2", "因暴雨，阿福 移到了 码头。阿福 自第 3 次起改名为 福哥。"),
          (4, "e#4", "听闻容量，甲仓 记作 300（暂定）。")]
    P5 = Learner(llm=teacher_llm.Teacher(llm=fake2, batch=10)).ingest(S5)
    a = P5.answer("截至第 9 次，甲仓 的容量当前是什么值？")["value"]
    check("L21 句框自检：重抽结果与老师标注不一致（取值切错）⇒ 不晋升，以老师答案入链",
          a == "300" and not any("记作" in t for t, _ in P5.frames), f"{a},{P5.frames}")
    a = P5.answer("阿福 的位置为什么在第 2 次被修改？")["value"]
    check("L22 原表抽到但没解释全句（前面有原因）⇒ 仍交 LLM 复核，原因补上", a == "暴雨", f"{a}")
    ents = {e.entity for e in P5.R.mem._events.values()}
    check("L24 句中没写出、记忆里也没有的属性名（LLM 臆造）⇒ 丢弃", "天气" not in P5.R.facets, f"{P5.R.facets}")
    check("L23 改名句不交 LLM、不改写，别名照常登记", "福哥" in ents and "阿福" not in ents and "名" not in P5.R.facets, f"{ents}")


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
    ("M10 关逐字校验", 'if op != "retire" and (not v or v not in sent):', 'if op != "retire" and not v:', "teacher_llm.py"),
    ("M11 问完不学句框", 'self._add(tpl, "frame:" + o)', "pass"),
    ("M12 关规范句入链", "        if self.facts:", "        if False:"),
    ("M13 关缓存", "if f and f.exists():", "if False:", "teacher_llm.py"),
    ("M15 关句框自检", "if tpl and self._agree(tpl, sent, s, a, op, v, v2, r):", "if tpl:"),
    ("M16 不复核没解释全的句子", 'if pre.strip(" ，；："):', "if False:"),
    ("M17 改名句也交 LLM", "and not RENAME.search(sent)):", "):"),
    ("M18 隐含属性不核对", "if x[3] in x[1] or x[3] in self.R.facets]", "if True]"),
    ("M14 关默认闸门", 'if os.environ.get("LEARN_LLM") != "1":', "if False:", "teacher_llm.py"),
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
    "M7 不载入存盘说法": {"L10 存盘的说法表在新实例上不学也能用", "L20 LLM+ 学到的句框存盘后冻结可用、零调用"},
    "M8 关句框槽数门": {"L12 句框只见于一个槽 ⇒ 不晋升"},
    "M9 不用老师": {"L13 没有种子时自举学不到；v15 老师给种子后学到"},
    "M10 关逐字校验": {"L18 LLM 编造原句里没有的取值 ⇒ 丢弃"},
    "M11 问完不学句框": {"L16 第一批学成句框后，同句形的后续句不再问 LLM"},
    # L21/L22 的正确答案也靠老师答案入链
    "M12 关规范句入链": {"L17 只见一个槽、学不成句框的句子：LLM 答案改写成规范句直接入链",
                       "L21 句框自检：重抽结果与老师标注不一致（取值切错）⇒ 不晋升，以老师答案入链",
                       "L22 原表抽到但没解释全句（前面有原因）⇒ 仍交 LLM 复核，原因补上"},
    # 臆造的「天气=暴雨」进链后，「暴雨」被当成天气而非原因，L22 一起红
    "M18 隐含属性不核对": {"L24 句中没写出、记忆里也没有的属性名（LLM 臆造）⇒ 丢弃",
                         "L22 原表抽到但没解释全句（前面有原因）⇒ 仍交 LLM 复核，原因补上"},
    "M13 关缓存": {"L19 磁盘缓存：同一批句子不问第二次"},
    "M15 关句框自检": {"L21 句框自检：重抽结果与老师标注不一致（取值切错）⇒ 不晋升，以老师答案入链"},
    "M16 不复核没解释全的句子": {"L22 原表抽到但没解释全句（前面有原因）⇒ 仍交 LLM 复核，原因补上"},
    "M17 改名句也交 LLM": {"L23 改名句不交 LLM、不改写，别名照常登记"},
    "M14 关默认闸门": {"L14b 默认 LLM 函数无 LEARN_LLM=1 拒绝发请求"},
}


def mutate(list_only=False):
    srcs = {f: open(os.path.join(HERE, f), encoding="utf-8").read() for f in ("learn.py", "teacher_llm.py")}
    if list_only:
        for n, *_ in MUTATIONS:
            print(n, sorted(WANT[n]))
        return 0
    bad = 0
    for name, anchor, repl, *fn in MUTATIONS:
        fn = fn[0] if fn else "learn.py"; src = srcs[fn]
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
            for f, t in srcs.items():
                open(os.path.join(d, f), "w", encoding="utf-8").write(t)
            os.environ["LEARN_LIYANG_ROOT"] = os.path.join(HERE, "..", "..", "..", "Liyang")
            open(os.path.join(d, fn), "w", encoding="utf-8").write(src.replace(anchor, repl))
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
