# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""RA-AGM_zh + 逻辑链条守卫（零模型、确定性）。
  Z1 英文问句：ZhMemory 的打分与排序与 Lex+RA-AGM 逐位相同
  Z2 qterms 去掉「什么」这类两字皆虚的二元组，保留实词二元组；全是虚字时原样保留
  Z3 中文问句确实走了去虚字（打分与 Lex+RA-AGM 不同）
  Z4 中文问句不做 RM3（打分 = 关 RM3 的打分），英文问句照做
  Z5 拉丁术语 + 短中文疑问也算中文问句（dsh-bounty#493）；只夹一个汉字的英文句不算
  C1 认不出主体/属性的问句：ZhChain(chain=True) 与 chain=False 排序逐位相同
  C2 现值问：排头是最新一版所在段（检索单路排不到第一）
  C3 变更问：排头是整条链各版所在段，按序号
运行：python -X utf8 test_zh.py [--mutate]"""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import chain  # noqa: E402
import zh  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILS.append(name)


EN = ["user: I adopted a beagle named Max last spring.", "assistant: Congratulations, lovely companion!",
      "user: I started pottery classes downtown.", "assistant: Pottery is relaxing.", "user: My sister visits in June."]
SEGS = [(1, "d#1", "第 1 次提交。甲服务 的依赖名首次确立为 redis。值班同学复现了问题。"),
        (2, "d#2", "第 2 次提交。甲服务 的依赖名调整为 lmdb，起因是容量评估。依赖名的说明文档也更新了，依赖名依赖名。"),
        (3, "d#3", "第 3 次提交。甲服务 的依赖名调整为 sled，起因是接口兼容。"),
        (4, "d#4", "第 4 次提交。乙模块 的有效期秒数首次确立为 600。甲服务 的依赖名 讨论 依赖名 依赖名 当前 值。")]


def run():
    import lex as L, role
    a, b = zh.ZhMemory(rm3=True), role.attach(L.LexMemory(delta=1.0, stem=True, rm3=True))
    for t in EN:
        r, x = t.split(": ", 1)
        a.add_turn(r, x); b.add_turn(r, x)
    q = "What is my beagle called?"
    sa, sb = a.bm25(q), b.bm25(q)
    check("Z1 英文打分与排序逐位相同（rm3=True 复现旧路径）", sa == sb and a.rank_agm(sa) == b.rank_agm(sb))
    c, d = zh.ZhMemory(), role.attach(L.LexMemory(delta=1.0, stem=True, rm3=False))
    for t in EN:
        r, x = t.split(": ", 1)
        c.add_turn(r, x); d.add_turn(r, x)
    check("Z6 默认英文问句不做 RM3", c.bm25(q) == d.bm25(q) and c.bm25(q) != sa)
    check("Z2 去掉「什么」保留实词", zh.qterms(["陈默", "什么", "么时"]) == ["陈默", "么时"], str(zh.qterms(["陈默", "什么", "么时"])))
    check("Z2 全是虚字时原样保留", zh.qterms(["什么", "哪些"]) == ["什么", "哪些"])
    a2, b2 = zh.ZhMemory(rm3=True), role.attach(L.LexMemory(delta=1.0, stem=True, rm3=True))
    for t in ["陈默走进巨子塔，什么也没看见。", "什么时候开饭？什么什么。", "巨子塔是系统核心指令的备份点。"]:
        a2.add_turn("user", t); b2.add_turn("user", t)
    qz = "巨子塔里有什么？"
    c2 = L.LexMemory(delta=1.0, stem=True, rm3=False)
    for t in ["陈默走进巨子塔，什么也没看见。", "什么时候开饭？什么什么。", "巨子塔是系统核心指令的备份点。"]:
        c2.add_turn("user", t)
    check("Z3 中文问句走去虚字", a2.bm25(qz) != c2.c_sdm.score(c2._toks(qz)))
    check("Z4 中文问句不做 RM3", a2.bm25(qz) == c2.c_sdm.score(zh.qterms(c2._toks(qz))))
    check("Z4 闸门只认中文", zh.is_zh(qz) and not zh.is_zh("What is my beagle called?"))
    mixed = ["redis 是什么", "redis是什么", "kafka 如何配置", "为什么用 redis",
             "postgresql 索引怎么用", "kubernetes 的调度策略是什么", "sled 是什么"]
    check("Z5 混排问句判中文", all(zh.is_zh(q) for q in mixed))
    check("Z5 单个汉字的英文句不判中文", not zh.is_zh("What does 是 mean in this sentence?"))
    on, off = chain.ZhChain(True), chain.ZhChain(False)
    for s in SEGS:
        on.add(*s); off.add(*s)
    q0 = "丙系统的部署方式是什么？"
    check("C1 未路由与 RA-AGM_zh 逐位相同", on.rank(q0) == off.rank(q0))
    qp = "截至第 4 次提交，甲服务 的依赖名当前是什么值？"
    check("C2 前提：单路检索第一不是最新版", off.rank(qp)[0] != "d#3", str(off.rank(qp)))
    check("C2 现值问排头是最新版所在段", on.rank(qp)[0] == "d#3", str(on.rank(qp)))
    qc = "甲服务 的依赖名从最初到现在经历过哪些变更？请按序号顺序列出每一次变更前后的值。"
    check("C3 变更问排头是整条链", on.rank(qc)[:3] == ["d#1", "d#2", "d#3"], str(on.rank(qc)))


MUT = {
    "M1 去掉所有两字词项（不看是否虚字）": (lambda: setattr(zh, "qterms", lambda toks: [t for t in toks if len(t) != 2] or toks),
                         {"Z1 英文打分与排序逐位相同（rm3=True 复现旧路径）", "Z2 去掉「什么」保留实词", "Z3 中文问句走去虚字", "Z6 默认英文问句不做 RM3"}),
    "M2 不去虚字": (lambda: setattr(zh, "qterms", lambda toks: toks),
                 {"Z2 去掉「什么」保留实词", "Z3 中文问句走去虚字"}),
    "M4 中文也做 RM3": (lambda: setattr(zh, "is_zh", lambda q: False), {"Z4 中文问句不做 RM3", "Z4 闸门只认中文", "Z5 混排问句判中文"}),
    "M5 英文也关 RM3": (lambda: setattr(zh, "is_zh", lambda q: True), {"Z1 英文打分与排序逐位相同（rm3=True 复现旧路径）", "Z4 闸门只认中文", "Z5 单个汉字的英文句不判中文", "Z6 默认英文问句不做 RM3"}),
    "M6 只按字符占比（#493 回退）": (lambda: setattr(zh, "CJK_RUN", 10 ** 9), {"Z5 混排问句判中文"}),
    "M7 单字即算中文": (lambda: setattr(zh, "CJK_RUN", 1), {"Z5 单个汉字的英文句不判中文"}),
    "M8 英文默认仍开 RM3（回退 2026-10-15 前）": (lambda: setattr(zh.ZhMemory.__init__, "__defaults__", (True, True)), {"Z6 默认英文问句不做 RM3"}),
    "M3 不接逻辑链条": (lambda: setattr(chain.ZhChain, "head", lambda self, q: []),
                   {"C2 现值问排头是最新版所在段", "C3 变更问排头是整条链"}),
}

if __name__ == "__main__":
    if "--mutate" in sys.argv:
        import subprocess
        bad = 0
        for name in MUT:
            p = subprocess.run([sys.executable, "-X", "utf8", __file__, "--one", name], capture_output=True, text=True)
            red = {l[5:].split("  ")[0] for l in p.stdout.splitlines() if l.startswith("FAIL ")}
            ok = red == MUT[name][1]
            bad += not ok
            print(("OK   " if ok else "BAD  ") + name, sorted(red))
        print(f"变异 {len(MUT)} 条，未恰好点红 {bad} 条"); sys.exit(1 if bad else 0)
    if "--one" in sys.argv:
        MUT[sys.argv[sys.argv.index("--one") + 1]][0]()
    run()
    print(f"失败 {len(FAILS)}"); sys.exit(1 if FAILS else 0)
