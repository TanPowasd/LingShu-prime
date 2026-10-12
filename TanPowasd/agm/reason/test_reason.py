# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""推理守卫：reason.py（零模型、零网络、确定性；自带小语料，不依赖 hive）。
  python -X utf8 test_reason.py            # 正向 R1–R14
  python -X utf8 test_reason.py --mutate   # 定点变异：每条恰好点红其目标判据
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
    (1, "d#1", "旧城仓 的容量首次确立为 100。旧城仓 的负责人首次确立为 张三。甲队 的口令首次确立为 alpha。甲队·下属 的口令首次确立为 omega。"),
    (2, "d#2", "旧城仓 自第 2 次起改名为 新城仓。新城仓 的容量调整为 200，起因是扩建完成。阿福 移到了 渡口，起因是避雨。"),
    (3, "d#3", "新城仓 的容量调整为 300，起因是并入东库。新城仓 的负责人出现两种并存的取值：李四 与 王五，尚未裁定，起因是交接未完。"),
    (4, "d#4", "新城仓 的负责人的争议就此裁定为 李四，起因是总部批复。甲队 的口令被撤销，此后不再保留取值，起因是泄露。早先一度，新城仓 的容量调整为 999。"),
    (5, "d#5", "阿福 移到了 码头，起因是找活。甲队·下属 的口令调整为 sigma，起因是例行轮换。"),
]


def run():
    from reason import Reason
    R = Reason(); R.ingest(SEGS)
    a = R.answer("截至第 5 次提交，新城仓 的容量当前是什么值？")
    check("R1 现值取最后一版", (a["value"], a["state"], a["at"]) == ("300", "active", 3.0), f"{a['value']},{a['at']}")
    a = R.answer("在第 2 次提交时，新城仓 的容量是什么值？")
    check("R2 时点只看该序号以前", (a["value"], a["at"]) == ("200", 2.0), f"{a['value']},{a['at']}")
    a = R.answer("截至第 5 次提交，甲队 的口令处于什么状态？")
    check("R3 撤销 ⇒ retired、值为空", (a["state"], a["value"], a["at"]) == ("retired", None, 4.0), f"{a['state']},{a['value']}")
    a3 = R.answer("在第 3 次提交这个时间点，新城仓 的负责人的值和状态分别是什么？")
    a4 = R.answer("截至第 4 次提交，新城仓 的负责人当前是什么值？")
    check("R4 两说并存 ⇒ unresolved，裁定后 active", (a3["state"], a3["value"], a3.get("alternative")) == ("unresolved", "李四", "王五")
          and (a4["state"], a4["value"]) == ("active", "李四"), f"{a3['state']},{a4['state']}")
    a = R.answer("在第 1 次提交时，新城仓 的容量是什么值？")
    check("R5 改名前的事件归到新名下", a["value"] == "100", f"{a['value']}")
    a = R.answer("截至第 5 次提交，甲队·下属 的口令当前是什么值？")
    b = R.answer("在第 3 次提交时，甲队 的口令是什么值？")
    check("R6 下属单元不与本体合并", a["value"] == "sigma" and b["value"] == "alpha", f"{a['value']},{b['value']}")
    a = R.answer("新城仓 的容量从最初到现在经历过哪些变更？")
    check("R7 回顾句不入链", [x["to"] for x in a["chain"]] == ["100", "200", "300"], f"{[x['to'] for x in a['chain']]}")
    a = R.answer("新城仓 的容量为什么在第 3 次提交被修改？")
    check("R8 缘由按事件时点定位", a["value"] == "并入东库", f"{a['value']}")
    a = R.answer("新城仓 的容量从最初到现在经历过哪些变更？")
    check("R9 变更链 from/to", [(x["from"], x["to"]) for x in a["chain"]] == [(None, "100"), ("100", "200"), ("200", "300")])
    a = R.answer("截至第 5 次提交，阿福 的位置当前是什么值？")
    check("R10 隐含属性：移到了 ⇒ 位置", (a["value"], a["at"]) == ("码头", 5.0), f"{a['value']}")
    check("R11 题面最长主体匹配", R.parse("截至第 5 次，甲队·下属 的口令当前是什么值？")[0] == "甲队·下属")
    a = R.answer("截至第 5 次提交，无名氏 的口令当前是什么值？")
    check("R12 生词题面 ⇒ absent 且未解析", a["state"] == "absent" and a["parsed"] is False)
    from reason import VERBS as _V
    V2 = {**_V, "set": _V["set"] + ("成了",)}
    R2 = Reason(verbs=V2, frames=[("⟨S⟩ 的⟨A⟩最早定成了", "set")])
    R2.ingest([(1, "x#1", "丁 的信任对象最早定成了 小满。"), (2, "x#2", "丁 的信任对象成了 无人。")])
    ch = R2.answer("丁 的信任对象从最初到现在经历过哪些变更？")["chain"]
    check("R13 多说法都能匹配取属性最短（短动词不吞长句框）", [c["to"] for c in ch] == ["小满", "无人"], f"{[c['to'] for c in ch]}")
    R3 = Reason(frames=[("说到⟨A⟩，⟨S⟩ 这回定为", "set")])
    R3.ingest([(1, "x#1", "说到容量，甲仓 这回定为 100。")])
    a = R3.answer("截至第 5 次，甲仓 的容量当前是什么值？")
    check("R14 句框（主体挪位）可抽", a["value"] == "100", f"{a['value']}")


