# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""NC 守卫（PREREG_nc.md §5）。零外部数据。
  N1 te_scores 排序与 tree.rank 逐位相同（NC 的底分就是 TE 最终分）。
  N2 grp=None ⇒ 三个候选的块排序与 TE 逐位相同（检索集 / PerLTQA 不加任何相邻关系）。
  N3 聚合式手算：同组、d ≤ w、decay^(d−1)、取最大、只在已打分集合内；跨组不传。
  N4 RA：非种子 assistant 块既不接收也不贡献；种子 assistant 照常；ra=False 时照常参与。
  N5 ra=True 而无角色表 ⇒ ValueError（不静默退化）。
  N6 chunk_groups：块继承所在轮组号；长轮多块同组。
--mutate：对 nc.py 源码做定点变异（M1 忽略组、M2 取和代替最大、M3 去 decay、M4 窗口差一、M5 助手可贡献、M6 助手可接收、
          M7 grp=None 不短路、M8 te_scores 丢激活项、M9 吞 ra 无角色错），每个变异须使至少一条指定守卫转红。"""
import os, pathlib, sys, types

HERE = pathlib.Path(__file__).resolve().parent
AGM = HERE.parent
sys.path[:0] = [str(HERE)] + [str(AGM / d) for d in ("lex", "bench", "tricue", "zh", "xbench", "confluence")]
os.environ["LEX_RM3"] = "0"
import bench_cc as BC  # noqa: E402
import tree as TR      # noqa: E402
import lex as LX       # noqa: E402
SRC = (HERE / "nc.py").read_text(encoding="utf-8")

TEXTS = ["user: I adopted a grey cat named Miso last spring.", "assistant: That is lovely! Cats are great companions.",
         "user: She likes sleeping on the windowsill.", "user: My sister Anna visited Paris in May.",
         "assistant: Paris in May sounds wonderful, did Anna see the Louvre?", "user: Yes, and she brought me a scarf.",
         "user: I started learning the violin this year.", "assistant: Violin is hard but rewarding. " + "Practice daily, slowly and carefully.\n" * 60,
         "user: My teacher is called Mr Okafor.", "user: The cat Miso knocked over my violin stand."]
ROLES = [t.split(": ", 1)[0] for t in TEXTS]
SESS = [0, 0, 0, 1, 1, 1, 2, 2, 2, 3]
QS = ["What is the name of my cat?", "Who visited Paris?", "What did Anna bring?", "who teaches violin", "scarf"]


def _mem():
    BC.ARMS = ["role", "tree"]
    m = BC.build(TEXTS, ROLES, SESS)
    g = TR.build(m, m._sess, speakers=m._spk, **TR.ARMS["TE"])
    return m, g


def checks(nc):
    ok = []
    m, g = _mem()
    good1, good2 = True, True
    for q in QS:
        base = LX.LexMemory.bm25(m, q)
        f = nc.te_scores(g, base)
        good1 &= sorted(f, key=lambda i: (-f[i], i)) == TR.rank(g, base)
        for k, c in nc.CANDS.items():
            try:
                good2 &= nc.rank(m, g, base, None, **c) == TR.rank(g, base)
            except Exception:
                good2 = False
    ok.append(("N1 te_scores≡tree.rank", good1))
    ok.append(("N2 grp=None≡TE", good2))
    r = lambda d: {k: round(v, 9) for k, v in d.items()}
    try:
        a = r(nc.aggregate({0: 1.0, 1: 0.5, 2: 0.2, 5: 0.9}, [0, 0, 0, 1, 1, 1], 0.8, 3, 0.6))
        b = r(nc.aggregate({0: 1.0, 3: 0.1}, [0, 0, 0, 0], 0.8, 3, 0.6))
        c3 = r(nc.aggregate({0: 1.0, 4: 0.3}, [0] * 5, 0.8, 3, 0.6))
        n3 = a == {0: 1.4, 1: 1.3, 2: 0.68, 5: 0.9} and b == {0: round(1.0 + 0.8 * 0.36 * 0.1, 9), 3: round(0.1 + 0.8 * 0.36, 9)} \
            and c3 == {0: 1.0, 4: 0.3}
    except Exception as e:
        n3, a = False, repr(e)
    ok.append(("N3 聚合式手算", n3, str(a)))
    roles = ["user", "assistant", "user", "assistant"]
    try:
        x = r(nc.aggregate({1: 0.9, 2: 0.2}, [0, 0, 0, 0], 0.8, 1, 0.6, ra=True, roles=roles, seeds=()))
        y = r(nc.aggregate({1: 0.9, 2: 0.2}, [0, 0, 0, 0], 0.8, 1, 0.6, ra=True, roles=roles, seeds={1}))
        z = r(nc.aggregate({1: 0.9, 2: 0.2}, [0, 0, 0, 0], 0.8, 1, 0.6, ra=False, roles=roles))
        n4 = x == {1: 0.9, 2: 0.2} and y == {1: 1.06, 2: 0.92} and z == {1: 1.06, 2: 0.92}
    except Exception as e:
        n4, x = False, repr(e)
    ok.append(("N4 RA 非种子助手不参与", n4, str(x)))
    try:
        nc.aggregate({0: 1.0, 1: 0.5}, [0, 0], 0.8, 3, 0.6, ra=True, roles=None)
        n5 = False
    except ValueError:
        n5 = True
    except Exception:
        n5 = False
    ok.append(("N5 ra 无角色⇒ValueError", n5))
    cg = nc.chunk_groups(m, SESS)
    n6 = len(cg) == len(m.raw) and all(cg[i] == SESS[m.turn_of[i]] for i in range(len(m.raw))) and len(m.raw) > len(TEXTS) \
        and nc.chunk_groups(m, None) is None
    ok.append(("N6 chunk_groups 块继承轮组号", n6, f"chunks={len(m.raw)} turns={len(TEXTS)}"))
    return ok


def load(src):
    mod = types.ModuleType("nc_mut")
    mod.__file__ = str(HERE / "nc.py")
    exec(compile(src, "nc.py", "exec"), mod.__dict__)
    return mod


MUTS = {"M1 忽略组": ("grp[j] == grp[i] and ", "", "N3"),
        "M2 取和": ("best = max(best, k * f[j])", "best += k * f[j]", "N3"),
        "M3 去decay": ("k = decay ** (d - 1)", "k = 1.0", "N3"),
        "M4 窗口差一": ("range(1, w + 1)", "range(1, w)", "N3"),
        "M5 助手可贡献": (" and not out_(j)", "", "N4"),
        "M6 助手可接收": ("        if out_(i):\n            out[i] = v\n            continue\n", "", "N4"),
        "M7 grp=None不短路": ("if grp is None or beta", "if beta", "N2"),
        "M8 丢激活项": ("f[i] = f.get(i, 0.0) + beta * x", "f[i] = f.get(i, 0.0) + 0 * x", "N1"),
        "M9 吞ra无角色错": ("raise ValueError(", "print(", "N5")}


def main():
    if "--mutate" in sys.argv:
        res = []
        for name, (old, new, tid) in MUTS.items():
            assert SRC.count(old) == 1, (name, SRC.count(old))
            bad = [c[0] for c in checks(load(SRC.replace(old, new))) if not c[1]]
            res.append(f"{name.split()[0]} {'killed' if any(b.startswith(tid + ' ') for b in bad) else 'SURVIVED'}")
        print(" | ".join(res)); sys.exit(0 if all("killed" in x for x in res) else 1)
    r = checks(load(SRC))
    for c in r:
        print("PASS" if c[1] else "FAIL", c[0], *(c[2:] if not c[1] else []))
    bad = [c[0] for c in r if not c[1]]
    print("RED:" + ",".join(bad)); sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
