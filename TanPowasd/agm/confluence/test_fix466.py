# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""dsh-bounty#466 修复守卫：臂身份进产物、_sys 缓存隔离闭环、截断/空源图与缺题显式报错。零网络、零 key。

判据（任一红 ⇒ 退出码 1）
  G1  首次 gen：写 _identity.json，每题调用一次
  G2  同身份同命令复跑：0 调用、全部 skip、正常结束（复用不误报）
  G3  LLM_SYS=1 的缺省产物目录与未设时不同（out_<臂>_sys）
  G4  显式同一 --tag、LLM_SYS 翻转：拒绝（退出码 2）、0 调用、旧产物字节不变   ← #466 F1 的原始复现
  G5  修复前产物（有答案、无清单）：拒绝（退出码 2）、0 调用
  G6  同身份但上下文变了（语料改动）：拒绝（退出码 2）、0 调用
  G7  judge：即使 LLM_SYS=1 也以 system=False 调用；请求体变了 ⇒ 拒绝（退出码 2）
  G8  chat(system=False) 在 LLM_SYS=1 下发出的 messages 不含 system；system=None 时含（开关真起作用）
  G9  hx 追问缓存目录：LLM_SYS=1 ⇒ cache_h_sys，未设 ⇒ cache_h               ← #466 F2
  G10 extract 源图缓存：LLM_SYS=1 ⇒ cache_sys；LLM_SYS_GRAPH=0 ⇒ cache（显式沿用）
  G11 hive 源图只覆盖 1/3 的块：load_full 抛 PartialGraph                      ← #466 F3
  G12 LoCoMo 源图缓存为空：load_triples 抛 RuntimeError
  G13 hive_qmd.contexts 题面扩展缺题：抛 RuntimeError（不静默退回多维）
  G14 hive_hop.contexts 追问缺题：抛 RuntimeError（不静默退回单跳）
用法：python -X utf8 test_fix466.py [--mutate]
--mutate：子进程里把被测模块源码做一处定点替换（不写工作区），断言恰好点红预期判据。"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
AGM = HERE.parent
PATHS = {"hive_retrieval": AGM / "bench" / "hive_retrieval.py", "hive_official": AGM / "bench" / "hive_official.py",
         "hive_extract": HERE / "hive_extract.py", "hx": HERE / "hx.py", "extract": HERE / "extract.py",
         "bench_dev": HERE / "bench_dev.py", "hive_qmd": HERE / "hive_qmd.py", "hive_hop": HERE / "hive_hop.py"}

# 变异：名字 → (模块, 原串, 替换串, 预期点红判据)
MUTANTS = {
    "M1 hx 追问缓存去掉 _sys": ("hx", 'HERE / ("cache_h" + SYS_SUFFIX) / which', 'HERE / "cache_h" / which', {"G9"}),
    "M2 身份清单不比对": ("hive_official", 'if m.get("identity") != identity:', "if False:", {"G4"}),
    "M3 逐题输入指纹不比对（存在即 skip）": ("hive_official", "if old != fp:", "if False:", {"G6", "G7"}),
    # 无清单旧产物有两层闸（清单构造时 elif have；逐题 reusable 里 old=None≠fp），单拆一层另一层仍拦，故两点同拆
    "M4 无清单旧产物照常 skip（两层闸同拆）": ("hive_official", ["elif have:", "if old != fp:"],
                                     ["elif False:", "if old is not None and old != fp:"], {"G5"}),
    "M5 判官带 system（跟随 LLM_SYS）": ("hive_official", "obj = parse_json(chat(body, A.model, system=False))",
                                    "obj = parse_json(chat(body, A.model))", {"G7"}),
    "M6 缺省产物目录不带 _sys": ("hive_official", "A.tag or (A.arm + SYS_SUFFIX)", "A.tag or A.arm", {"G3"}),
    "M7 截断源图不报错": ("hive_extract", "if cov < 1.0:", "if False:", {"G11"}),
    "M8 空源图不报错": ("bench_dev", "if not m:", "if False:", {"G12"}),
    "M9 题面扩展缺题不报错": ("hive_qmd", "if nh < len(cards):", "if False:", {"G13"}),
    "M10 追问缺题不报错": ("hive_hop", "if nh < len(cards):", "if False:", {"G14"}),
    "M11 extract 源图缓存去掉 _sys": ("extract", 'CACHE = HERE / ("cache" + (SYS_SUFFIX if os.environ.get("LLM_SYS_GRAPH", "1") == "1" else ""))',
                                 'CACHE = HERE / "cache"', {"G10"}),
}


