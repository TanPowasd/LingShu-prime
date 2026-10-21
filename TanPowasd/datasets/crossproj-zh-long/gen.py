# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""crossproj-zh-long v0.1 生成器（vsa/PREREG_long_hold.md §1）：零 LLM、零 key、确定性（固定种子）。
一人（周以宁）× 六个并行项目；事实写进短轮与长文档（用户整篇粘贴的纪要 / 日志，一篇一轮）；程序出题、回填金标 dia_id。
  python3 gen.py            # → release/crossproj_zh_long_hold.json（结构校验见 vsa/long_hold.py --check；冻结哈希见 release/SHA256SUMS.json）
只用标准库。不读任何算法输出。"""
import datetime as dt
import json
import pathlib
import random
import re

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261021
N_SESS = 44
START = dt.date(2026, 3, 3)
SP, AS = "周以宁", "助手"
DOC_ENTRIES = (22, 28)          # 每篇长文档条目数区间。v0.1 首版 (14, 18) 结构校验只得 25 个长单元 < 60，按 PREREG §1 只加大此处（未看任何算法输出）
N_DOCS = 92

PROJ = {
    "P1": ("青岚血氧仪注册上市", "青岚项目周会纪要",
           ["主板", "传感器模组", "外壳模具", "注册检验", "临床评价", "说明书", "包装盒", "固件二版", "电磁兼容测试", "生物相容性测试",
            "锂电池组", "充电底座", "质量体系文件", "首批试产"]),
    "P2": ("新房装修", "装修施工日志",
           ["厨房橱柜", "卫生间防水", "客厅地板", "主卧衣柜", "阳台推拉门", "全屋电路", "中央空调", "入户门锁", "书房吊顶", "热水器",
            "墙面乳胶漆", "开关面板", "瓷砖铺贴", "窗帘轨道"]),
    "P3": ("在职研究生备考", "备考学习日志",
           ["英语阅读", "管理学教材", "逻辑真题", "写作模板", "数学错题本", "复试材料", "推荐信", "模拟考试", "线上辅导课", "单词打卡",
            "政治背诵", "面试小组", "报名材料", "学习小组"]),
    "P4": ("社区读书会", "读书会活动记录",
           ["春季书单", "共读群", "分享嘉宾", "场地租借", "茶歇采购", "海报设计", "签到表", "会员名册", "图书捐赠", "线上直播",
            "亲子共读场", "年度账本", "读书笔记合集", "志愿者排班"]),
    "P5": ("母亲膝关节手术康复", "陪护康复日志",
           ["术前检查", "主刀医生团队", "康复训练", "护工安排", "术后复查", "止痛方案", "助行器", "康复理疗", "医保报销", "营养餐",
            "护膝支具", "居家扶手", "出院手续", "住院押金"]),
    "P6": ("妹妹婚礼筹备", "婚礼筹备会记录",
           ["婚宴酒店", "婚纱摄影", "婚车车队", "伴娘礼服", "喜糖礼盒", "请柬印刷", "司仪人选", "婚礼跟拍", "花艺布置", "宾客名单",
            "蜜月行程", "答谢宴", "婚戒定制", "迎亲游戏"]),
}
ATTRS = [("负责人", "person", "是谁"), ("对接人", "person", "是谁"), ("供应商", "org", "是哪家"), ("合作方", "org", "是哪家"),
         ("预算", "num:万元", "是多少"), ("报价", "num:元", "是多少"), ("数量", "num:件", "是多少"), ("存放地点", "place", "在哪")]
SUR = list("赵钱孙李吴郑冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜戚谢邹喻柏窦章苏潘葛范彭鲁马方俞任袁柳鲍史唐")
GIV = ["思远", "嘉怡", "子涵", "雨辰", "浩然", "若溪", "明轩", "静怡", "一帆", "梓萱", "晨阳", "安琪", "宇航", "书瑶", "俊杰", "可欣",
       "天佑", "梦洁", "志强", "慧敏", "文博", "诗涵", "泽宇", "佳宁", "乐天", "晓彤", "云飞", "婉清", "国栋", "海燕", "立新", "秋实"]
ORG_PRE = ["恒泰", "瑞景", "华辰", "嘉禾", "博远", "鼎盛", "清源", "汇丰", "启明", "星河", "云帆", "锦程", "宏图", "安和", "正阳", "长青",
           "天衡", "九州", "银杏", "明德", "致远", "合众", "新航", "远山", "朗润", "金石", "万象", "和光", "青松", "海纳"]
ORG_SUF = ["科技", "检测中心", "建材行", "工作室", "服务社", "医疗器械公司", "家居馆", "文化传媒", "电子厂", "供应链公司", "设计事务所", "实业"]
AREA = ["工业园区", "姑苏区", "吴中区", "相城区", "高新区", "吴江区", "园区湖东", "园区湖西", "石路", "平江路", "金鸡湖东", "独墅湖"]
BLD = ["三号仓库", "B座档案室", "七楼储物间", "地下车库储藏间", "物业库房", "临时周转仓", "二号样品柜", "东区货架", "前台寄存处", "会议室柜子"]
TASKS = ["提交材料", "完成验收", "交付样品", "确认方案", "签署合同", "完成复核", "付清尾款", "上交报告", "完成整改", "寄出资料", "完成培训", "办完手续"]
EVENTS = {
    "P1": ["去{o}开了{x}评审会", "带团队去{o}做了{x}现场核查", "跟{p}一起去{o}交了{x}的样机"],
    "P2": ["去{o}挑了{x}的样品", "约{p}在新房验了{x}", "跟{p}去{o}定了{x}"],
    "P3": ["在{o}参加了{x}的模考", "跟{p}在{o}讨论了{x}", "去{o}听了{x}讲座"],
    "P4": ["在{o}办了{x}的线下活动", "跟{p}去{o}谈了{x}合作", "请{p}来讲了{x}专题"],
    "P5": ["陪妈妈去{o}做了{x}", "带妈妈去{o}复诊了{x}", "跟{p}一起陪妈妈做了{x}"],
    "P6": ["陪妹妹去{o}看了{x}", "跟{p}去{o}试了{x}", "帮妹妹在{o}订了{x}"],
}
FILL = ["{o}进度正常，{p}继续跟进。", "{p}提到{o}可能有风险，下次再议。", "{o}相关票据已交给{p}整理。", "{o}的方案还在比选，先不定。",
        "{p}反馈{o}这周有点卡，需要协调资源。", "{o}暂时搁置，等{p}的消息。", "{p}建议{o}多做一轮比价。", "{o}的照片已经上传到共享盘。",
        "{o}这块先按原计划走，不做调整。", "{p}说{o}的问题已经解决了一半。", "{o}的沟通记录由{p}补充。", "大家对{o}没有异议。",
        "{o}的细节等{p}出差回来再敲。", "{p}负责把{o}的清单再核一遍。", "{o}出现小插曲，已和{p}沟通过。", "{o}暂不追加开支。",
        "{o}按{p}的意见改了两处措辞。", "{p}觉得{o}可以再简化一些。", "{o}的历史资料都归档了。", "{o}下周由{p}牵头复盘。"]
CHAT = ["今天下雨，地铁特别挤，到公司腿都酸了。", "最近睡得不太好，脑子有点乱，先跟你絮叨几句。", "中午吃了碗苏式汤面，心情好多了。",
        "晚上想去金鸡湖边走走，透透气。", "这周事情扎堆，感觉自己像陀螺。", "猫又把绿萝啃了，真拿它没办法。", "周末想睡个懒觉，不知道能不能实现。",
        "刚跟老同学打了个电话，聊了好久。", "今天的咖啡太苦了，下次换家店。", "办公室空调坏了，热得不行。", "最近在听一档讲历史的播客，挺有意思。",
        "早上跑了三公里，久违的出汗。", "手机屏幕摔裂了，烦。", "想给自己放半天假，不过估计不行。", "楼下新开了家面包店，排队的人好多。"]
ACK = ["好的，{j}这条我记下了。", "收到，已经归到{j}里。", "明白，{j}的信息我帮你存好了，需要时随时问我。", "记好了。{j}最近事情不少，注意休息。",
       "好，{j}这边我更新了。还有别的要补充吗？", "已存档到{j}。", "了解，{j}我会按这个版本记。", "收到，回头整理{j}的时候会用到。"]
CHAT_ACK = ["辛苦了，照顾好自己。", "听起来挺累的，晚上早点休息吧。", "哈哈，生活里的小事也挺有意思。", "抱抱，忙完这阵就好了。",
            "要不要我帮你列个这周的待办？", "嗯嗯，我在听。", "那就先放松一下。"]


def md(d):
    return f"{d.month}月{d.day}日"


def ymd(d):
    return f"{d.year}年{d.month}月{d.day}日"


class World:
    def __init__(self, rng):
        self.rng = rng
        self.used_vals, self.used_oa, self.used_ev, self.used_ot = set(), set(), set(), set()
        self.persons = [s + g for s in SUR for g in GIV if s + g != SP]
        rng.shuffle(self.persons)

    def value(self, kind):
        r = self.rng
        for _ in range(10000):
            if kind == "person":
                v = self.persons.pop()
            elif kind == "org":
                v = r.choice(ORG_PRE) + r.choice(ORG_SUF)
            elif kind == "place":
                v = r.choice(AREA) + r.choice(BLD)
            else:
                unit = kind.split(":")[1]
                n = {"万元": r.randint(3, 400), "元": r.randint(120, 98000), "件": r.randint(6, 3000)}[unit]
                v = f"{n}{unit}"
            if v not in self.used_vals:
                self.used_vals.add(v)
                return v
        raise RuntimeError("取值池耗尽")

    def fact(self, p):
        objs = PROJ[p][2]
        for _ in range(10000):
            o = self.rng.choice(objs); a = self.rng.choice(ATTRS)
            if (o, a[0]) not in self.used_oa:
                self.used_oa.add((o, a[0]))
                return {"proj": p, "obj": o, "attr": a[0], "qw": a[2], "kind": a[1], "value": self.value(a[1])}
        raise RuntimeError("对象×属性耗尽")

    def person(self):
        return self.persons.pop()


def fact_sent(f, rng):
    t = rng.choice(["{o}的{a}定为{v}", "{o}这边，{a}最后敲定是{v}", "关于{o}：{a}确定为{v}", "{o}的{a}落实了，是{v}"])
    return t.format(o=f["obj"], a=f["attr"], v=f["value"])


def upd_sent(f, old, rng):
    t = rng.choice(["{o}的{a}由{w}调整为{v}", "{o}的{a}改了，从{w}换成{v}"])
    return t.format(o=f["obj"], a=f["attr"], v=f["value"], w=old)


def build():
    rng = random.Random(SEED)
    W = World(rng)
    dates = [START + dt.timedelta(days=round(i * 3.7)) for i in range(N_SESS)]
    projs = list(PROJ)
    # ---- 文档：每篇 (会话, 项目, 抬头日期)
    docs = []
    for k in range(N_DOCS):
        s = k * N_SESS // N_DOCS
        docs.append({"sess": s, "proj": projs[k % 6], "date": dates[s] - dt.timedelta(days=rng.randint(0, 3)), "targets": []})
    by_proj = {p: [d for d in docs if d["proj"] == p] for p in projs}
    shorts = {s: [] for s in range(N_SESS)}           # 会话 → 短事实条目
    Q = []                                            # 待出题：dict(cat, ..., ref=条目对象)

    def to_doc(p, item, min_sess=0):
        cands = [d for d in by_proj[p] if d["sess"] >= min_sess]
        d = rng.choice(cands); d["targets"].append(item); return d

    pr = lambda i: projs[i % 6]
    # 检索：短轮 50、长文档 50
    for i in range(50):
        f = W.fact(pr(i)); it = {"type": "fact", "f": f}
        shorts[rng.randrange(N_SESS)].append(it); Q.append({"cat": "fact_short", "it": it})
    for i in range(50):
        f = W.fact(pr(i + 3)); it = {"type": "fact", "f": f}
        to_doc(f["proj"], it); Q.append({"cat": "fact_long", "it": it})
    # 更新后最新值 20（证据短 10 / 长 10）；初值落在更早会话（短轮或文档随机）
    for i in range(20):
        f = W.fact(pr(i + 1)); old = f["value"]; new = W.value(f["kind"])
        s_new = rng.randint(12, N_SESS - 1)
        it0 = {"type": "fact", "f": dict(f)}
        if rng.random() < .5:
            shorts[rng.randint(0, s_new - 6)].append(it0)
        else:
            d = rng.choice([d for d in by_proj[f["proj"]] if d["sess"] <= s_new - 6]); d["targets"].append(it0)
        f2 = dict(f, value=new); it = {"type": "upd", "f": f2, "old": old}
        if i < 10:
            shorts[s_new].append(it)
        else:
            cands = [d for d in by_proj[f["proj"]] if d["sess"] >= s_new - 2] or by_proj[f["proj"]][-1:]
            rng.choice(cands)["targets"].append(it)
        Q.append({"cat": "update_latest", "it": it, "old": old})
    # 时间 (a) 短轮事件 30
    for i in range(30):
        p = pr(i); s = rng.randrange(N_SESS)
        while True:
            tmpl = rng.choice(EVENTS[p]); o = rng.choice(AREA) if "{o}" in tmpl else ""
            x = rng.choice(PROJ[p][2]); key = (tmpl, o, x)
            if key not in W.used_ev:
                W.used_ev.add(key); break
        per = W.person()
        ev = tmpl.format(o=o, x=x, p=per)
        d = dates[s] - dt.timedelta(days=rng.randint(1, 5))
        it = {"type": "event", "ev": ev, "date": d}
        shorts[s].append(it); Q.append({"cat": "time_short", "it": it})
    # 时间 (b) 长文档抬头日期 30
    for i in range(30):
        f = W.fact(pr(i + 2)); it = {"type": "fact", "f": f}
        d = to_doc(f["proj"], it); Q.append({"cat": "time_docdate", "it": it, "doc": d})
    # 时间 (c) 长文档正文日期 20
    for i in range(20):
        p = pr(i + 4)
        while True:
            o = rng.choice(PROJ[p][2]); t = rng.choice(TASKS)
            if (o, t) not in W.used_ot:
                W.used_ot.add((o, t)); break
        it = {"type": "due", "obj": o, "task": t, "proj": p}
        d = to_doc(p, it)
        it["date"] = d["date"] + dt.timedelta(days=rng.randint(6, 40))
        Q.append({"cat": "time_body", "it": it})

    # ---- 渲染
    conv = {"speaker_a": SP, "speaker_b": AS}
    turns_all = []                     # (会话, dia, 文本)

    def entry_text(it):
        if it["type"] == "fact":
            return fact_sent(it["f"], rng)
        if it["type"] == "upd":
            return upd_sent(it["f"], it["old"], rng)
        if it["type"] == "due":
            return f"{it['obj']}的{it['task']}须在{md(it['date'])}前完成"
        raise ValueError(it)

    for s in range(N_SESS):
        items = []                                      # (文本, 挂载条目, 是否长文档, 项目)
        for it in shorts[s]:
            if it["type"] == "event":
                t = rng.choice(["跟你说一下，{d}我{e}。", "记一笔：{d}{e}，挺顺利的。", "{d}我{e}，先记下来。"]).format(d=md(it["date"]), e=it["ev"])
                items.append((t, [it], False, None))
            else:
                t = rng.choice(["记一下：", "对了，", "跟你同步下，", "今天定了个事：", ""]) + entry_text(it) + "。"
                items.append((t, [it], False, it["f"]["proj"]))
        for _ in range(rng.randint(2, 4)):
            items.append((rng.choice(CHAT), [], False, None))
        for d in [d for d in docs if d["sess"] == s]:
            ents = [(entry_text(it), it) for it in d["targets"]]
            n_fill = rng.randint(*DOC_ENTRIES) - len(ents)
            n_ff = max(0, n_fill // 6)                    # v0.1 加长后对象×属性组合不够用，填充事实占比由 1/3 降到 1/6（只为结构）
            for _ in range(n_ff):                       # 不出题的填充事实
                ents.append((fact_sent(W.fact(d["proj"]), rng), None))
            for _ in range(max(0, n_fill - n_ff)):
                ents.append((rng.choice(FILL).format(o=rng.choice(PROJ[d["proj"]][2]), p=W.person() if rng.random() < .5 else rng.choice(W.persons[:40])), None))
            rng.shuffle(ents)
            title = PROJ[d["proj"]][1]
            head = rng.choice(["把{d}的{t}贴给你，帮我存档：", "{d}{t}，整理好了你存一下：", "补一份{d}的{t}："]).format(d=md(d["date"]), t=title)
            body = "\n".join(f"{k + 1}. {e.rstrip('。')}。" for k, (e, _) in enumerate(ents))
            items.append((head + "\n" + body, [it for _, it in ents if it is not None] + [{"type": "doc", "doc": d}], True, d["proj"]))
        rng.shuffle(items)
        ts = []
        for t, its, is_doc, p in items:
            dia = f"D{s + 1}:{len(ts) + 1}"
            ts.append({"speaker": SP, "dia_id": dia, "text": t})
            for it in its:
                it["dia"] = dia
                if it["type"] == "doc":
                    it["doc"]["dia"] = dia
            turns_all.append((s, dia, t, is_doc))
            j = PROJ[p][0] if p else None
            reply = rng.choice(ACK).format(j=j) if j else rng.choice(CHAT_ACK)
            dia2 = f"D{s + 1}:{len(ts) + 1}"
            ts.append({"speaker": AS, "dia_id": dia2, "text": reply})
            turns_all.append((s, dia2, reply, False))
        conv[f"session_{s + 1}"] = ts
        conv[f"session_{s + 1}_date_time"] = dates[s].isoformat()

    # ---- 出题
    def alt(val, lo, hi=N_SESS - 1):
        pat = re.compile(r"(?<![0-9])" + re.escape(val) + r"(?![0-9])")
        return sorted({dia for s, dia, t, _ in turns_all if lo <= s <= hi and pat.search(t)})

    sess_of = lambda dia: int(dia.split(":")[0][1:]) - 1
    qa = []
    for q in Q:
        it = q["it"]; c = q["cat"]
        if c in ("fact_short", "fact_long", "update_latest"):
            f = it["f"]
            qt = (f"{f['obj']}现在的{f['attr']}{f['qw']}？" if c == "update_latest" else f"{f['obj']}的{f['attr']}{f['qw']}？")
            grp = sorted(set([it["dia"]] + alt(f["value"], sess_of(it["dia"]))))
            row = dict(category=c, question=qt, answer=f["value"], evidence=[it["dia"]], evidence_groups=[grp], project=f["proj"])
            if c == "update_latest":
                row["distractor_values"] = [q["old"]]
        elif c == "time_short":
            qt = f"{it['ev']}是哪一天？"
            row = dict(category=c, question=qt, answer=ymd(it["date"]), evidence=[it["dia"]], evidence_groups=[[it["dia"]]])
        elif c == "time_docdate":
            f = it["f"]; d = q["doc"]
            qt = f"{f['obj']}的{f['attr']}定为{f['value']}，是在哪一天的{PROJ[f['proj']][1]}里记下的？"
            row = dict(category=c, question=qt, answer=ymd(d["date"]), evidence=[d["dia"]], evidence_groups=[[d["dia"]]], project=f["proj"])
        else:
            qt = f"{it['obj']}的{it['task']}须在哪一天前完成？"
            row = dict(category=c, question=qt, answer=ymd(it["date"]), evidence=[it["dia"]], evidence_groups=[[it["dia"]]], project=it["proj"])
        qa.append(row)
    for k, r in enumerate(qa):
        r["qid"] = f"cl{k:03d}"
    long_dias = sorted(d["dia"] for d in docs)
    return [{"sample_id": "crossproj-zh-long-hold", "conversation": conv, "qa": qa, "doc_dia_ids": long_dias}]


def main():
    data = build()
    out = HERE / "release" / "crossproj_zh_long_hold.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    c = data[0]["conversation"]
    n_turns = sum(len(v) for k, v in c.items() if re.fullmatch(r"session_\d+", k))
    print(f"写出 {out.name}：会话 {N_SESS}，轮 {n_turns}，长文档 {len(data[0]['doc_dia_ids'])}，题 {len(data[0]['qa'])}")


if __name__ == "__main__":
    main()
