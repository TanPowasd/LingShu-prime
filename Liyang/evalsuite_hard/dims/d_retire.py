"""H-RET 子项：退役与矛盾两侧（意图出处：旧项目 forget_advisor「归档=降权、可逆」；hive-memory-bench README
公开的灵枢弱点「退役后检索泄漏旧值 6/6」「聚焦检索丢失矛盾另一侧」）。

retire：情境层写 v1、再写与之矛盾的 v2，把 v2 重要度压低后跑 forget_advisor（系统自带归档）；
        查询同一主题 → 泄漏 = v2 仍在前 10；保留 = v1 在前 10。
contra：知识层写同一主题的两侧记载（A 说法 / 非 A 的另一种说法，词面重叠低），并用旧项目自有的矛盾落账
        原语 register_conflict(a, b) 显式登记二者矛盾；再加 40 条同实体干扰 →
        查询只用一侧的词面，两侧都在前 10 记为覆盖（矛盾已落账却只交付一侧 = 「聚焦检索丢失矛盾另一侧」）。
"""
import random

from data import ATTRS, corpus, value


def run(A, seed, n=30):
    rnd = random.Random(seed * 211 + 5)
    facts = corpus(seed + 400, n * 3, upd_frac=0)
    leak = keep = arch = 0
    for k in range(n):
        f = facts[k]
        m = A.open()
        v1 = f"{f['e']}的{f['a']}是{f['v']}"
        v2 = f"{f['e']}的{f['a']}改成了{value(rnd)}（后经核实作废）"
        m.add(v1, layer="context", importance=0.5)
        i2 = m.add(v2, layer="context", importance=0.5)
        try:
            m.set_importance_delta(i2, -0.45)
            m.forget_advisor()
            g = m.get(i2)
            arch += bool(g is None or "archived" in (g.get("tags") or []))
            hits = [str(nd["content"]) for nd, _ in m.recall(f"{f['e']}的{f['a']}", limit=10)]
        except Exception:
            hits = [v2]
        leak += any(v2 == h for h in hits)
        keep += any(v1 == h for h in hits)
    cover = 0
    for k in range(n):
        f = facts[n + k]
        m = A.open()
        side_a = f"{f['e']}在会议上明确表示支持{f['a']}改革"
        side_b = f"据档案记载，此人后来公开反对上述方案并递交了辞呈（{f['e']}）"
        ia = m.add(side_a, skip_dedup=True)
        ib = m.add(side_b, skip_dedup=True)
        try:
            m.conflict(ia, ib)
        except Exception:
            pass
        for j in range(40):
            g = facts[(n * 2 + j) % len(facts)]
            m.add(f"{f['e']}的{rnd.choice(ATTRS)}记录{j}：{value(rnd)}", skip_dedup=True)
        try:
            ids = [nd["id"] for nd, _ in m.recall(f"{f['e']}支持{f['a']}改革吗", limit=10)]
        except Exception:
            ids = []
        cover += ia in ids and ib in ids
    return {"retire_leak_rate": round(leak / n, 4), "retire_v1_kept": round(keep / n, 4), "archived_applied": round(arch / n, 4),
            "contra_both_sides@10": round(cover / n, 4)}