def load_mod(name):
    """按源码加载模块；MUTATE 环境变量指定的变异在内存里替换一次（替换数必须恰为 1）。"""
    if name in sys.modules:
        return sys.modules[name]
    src = PATHS[name].read_text(encoding="utf-8")
    mk = os.environ.get("MUTATE")
    if mk and MUTANTS[mk][0] == name:
        _, a, b, _ = MUTANTS[mk]
        for x, y in (zip(a, b) if isinstance(a, list) else [(a, b)]):
            if src.count(x) != 1:
                print(f"变异未落地：{mk} 原串出现 {src.count(x)} 次", flush=True)
                raise SystemExit(3)
            src = src.replace(x, y)
    m = types.ModuleType(name)
    m.__file__ = str(PATHS[name])
    sys.modules[name] = m
    exec(compile(src, str(PATHS[name]), "exec"), m.__dict__)
    return m


def boot():
    for p in (HERE, AGM / "bench", AGM / "tricue"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    for n in ("hive_retrieval", "hive_official", "hive_extract", "extract", "hx", "bench_dev", "hive_qmd", "hive_hop"):
        load_mod(n)


R = []


def check(name, ok, detail=""):
    R.append((name, bool(ok), detail))


def mini_bench(root):
    (root / "questions").mkdir(parents=True)
    (root / "corpus").mkdir()
    (root / "questions" / "题目_主轮.json").write_text(json.dumps(
        [{"qid": "o001", "question": "甲是谁"}, {"qid": "o002", "question": "乙在哪"}], ensure_ascii=False), encoding="utf-8")
    (root / "questions" / "作答契约.md").write_text("头\n---\n作答：写入指定的输出文件 `sut/out/<qid>.json`（文件内容就是该对象，不要代码块包裹、不要额外说明）\n---\n尾",
                                                encoding="utf-8")
    (root / "corpus" / "语料.md").write_text("甲是掌柜。乙在城东。", encoding="utf-8")


class Stub:
    def __init__(self):
        self.calls = []

    def __call__(self, prompt, model, max_tokens=None, tries=4, system=None):
        self.calls.append(system)
        return json.dumps({"answer": "桩", "sys": None if system is False else os.environ.get("LLM_SYS")})


def run_gen(HO, bench, tag=None, sys_on=False):
    """在进程内以给定 LLM_SYS 态跑 cmd_gen；返回 (退出码, 调用数, 输出)。"""
    HO.SYS_ON = sys_on
    HO.SYS_SUFFIX = "_sys" if sys_on else ""
    st = Stub(); HO.chat = st
    A = types.SimpleNamespace(bench=str(bench), arm="直读", tag=tag, model="M", workers=2, limit=None, dry=False)
    buf, code = io.StringIO(), 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            HO.cmd_gen(A)
        except SystemExit as e:
            code = e.code
    return code, len(st.calls), buf.getvalue()


def snap(d):
    return {f.name: f.read_bytes() for f in sorted(d.glob("o*.json"))}


def guards():
    boot()
    HO = sys.modules["hive_official"]
    real_chat = HO.chat
    with tempfile.TemporaryDirectory() as td:
        bench = pathlib.Path(td) / "bench"; mini_bench(bench)
        c, n, out = run_gen(HO, bench)
        d0 = bench / "sut" / "out_直读"
        check("G1 首次 gen 写清单且每题一次调用", c == 0 and n == 2 and (d0 / "_identity.json").exists(), f"code={c} calls={n}")
        c, n, out = run_gen(HO, bench)
        check("G2 同身份复跑 0 调用全 skip", c == 0 and n == 0 and out.count(" skip") == 2, f"code={c} calls={n}")
        c, n, out = run_gen(HO, bench, sys_on=True)
        d1 = bench / "sut" / "out_直读_sys"
        check("G3 LLM_SYS=1 缺省目录与未设不同", d1.exists() and c == 0 and n == 2, f"code={c} calls={n} dirs={sorted(p.name for p in (bench / 'sut').iterdir())}")
        # G4：显式同 tag，先不带 sys 跑，再带 sys 跑
        c, n, _ = run_gen(HO, bench, tag="T")
        before = snap(bench / "sut" / "out_T")
        c, n, out = run_gen(HO, bench, tag="T", sys_on=True)
        check("G4 同 --tag 翻转 LLM_SYS ⇒ 拒绝、0 调用、产物不变", c == 2 and n == 0 and snap(bench / "sut" / "out_T") == before,
              f"code={c} calls={n}")
        # G5：修复前产物（有答案无清单）
        old = bench / "sut" / "out_OLD"; old.mkdir(parents=True)
        (old / "o001.json").write_text('{"answer": "旧"}', encoding="utf-8"); (old / "o002.json").write_text('{"answer": "旧"}', encoding="utf-8")
        c, n, _ = run_gen(HO, bench, tag="OLD")
        check("G5 无清单旧产物 ⇒ 拒绝、0 调用", c == 2 and n == 0, f"code={c} calls={n}")
        # G6：上下文变了
        (bench / "corpus" / "语料.md").write_text("甲是掌柜。乙在城西。", encoding="utf-8")
        c, n, _ = run_gen(HO, bench)
        check("G6 上下文变了 ⇒ 拒绝、0 调用", c == 2 and n == 0, f"code={c} calls={n}")
        # G7：judge
        req = bench / "semantic" / "req" / "real_X"; req.mkdir(parents=True)
        (req / "o001__o001.md").write_text("判这题", encoding="utf-8")
        HO.SYS_ON, HO.SYS_SUFFIX = True, "_sys"
        st = Stub(); HO.chat = st
        J = types.SimpleNamespace(bench=str(bench), real="real_X", model="M", workers=1)
        buf = io.StringIO(); code = 0
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                HO.cmd_judge(J)
            except SystemExit as e:
                code = e.code
        ok1 = code == 0 and st.calls == [False]
        (req / "o001__o001.md").write_text("判这题（答卷换了）", encoding="utf-8")
        st = Stub(); HO.chat = st; code = 0
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                HO.cmd_judge(J)
            except SystemExit as e:
                code = e.code
        check("G7 判官 system=False 且请求体变了 ⇒ 拒绝", ok1 and code == 2 and st.calls == [], f"first_ok={ok1} code={code} calls={st.calls}")
    # G8：chat() 组包（桩 urlopen）
    sent = []

    class Resp:
        def __init__(self, b): self.b = b
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()

    def fake_open(req, timeout=None):
        sent.append(json.loads(req.data)["messages"]); return Resp(None)
    real_open = HO.urllib.request.urlopen
    HO.urllib.request.urlopen = fake_open
    try:
        HO.SYS_ON = True
        real_chat("p", "M", system=False); real_chat("p", "M")
    finally:
        HO.urllib.request.urlopen = real_open
    check("G8 system=False 不带 system；system=None 在 LLM_SYS=1 下带",
          len(sent) == 2 and [m["role"] for m in sent[0]] == ["user"] and [m["role"] for m in sent[1]] == ["system", "user"], str(sent))
    # G9 / G10：子进程看真实环境变量下的目录
    def probe(env, expr):
        e = {k: v for k, v in os.environ.items() if k not in ("LLM_SYS", "LLM_SYS_GRAPH")}
        e.update(env)
        r = subprocess.run([sys.executable, "-X", "utf8", __file__, "--probe", expr], env=e, capture_output=True, text=True, encoding="utf-8")
        return (r.stdout.strip().splitlines() or [r.stderr[-300:]])[-1]
    a, b = probe({"LLM_SYS": "1"}, "sys.modules['hx'].cache_dir('hive').parent.name"), probe({}, "sys.modules['hx'].cache_dir('hive').parent.name")
    check("G9 hx 追问缓存 _sys 隔离", a == "cache_h_sys" and b == "cache_h", f"sys={a} plain={b}")
    a = probe({"LLM_SYS": "1"}, "sys.modules['extract'].CACHE.name")
    b = probe({"LLM_SYS": "1", "LLM_SYS_GRAPH": "0"}, "sys.modules['extract'].CACHE.name")
    c = probe({}, "sys.modules['extract'].CACHE.name")
    check("G10 extract 源图缓存 _sys 隔离（LLM_SYS_GRAPH=0 显式沿用）", (a, b, c) == ("cache_sys", "cache", "cache"), f"{a},{b},{c}")
    # G11：截断源图
    HX = sys.modules["hive_extract"]
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td); (root / "corpus").mkdir()
        (root / "corpus" / "u01.json").write_text(json.dumps({"chapters": [{"cid": "c1", "text": "甲" * 170 + "。" + "乙" * 170 + "。" + "丙" * 170 + "。"}]},
                                                             ensure_ascii=False), encoding="utf-8")
        cache = root / "cache"; cache.mkdir()
        ids = HX.ids_of(sys.modules["hive_retrieval"].load_chunks(root))
        (cache / "b0000.json").write_text(json.dumps({"ids": ids[:1], "out": {"chunks": {ids[0]: [["甲", "是", "甲"]]}}}, ensure_ascii=False))
        HX.CACHE = cache
        try:
            HX.load_full(root); red = False
        except HX.PartialGraph:
            red = True
        check("G11 截断源图 ⇒ PartialGraph", red and len(ids) == 3, f"chunks={len(ids)}")
    # G12：空 LoCoMo 源图
    BD, X = sys.modules["bench_dev"], sys.modules["extract"]
    with tempfile.TemporaryDirectory() as td:
        X.CACHE = pathlib.Path(td)
        try:
            BD.load_triples({"sid": "conv-x", "ids": ["D1:1", "D1:2"]}); red = False
        except RuntimeError:
            red = True
        check("G12 空源图 ⇒ RuntimeError", red)
    # G13 / G14：缺题门
    HQ, HH, HR = sys.modules["hive_qmd"], sys.modules["hive_hop"], sys.modules["hive_retrieval"]
    cards = [{"qid": "o001", "question": "甲"}, {"qid": "o002", "question": "乙"}]
    chunks = [{"cid": "c1", "i": 0, "text": "甲", "n": "甲"}]

    class G:
        def rank(self, q): return [0]
    HR.load_cards = lambda root: cards
    real_build = HQ.build
    HQ.build = lambda bench, cs: (chunks, G(), 1)
    try:
        HQ.contexts("x", cards); red = False
    except RuntimeError:
        red = True
    check("G13 题面扩展缺题 ⇒ RuntimeError", red)
    HQ.build = real_build
    HH.ranker = lambda bench, cs: (chunks, G(), lambda q: [0])
    HH.hx.load = lambda which: {"o001": {"follow": [], "found": True}}
    HH.hx.cache_dir = lambda which: pathlib.Path("cache_h_x") / which
    try:
        HH.contexts("x", cards); red = False
    except RuntimeError:
        red = True
    check("G14 追问缺题 ⇒ RuntimeError", red)
    return R


