# -*- coding: utf-8 -*-
"""矛盾另一侧探针（零 LLM）：HMB 小说 178 块作背景，混写同一事物的矛盾短记载对，查询贴近其中一侧，
看前 10 名是否两侧齐全。另测误登记：同模板不同事物（编号/主体不同）与 HMB 长块之间不应登记矛盾。

  PYTHONPATH=<快照> python conflict_probe.py <tag>     → out/conflict_<tag>.json
口径：
  both@10      两侧都在 recall(q, 10) 里的对数 / 总对数（「另一侧存活」）
  new_first    新值（后写入、含变更词时）排在旧值前面的比例（取代降权的作用）
  fp_edges     误登记：模板干扰组与 HMB 长块写入后产生的自动矛盾边数
  write_ms     每条写入耗时（全部写入均摊；HMB 长块与短事实分列）
  query_ms     查询中位
"""
import json, os, random, statistics, sys, tempfile, time
sys.path.insert(0, "/workspace/work/ls/rewrite/evalsuite_hmb")
import hmb_lib as H
from lingshu_ng.compat import SpacetimeMemoryEngine

HERE = os.path.dirname(os.path.abspath(__file__))
ENT = ["巨子塔", "风神像", "蜂巢东区", "共识委员会", "指南终端", "摘星崖哨站", "风龙废墟营地", "神经认证中心", "旧时代档案馆", "骑士团仓库",
       "西风教堂", "蒙德城门", "无风之地观测站", "蜂巢医院", "贡献点兑换处"]
ATTR = ["开放时间", "负责人", "维护周期", "容纳人数", "联络频道", "安全等级", "所在楼层", "供电方式"]
CN = "一二三四五六七八九十"


def pairs(seed=0):
    """(旧, 新, 查询, 类别)。查询照旧侧措辞（「另一侧」= 新侧）或照新侧措辞，交替。"""
    rnd = random.Random(seed)
    out = [
        ("巨子塔的开放时间是每天上午九点到十一点", "巨子塔的开放时间改为每天下午三点到五点", "巨子塔的开放时间是什么时候", "time"),
        ("陈默当前的公民权限等级是一级", "陈默当前的公民权限等级已经提升为三级", "陈默当前的公民权限等级是几级", "state"),
        ("新生分配的住处位于蜂巢东区七号楼", "新生分配的住处已经调整到蜂巢西区十二号楼", "新生分配的住处在哪里", "state"),
        ("指南规定每日贡献点的上限是一百点", "指南规定每日贡献点的上限调整为三百点", "每日贡献点的上限是多少", "number"),
        ("风神的联络频道是蓝色频段", "风神的联络频道更换为红色频段", "风神的联络频道是什么频段", "state"),
        ("下一次共识投票定在本月十五日举行", "下一次共识投票推迟到下月二日举行", "下一次共识投票在哪天举行", "time"),
    ]
    used = set()
    while len(out) < 40:
        e, a = rnd.choice(ENT), rnd.choice(ATTR)
        if (e, a) in used:
            continue
        used.add((e, a))
        k = rnd.randrange(4)
        if k == 0:     # 否定
            out.append((f"{e}的{a}由共识委员会统一管理", f"{e}的{a}不由共识委员会统一管理", f"{e}的{a}由谁管理", "negation"))
        elif k == 1:   # 数值
            x, y = rnd.sample(range(2, 99), 2)
            out.append((f"{e}的{a}记录为{x}项", f"{e}的{a}记录为{y}项", f"{e}的{a}记录为多少项", "number"))
        elif k == 2:   # 时间
            x, y = rnd.sample(range(1, 11), 2)
            out.append((f"{e}的{a}在{CN[x - 1]}月完成核定", f"{e}的{a}在{CN[y - 1]}月完成核定", f"{e}的{a}在几月核定", "time"))
        else:          # 状态变更
            out.append((f"{e}的{a}目前处于试行阶段", f"{e}的{a}已经停止试行", f"{e}的{a}处于什么阶段", "state"))
    return out


