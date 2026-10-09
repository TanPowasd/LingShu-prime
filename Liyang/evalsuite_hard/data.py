"""HARD 榜合成数据（全部 random.Random(seed) 生成，可复跑；seed=0 主榜，seed=1 防过拟合复核）。"""
from __future__ import annotations

import random

SURN = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳"
GIVEN = "伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀霞平刚桂英华玉兰萍红鹏飞宇浩然子轩梓涵欣怡思远博文雨辰嘉宁泽睿安琪晨曦锦程若溪"
ATTRS = ["生日", "住址", "电话", "职业", "爱好", "血型", "车牌", "宠物", "公司", "学校",
         "籍贯", "身高", "体重", "邮箱", "专业", "导师", "座位", "工号", "口头禅", "过敏源",
         "常去餐厅", "最爱电影", "母语", "星座", "银行", "护照号", "门牌", "乐器", "球队", "密码提示"]
VALCH = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥青赤黄白黑金木水火土东南西北春夏秋冬山川湖海松竹梅兰"


def entities(rnd: random.Random, n: int):
    seen, out = set(), []
    while len(out) < n:
        nm = rnd.choice(SURN) + rnd.choice(GIVEN) + rnd.choice(GIVEN)
        if nm in seen:
            continue
        seen.add(nm)
        out.append(nm)
    return out


def value(rnd: random.Random):
    return "".join(rnd.choice(VALCH) for _ in range(3)) + str(rnd.randrange(100, 999))


DOC_T = ["{e}的{a}是{v}", "关于{e}：{a}为{v}", "{e}，{a}：{v}。", "记录显示{e}的{a}={v}"]


UPD_T = ["{e}的{a}已更新为{v}", "更正：{e}的{a}现在是{v}"]


def corpus(seed: int, n: int, per_entity: int = 5, upd_frac: float = 0.05):
    """n 条事实；每个实体约 per_entity 条，属性在实体间大量共享（强干扰）。
    返回 facts=[{e,a,v,text}]（下标即文档号）。"""
    rnd = random.Random(seed * 7919 + n)
    ents = entities(rnd, max(1, n // per_entity))
    facts, used = [], set()
    while len(facts) < n:
        e = rnd.choice(ents)
        a = rnd.choice(ATTRS)
        if (e, a) in used:
            continue
        used.add((e, a))
        v = value(rnd)
        facts.append({"e": e, "a": a, "v": v, "text": rnd.choice(DOC_T).format(e=e, a=a, v=v)})
    # 更正事实（写在全部原始事实之后）：同 (实体, 属性) 的新值；原事实下标记入 old
    for i in rnd.sample(range(n), int(n * upd_frac)):
        f = facts[i]
        v2 = value(rnd)
        facts.append({"e": f["e"], "a": f["a"], "v": v2, "old": i,
                      "text": rnd.choice(UPD_T).format(e=f["e"], a=f["a"], v=v2)})
    return facts


Q_EA = ["{e}的{a}是什么", "请问{e}{a}", "{a}，{e}", "查一下{e}的{a}"]
Q_NOISY = ["我想知道一下{e}这个人的{a}到底是多少呀，麻烦帮我查查", "之前好像听谁提过，{e}那边的{a}是啥来着？",
           "帮忙回忆：有关{e}，特别是{a}方面的信息"]


def queries(seed: int, facts, nq: int = 200):
    """七类查询（相关集为文档下标；upd 为分级相关）：
    ea=实体+属性（唯一相关）；noisy=口语化长句里的实体+属性；rev=按值反查；ent=实体全部事实；
    pair=两实体同属性（2 个相关）；upd=被更正过的事实（新值增益 2、旧值 1）；
    neg=语料里不存在的实体（不计入 IR 分，只记录「误召回」是否带高分——见 d_retrieval）。"""
    rnd = random.Random(seed * 104729 + len(facts))
    by_e, by_ea, by_a = {}, {}, {}
    base = [i for i, f in enumerate(facts) if "old" not in f]
    for i, f in enumerate(facts):
        by_e.setdefault(f["e"], set()).add(i)
        by_ea.setdefault((f["e"], f["a"]), []).append(i)
        if "old" not in f:
            by_a.setdefault(f["a"], []).append(i)
    upd = [i for i, f in enumerate(facts) if "old" in f]
    out = []
    for k in range(nq):
        i = rnd.choice(base)
        f = facts[i]
        t = k % 6
        if t == 0:
            out.append(("ea", rnd.choice(Q_EA).format(e=f["e"], a=f["a"]), set(by_ea[(f["e"], f["a"])])))
        elif t == 1:
            out.append(("noisy", rnd.choice(Q_NOISY).format(e=f["e"], a=f["a"]), set(by_ea[(f["e"], f["a"])])))
        elif t == 2:
            out.append(("rev", f"谁的{f['a']}是{f['v']}", {i}))
        elif t == 3:
            out.append(("ent", f"{f['e']}", set(by_e[f["e"]])))
        elif t == 4:
            cands = [j for j in by_a[f["a"]] if facts[j]["e"] != f["e"]]
            j = rnd.choice(cands) if cands else i
            g = facts[j]
            rel = set(by_ea[(f["e"], f["a"])]) | set(by_ea[(g["e"], g["a"])])
            out.append(("pair", f"比较{f['e']}和{g['e']}的{f['a']}", rel))
        else:
            if upd:
                u = rnd.choice(upd)
                fu = facts[u]
                out.append(("upd", f"{fu['e']}的{fu['a']}现在是什么", {u: 2, fu["old"]: 1}))
    return out