def main():
    if "--probe" in sys.argv:                      # 子进程探针：在给定环境变量下加载模块并打印表达式
        boot(); print(eval(sys.argv[sys.argv.index("--probe") + 1]))
        return 0
    if "--mutate" in sys.argv:
        bad = 0
        for mk, (_, _, _, want) in MUTANTS.items():
            e = dict(os.environ, MUTATE=mk)
            r = subprocess.run([sys.executable, "-X", "utf8", __file__], env=e, capture_output=True, text=True, encoding="utf-8")
            red = {ln.split()[1] for ln in r.stdout.splitlines() if ln.startswith("FAIL ")}
            ok = r.returncode == 1 and red == want
            bad += not ok
            print(f"  {'OK  ' if ok else 'BAD '} {mk}: 红 {sorted(red)}（预期 {sorted(want)}，退出码 {r.returncode}）")
        print(f"变异 {len(MUTANTS)} 条，未恰好点红 {bad} 条")
        return 1 if bad else 0
    guards()
    for n, ok, d in R:
        print(("OK   " if ok else "FAIL ") + n + ("" if ok else f"  [{d}]"))
    f = sum(not ok for _, ok, _ in R)
    print(f"通过 {len(R) - f} / 失败 {f}")
    return 1 if f else 0


if __name__ == "__main__":
    raise SystemExit(main())