def crowd(P, per=12, seed=0):
    """同一事物的非矛盾记载（共享主体与属性词，把前 10 名挤满）：每对 per 条。"""
    rnd = random.Random(seed + 3)
    W = ["很满意", "希望改进", "没有意见", "提出了建议", "表示理解", "写了长评", "画了示意图", "拍了照片"]
    out = []
    for old, _, q, _ in P:
        subj = q.split("是")[0].split("在")[0].split("由")[0].split("记录")[0].split("处于")[0]
        for j in range(per):
            out.append(f"关于{subj}，访客甲{j}{rnd.choice(W)}，并留言说{subj}值得关注")
    return out


def distractors(seed=0):
    """同模板、不同事物：编号或主体不同（不应登记矛盾）。"""
    rnd = random.Random(seed + 7)
    out = []
    for i in range(30):
        out.append(f"骑士团仓库第{i + 1}号柜存放了{rnd.choice(['零件', '药剂', '卷轴', '弓箭'])}")
        out.append(f"巡逻记录{4000 + i * 13}：{rnd.choice(ENT)}今日巡逻正常")
    for e in ENT:
        out.append(f"{e}的清洁工作由志愿者负责")
    return out


def main(tag):
    db = os.path.join(tempfile.mkdtemp(prefix="cprobe_"), "m.db")
    e = SpacetimeMemoryEngine(db)
    chunks = H.novel_chunks()
    P = pairs()
    rnd = random.Random(1)
    # 写入序：HMB 块与旧记载交错 → 干扰组 → 新记载（新值总在旧值之后写入）
    t_long, t_short, n_short = 0.0, 0.0, 0
    olds = [p[0] for p in P]
    stream = [("L", c["text"]) for c in chunks]
    for o in olds:
        stream.insert(rnd.randrange(len(stream) + 1), ("S", o))
    stream += [("S", d) for d in distractors()]
    for c_ in crowd(P):
        stream.insert(rnd.randrange(len(stream) + 1), ("S", c_))
    edges_after = {}
    for kind, txt in stream:
        t0 = time.perf_counter()
        e.add_perception(txt)
        dt = time.perf_counter() - t0
        if kind == "L":
            t_long += dt
        else:
            t_short += dt
            n_short += 1
    db_ = e.ng.store.db
    fp = db_.scalar("SELECT COUNT(*) FROM edges WHERE relation_type='opposite'") or 0
    for _, new, _, _ in P:
        t0 = time.perf_counter()
        e.add_perception(new)
        t_short += time.perf_counter() - t0
        n_short += 1
    auto = db_.scalar("SELECT COUNT(*) FROM edges WHERE relation_type='opposite'") or 0
    E = {(x, y) for x, y in db_.all("SELECT a.content, b.content FROM edges e JOIN nodes a ON a.id = e.source_id "
                                    "JOIN nodes b ON b.id = e.target_id WHERE e.relation_type='opposite'")}
    both, newfirst, qms, per = 0, 0, [], []
    for i, (old, new, q, k) in enumerate(P):
        t0 = time.perf_counter()
        hits = [n.content for n, _ in e.recall(q, limit=10)]
        qms.append(1000 * (time.perf_counter() - t0))
        io, inew = (hits.index(old) if old in hits else None), (hits.index(new) if new in hits else None)
        ok = io is not None and inew is not None
        both += ok
        newfirst += inew is not None and (io is None or inew < io)
        per.append({"kind": k, "old_rank": io, "new_rank": inew, "edge": (new, old) in E or (old, new) in E})
    res = {"tag": tag, "pairs": len(P), "both@10": both, "new_first": newfirst, "fp_edges_before_new": fp,
           "opposite_edges_total": auto, "pairs_registered": sum(1 for x in per if x["edge"]), "write_ms_long": round(1000 * t_long / len(chunks), 3),
           "write_ms_short": round(1000 * t_short / max(1, n_short), 3), "query_ms_median": round(statistics.median(qms), 3),
           "by_kind": {k: f"{sum(1 for x in per if x['kind'] == k and x['old_rank'] is not None and x['new_rank'] is not None)}/"
                          f"{sum(1 for x in per if x['kind'] == k)}" for k in ("negation", "number", "time", "state")},
           "per": per}
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    json.dump(res, open(os.path.join(HERE, "out", f"conflict_{tag}.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "per"}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