MUTATIONS = [
    ("M1 关时间过滤", "at=at if self.time_filter else math.inf", "at=math.inf"),
    ("M2 关别名", 'self.mem.add_alias("entity", old, new)', "pass"),
    ("M3 关回顾句过滤", "if not sent or any(r in sent for r in self.retro):", "if not sent:"),
    ("M5 关隐含属性", "for fac, pat in self._imp:", "for fac, pat in []:"),
    ("M7 关最短属性择优", 'hits = [min(hits, key=lambda h: (len(h[2].group("a")), -len(h[1])))]', "hits = hits[:1]"),
    ("M8 句框不编译", "self._pats += [(op, tpl, frame_regex(tpl)) for tpl, op in frames]", "pass"),
    ("M6 丢缘由", 'reason = r.group("r").strip() if r else None', "reason = None"),
]
WANT = {
    # 时点问与「处于什么状态」都走时间过滤；关掉后 R2/R4(第3次)/R5(第1次)/R6(第3次) 一起看到最新版，属语义必然
    "M1 关时间过滤": {"R2 时点只看该序号以前", "R4 两说并存 ⇒ unresolved，裁定后 active",
                  "R5 改名前的事件归到新名下", "R6 下属单元不与本体合并"},
    # 别名断开：改名前的容量/负责人留在旧名下，新名的链少一版
    "M2 关别名": {"R5 改名前的事件归到新名下", "R7 回顾句不入链", "R9 变更链 from/to"},
    # 回顾句被当成第 4 次的新版本：现值、链长、链尾一起错
    "M3 关回顾句过滤": {"R1 现值取最后一版", "R7 回顾句不入链", "R9 变更链 from/to"},
    "M5 关隐含属性": {"R10 隐含属性：移到了 ⇒ 位置"},
    "M6 丢缘由": {"R8 缘由按事件时点定位"},
    "M7 关最短属性择优": {"R13 多说法都能匹配取属性最短（短动词不吞长句框）"},
    "M8 句框不编译": {"R13 多说法都能匹配取属性最短（短动词不吞长句框）", "R14 句框（主体挪位）可抽"},
}


def mutate(list_only=False):
    src = open(os.path.join(HERE, "reason.py"), encoding="utf-8").read()
    if list_only:
        for n, *_ in MUTATIONS:
            print(n, sorted(WANT[n]))
        return 0
    bad = 0
    chron = os.path.join(HERE, "..", "..", "chronicle", "chronicle.py")
    for name, anchor, repl in MUTATIONS:
        if src.count(anchor) != 1:
            print(f"ANCHOR-MISS {name}: {src.count(anchor)}"); return 2
        tmp = tempfile.mkdtemp(prefix="reason_mut_")
        try:
            d = os.path.join(tmp, "TanPowasd", "agm", "reason"); os.makedirs(d)
            c = os.path.join(tmp, "TanPowasd", "chronicle"); os.makedirs(c)
            shutil.copy(chron, c)
            shutil.copy(os.path.join(HERE, "test_reason.py"), d)
            open(os.path.join(d, "reason.py"), "w", encoding="utf-8").write(src.replace(anchor, repl))
            p = subprocess.run([sys.executable, "-X", "utf8", "test_reason.py", "--json-fails"], cwd=d,
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
