# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""联想守卫：assoc.py（零模型、零网络、确定性）。

判据面：
  P1 零词面重合合成集（seed 13）：两线索题 r@1 ≥ .90
  P2 反面对照 BM25：两线索题 r@10 ≤ .05（证明题面确实无词面捷径）
  P3 两跳必需：只看 0 跳（lam=0）时，金标一条都不进分数表
  P4 汇流：金标排在它的全部单线索诱饵之前的题 ≥ 95%
  P5 中枢抑制：中枢词（「记录」）入 hubs，低频实体词不入
  P6 打乱边对照：两线索题 r@10 ≤ .05
  P7 确定性：同输入两次 rank 逐位相同
  P8 空题面 / 全生词题面 ⇒ []
  P9 外部边：只经同义表 edges 才能到达的目标，带 edges 进前二（第一是直接命中轮）、不带则不在分数表
  P10 分词：功能字切开，「的」不是词，「搭档」是词

运行：
  python -X utf8 test_assoc.py              # 正向
  python -X utf8 test_assoc.py --mutate     # 定点变异：每条恰好点红其目标判据
退出码：0 全绿；1 失败 / 变异未恰好点红；2 锚点不唯一。
"""
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


def r_at(rank_fn, mems, qs, k, typ="two_cue"):
    xs = [x for x in qs if x["type"] == typ]
    return sum(x["gold"] in rank_fn(x["q"])[:k] for x in xs) / len(xs)


def run():
    from assoc import Assoc, tokens
    import synth
    from bench_assoc import BM25
    mems, qs = synth.build(seed=13)
    A = Assoc(mems)
    v = r_at(A.rank, mems, qs, 1)
    check("P1 两线索题 r@1 ≥ .90", v >= .90, f"r@1={v:.3f}")
    v = r_at(BM25(mems).rank, mems, qs, 10)
    check("P2 BM25 两线索题 r@10 ≤ .05", v <= .05, f"r@10={v:.3f}")
    A0 = Assoc(mems, lam=0)
    leak = sum(x["gold"] in A0.scores(x["q"]) for x in qs)
    check("P3 lam=0 时金标不进分数表", leak == 0, f"泄漏 {leak}")
    # P4：单线索诱饵 = 与金标共享 B 或 Y 的记忆（同场景内），金标须排在它们全部之前
    ok = tot = 0
    for x in qs:
        if x["type"] != "two_cue":
            continue
        g = tokens(mems[x["gold"]])
        r = A.rank(x["q"]); pos = {m: i for i, m in enumerate(r)}
        dec = [m for m in r[:50] if m != x["gold"] and len(tokens(mems[m]) & g - A.hubs) >= 1
               and m in pos and not (tokens(mems[m]) & tokens(x["q"]))]
        tot += 1; ok += all(pos.get(x["gold"], 10 ** 9) < pos[m] for m in dec)
    check("P4 金标排在全部单线索诱饵之前 ≥ 95%", ok / tot >= .95, f"{ok}/{tot}")
    check("P5 中枢词入 hubs、实体词不入", "记录" in A.hubs and not (tokens(mems[qs[0]["gold"]]) - A.hubs <= set()),
          f"hubs样例 {sorted(A.hubs)[:8]}")
    v = r_at(Assoc(synth.shuffled(mems)).rank, mems, qs, 10)
    check("P6 打乱边 r@10 ≤ .05", v <= .05, f"r@10={v:.3f}")
    check("P7 确定性", all(Assoc(mems).rank(x["q"]) == A.rank(x["q"]) for x in qs[:10]))
    check("P8 空题面 / 全生词 ⇒ []", A.rank("") == [] and A.rank("zzqx 嚚嚚") == [])
    small = ["小葵最爱吃榴莲", "阿福在杭州开店", "老周喜欢钓鱼", "今天天气不错"] + [f"杂记{i}号 内容{i}" for i in range(20)]
    with_e = Assoc(small, edges=[("阿福", "老周", 1.0)], hub=.5).rank("阿福 爱好")
    without = Assoc(small, hub=.5).scores("阿福 爱好")
    check("P9 外部边可达：带边进前二、不带不在表", 2 in with_e[:2] and 2 not in without, f"{with_e[:3]}")
    t = tokens("小葵的搭档是老周")
    check("P10 分词：功能字切开", "的" not in t and "搭档" in t and "葵的" not in t, f"{sorted(t)}")


#: (名, 锚点, 替换, 期望点红集合)
MUTATIONS = [
    ("M1 关中枢抑制", 'len(ds) > P["hub"] * n}', "len(ds) > 10 ** 9}", None),
    ("M2 关两跳", 's[m] += P["lam"] * a * self.idf[t]', "s[m] += 0 * a", None),
    ("M3 关汇流", "(hit[m] / len(cues)) ** g", "(hit[m] / len(cues)) ** 0", None),
    ("M4 丢外部边", "bridge[t] += ic * w * self.idf[t]", "pass", None),
    ("M5 分词不切功能字", "if ch in _FUNC:", "if False:", None),
]
WANT = {
    # 中枢词当桥会把激活摊给大批诱饵，P1 同红属语义必然
    "M1 关中枢抑制": {"P5 中枢词入 hubs、实体词不入", "P1 两线索题 r@1 ≥ .90"},
    "M2 关两跳": {"P1 两线索题 r@1 ≥ .90", "P4 金标排在全部单线索诱饵之前 ≥ 95%"},
    # 去汇流后金标仍多半压过单线索诱饵（两路分数相加），但让位给桥记忆，r@1 掉
    "M3 关汇流": {"P1 两线索题 r@1 ≥ .90"},
    "M4 丢外部边": {"P9 外部边可达：带边进前二、不带不在表"},
    # 分词是全部判据的底座：不切功能字 ⇒ 「葵的」「是老」之类跨词二元组进索引、中枢词识别和外部边映射一起失效
    "M5 分词不切功能字": {"P10 分词：功能字切开", "P1 两线索题 r@1 ≥ .90", "P5 中枢词入 hubs、实体词不入", "P9 外部边可达：带边进前二、不带不在表"},
}


def mutate(list_only=False):
    src = open(os.path.join(HERE, "assoc.py"), encoding="utf-8").read()
    if list_only:
        for name, *_ in MUTATIONS:
            print(f"{name}  ⇒ 期望点红：{sorted(WANT[name])}")
        return 0
    bad = 0
    for name, anchor, repl, _ in MUTATIONS:
        if src.count(anchor) != 1:
            print(f"ANCHOR-MISS {name}: 锚点命中 {src.count(anchor)} 次"); return 2
        tmp = tempfile.mkdtemp(prefix="assoc_mut_")
        try:
            for f in ("synth.py", "bench_assoc.py", "test_assoc.py"):
                shutil.copy(os.path.join(HERE, f), os.path.join(tmp, f))
            open(os.path.join(tmp, "assoc.py"), "w", encoding="utf-8").write(src.replace(anchor, repl))
            p = subprocess.run([sys.executable, "-X", "utf8", "test_assoc.py", "--json-fails"], cwd=tmp,
                               capture_output=True, text=True, encoding="utf-8")
            reds = {ln[len("REDLIST "):] for ln in p.stdout.splitlines() if ln.startswith("REDLIST ")}
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
