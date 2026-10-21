# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""crossproj-zh-bodydate v0.1 生成器（vsa/PREREG_body_date.md §3）：零 LLM、零 key、确定性（固定种子 20261022）。
一人（林予安，无锡）× 五个并行项目；长文档两类——表头式（抬头句带日期 + 编号条目，部分条目带句中日期）与
日志式（抬头无日期，正文按「M月D日：」句首日期分日，后续无日期句继承当日，偶有句中日期）；程序出题、回填金标 dia_id。
  python3 gen.py            # → release/crossproj_zh_bodydate_hold.json（结构校验 vsa/bd_hold.py --check；冻结哈希 release/SHA256SUMS.json）
只用标准库。不读任何算法输出，不 import vsa/ 任何模块。与 crossproj-zh-long/gen.py 不共享人物、项目、对象表与抬头 / 条目句式。"""
import datetime as dt
import json
import pathlib
import random
import re

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261022
N_SESS = 40
START = dt.date(2026, 4, 6)
SP, AS = "林予安", "助手"
N_HEAD, N_LOG = 60, 30          # 表头式 / 日志式文档篇数（每篇一轮）
HEAD_ENTRIES = (26, 32)         # 表头式每篇条目数
LOG_DAYS, LOG_SENTS = (5, 6), (5, 6)   # 日志式：天数、每天句数（含当日首句）
MID_PER_DOC = (2, 4)            # 每篇句中日期条目数

PROJ = {
    "Q1": ("社区咖啡店开业", "咖啡店筹备例会纪要", "咖啡店装修日志",
           ["咖啡机", "磨豆机", "吧台", "门头招牌", "营业执照", "食品经营许可", "菜单设计", "烘焙豆", "外卖平台", "收银系统",
            "桌椅", "试营业活动", "员工招聘", "消防验收"]),
    "Q2": ("父亲心脏康复", "心内科会诊纪要", "父亲康复日志",
           ["支架复查", "心电监测", "降脂药", "心脏彩超", "康复门诊", "运动处方", "饮食方案", "血压计", "陪诊排班", "慢病医保",
            "动态心电图", "抗凝药", "复诊预约", "家庭氧气瓶"]),
    "Q3": ("公司年度审计", "审计协调会纪要", "审计现场日志",
           ["银行函证", "存货盘点", "固定资产清单", "收入截止测试", "关联方披露", "审计报告初稿", "管理层声明书", "往来对账", "税务底稿",
            "内控测试", "薪酬台账", "合同抽样", "费用报销抽查", "现金流量表"]),
    "Q4": ("老房出租翻新", "翻新协调会纪要", "翻新现场日志",
           ["厨房台面", "卫生间吊顶", "木地板翻新", "外墙防水", "旧家具清运", "热水器更换", "智能门锁", "窗户密封条", "墙纸", "阳台晾衣架",
            "租客合同", "中介挂牌", "燃气检测", "空调清洗"]),
    "Q5": ("学车考驾照", "驾校沟通会纪要", "练车日志",
           ["科目一题库", "科目二倒库", "侧方停车", "科目三路考", "体检表", "教练排班", "模拟器练习", "学车费用", "考场预约", "夜间灯光",
            "坡道起步", "直角转弯", "安全文明常识", "驾驶证照片"]),
}
ATTRS = [("经办人", "person", "是谁"), ("联系人", "person", "是谁"), ("合作单位", "org", "是哪家"), ("服务商", "org", "是哪家"),
         ("费用", "num:元", "是多少"), ("额度", "num:万元", "是多少"), ("份数", "num:份", "是多少"), ("存放处", "place", "在哪里")]
SUR = list("赵钱孙李郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳")
GIV = ["子墨", "欣怡", "浩宇", "雨桐", "梓涵", "若曦", "俊熙", "诗琪", "明哲", "佳琪", "思源", "语嫣", "博文", "可馨", "皓轩", "梦琪",
       "宇泽", "雅静", "晨曦", "嘉懿", "沐阳", "芷若", "景行", "清扬", "致远", "书言", "知秋", "听雨", "向晚", "南乔", "北辰", "怀瑾"]
ORG_A = ["澄明", "汇川", "泰和", "博雅", "瑞丰", "宏远", "启航", "嘉诚", "德润", "华茂", "兴邦", "海川", "景程", "恒信", "联创", "开元",
         "百川", "凯旋", "盛世", "同舟", "德馨", "望岳", "春晖", "长风", "鸿运", "思齐", "知行", "厚德", "弘毅", "致新"]
ORG_B = ["咨询公司", "会计师事务所", "装饰公司", "医疗服务站", "餐饮设备行", "物业公司", "驾培中心", "印务社", "信息技术公司", "家政公司",
         "建材商行", "检测公司"]
AREA = ["梁溪区", "滨湖区", "新吴区", "锡山区", "惠山区", "蠡湖边", "太湖新城", "南长街", "崇安寺", "清名桥", "江南大学旁", "火车站北"]
SPOT = ["一号仓", "资料柜", "前台抽屉", "车库隔间", "楼道储物柜", "办公室保险柜", "二楼小仓库", "样品架", "工具间", "档案盒"]
TASKS = ["现场复核", "交付验收", "签字确认", "第二轮评审", "费用结算", "资料归档", "样品寄送", "上门安装", "培训讲解", "整改回访",
         "初步排查", "方案汇报"]
MID = [   # (句中日期条目句式, 问句句式)；句中日期 = 本句约定 / 截止 / 安排日期
    ("{o}的{t}定在{d}", "{o}的{t}定在哪一天？"),
    ("{o}的{t}最晚{d}要完成", "{o}的{t}最晚哪一天要完成？"),
    ("按计划，{o}的{t}安排在{d}", "按计划，{o}的{t}安排在哪一天？"),
    ("{p}确认{o}的{t}放到{d}", "{o}的{t}放到了哪一天？"),
    ("{o}要赶在{d}之前做完{t}", "{o}要赶在哪一天之前做完{t}？"),
]
EVENTS = {
    "Q1": ["去{a}看了{x}的样品", "跟{p}去{a}谈了{x}", "约{p}在店里试了{x}"],
    "Q2": ["陪爸爸去{a}做了{x}", "带爸爸去{a}问了{x}", "跟{p}一起陪爸爸弄好了{x}"],
    "Q3": ["去{a}核对了{x}", "跟{p}在{a}过了一遍{x}", "陪审计组去{a}看了{x}"],
    "Q4": ["去{a}的老房子验了{x}", "跟{p}去{a}挑了{x}", "约{p}去老房子量了{x}"],
    "Q5": ["在{a}的考场练了{x}", "跟{p}去{a}熟悉了{x}", "在驾校跟{p}加练了{x}"],
}
FILL = ["{o}这件事先放一放，等{p}回话。", "{p}说{o}目前没有大问题。", "{o}的单据统一交给{p}保管。", "{o}还有两个方案在比，没拍板。",
        "{p}觉得{o}的节奏可以再快一点。", "{o}暂时不追加预算。", "{p}提议{o}再多问几家。", "{o}的现场照片放进共享文件夹了。",
        "{o}按原来的思路推进。", "{p}反映{o}沟通有点慢。", "{o}的记录由{p}补全。", "{o}没人提出异议。", "{p}负责盯紧{o}。",
        "{o}遇到点小麻烦，{p}已经在处理。", "{o}的措辞按{p}的意见改了。", "{p}认为{o}还能再精简。", "{o}的旧资料已经整理归档。",
        "{o}由{p}牵头做一次小结。"]
OPEN = ["上午{p}来电话聊了{o}。", "今天主要忙{o}。", "{p}过来一起看了{o}。", "早上先处理了{o}的杂事。", "下午跑了一趟{a}，为了{o}。",
        "今天心情还行，{o}有进展。", "跟{p}碰了下{o}。"]
CHAT = ["今天太湖边风好大，骑车差点被吹跑。", "最近总是失眠，先跟你吐槽两句。", "中午吃了碗小馄饨，舒服。", "晚上打算去南长街走走。",
        "这几天事情一件接一件，有点喘不过气。", "邻居家的狗又叫了一整晚。", "想周末去看场电影，看情况吧。", "刚跟大学室友视频了一会儿。",
        "楼下奶茶店换了新品，还挺好喝。", "办公室打印机又卡纸了。", "最近在读一本讲城市史的书。", "傍晚跑了两公里，出了身汗。",
        "雨伞落在地铁上了，心疼。", "好想放个长假。"]
ACK = ["好的，{j}这条记下了。", "收到，放进{j}里了。", "明白，{j}的信息已存好，随时可以问我。", "记好了，{j}最近挺忙的，注意身体。",
       "好，{j}已更新。还有要补的吗？", "已归档到{j}。", "了解，{j}就按这个版本记。"]
CHAT_ACK = ["辛苦啦，早点休息。", "听着就累，给自己放松一下。", "哈哈，挺有生活气息的。", "抱一下，熬过这阵就好。", "嗯嗯，我在。",
            "要不要我帮你理一下待办？"]
HEAD_TPL = ["这是{d}的{t}，帮我收好：", "{d}{t}，原样贴给你：", "麻烦存一下{d}开的{t}："]
LOG_TPL = ["{t}这几天的记录，贴给你存一下：", "把最近的{t}发你，帮我归档：", "{t}，最近几天的，存一下："]


def md(d):
    return f"{d.month}月{d.day}日"


def ymd(d):
    return f"{d.year}年{d.month}月{d.day}日"


class World:
    def __init__(self, rng):
        self.rng = rng
        self.vals, self.oa, self.ot, self.ev = set(), set(), set(), set()
        self.persons = [s + g for s in SUR for g in GIV if s + g != SP]
        rng.shuffle(self.persons)

    def value(self, kind):
        r = self.rng
        for _ in range(10000):
            if kind == "person":
                v = self.persons.pop()
            elif kind == "org":
                v = r.choice(ORG_A) + r.choice(ORG_B)
            elif kind == "place":
                v = r.choice(AREA) + r.choice(SPOT)
            else:
                u = kind.split(":")[1]
                n = {"元": r.randint(150, 88000), "万元": r.randint(2, 300), "份": r.randint(5, 2000)}[u]
                v = f"{n}{u}"
            if v not in self.vals:
                self.vals.add(v); return v
        raise RuntimeError("取值池耗尽")

    def fact(self, p):
        for _ in range(10000):
            o = self.rng.choice(PROJ[p][3]); a = self.rng.choice(ATTRS)
            if (o, a[0]) not in self.oa:
                self.oa.add((o, a[0]))
                return {"proj": p, "obj": o, "attr": a[0], "qw": a[2], "kind": a[1], "value": self.value(a[1])}
        raise RuntimeError("对象×属性耗尽")

    def mid(self, p, base):
        for _ in range(10000):
            o = self.rng.choice(PROJ[p][3]); t = self.rng.choice(TASKS)
            if (o, t) not in self.ot:
                self.ot.add((o, t))
                k = self.rng.randrange(len(MID))
                return {"type": "mid", "proj": p, "obj": o, "task": t, "tpl": k, "p": self.persons.pop(),
                        "date": base + dt.timedelta(days=self.rng.randint(3, 35))}
        raise RuntimeError("对象×任务耗尽")


def fact_sent(f, rng):
    t = rng.choice(["{o}的{a}落定为{v}", "{o}这块，{a}最终是{v}", "{o}的{a}敲定了，就是{v}", "关于{o}，{a}确认为{v}"])
    return t.format(o=f["obj"], a=f["attr"], v=f["value"])


def mid_sent(it):
    return MID[it["tpl"]][0].format(o=it["obj"], t=it["task"], d=md(it["date"]), p=it["p"])


def build():
    rng = random.Random(SEED)
    W = World(rng)
    dates = [START + dt.timedelta(days=round(i * 3.6)) for i in range(N_SESS)]
    projs = list(PROJ)
    docs = []
    for k in range(N_HEAD + N_LOG):
        kind = "head" if k < N_HEAD else "log"
        s = (k if kind == "head" else k - N_HEAD) * N_SESS // (N_HEAD if kind == "head" else N_LOG)
        p = projs[k % 5]
        d = {"kind": kind, "sess": s, "proj": p, "targets": [], "mids": []}
        if kind == "head":
            d["date"] = dates[s] - dt.timedelta(days=rng.randint(0, 3))
        else:
            n_days = rng.randint(*LOG_DAYS)
            days, cur = [], dates[s] - dt.timedelta(days=rng.randint(0, 2))
            for _ in range(n_days):
                days.append(cur); cur -= dt.timedelta(days=rng.randint(1, 2))
            d["days"] = sorted(days)
            d["slots"] = {j: [] for j in range(n_days)}       # 每天的目标条目（不含当日首句）
        docs.append(d)
    heads = {p: [d for d in docs if d["kind"] == "head" and d["proj"] == p] for p in projs}
    logs = {p: [d for d in docs if d["kind"] == "log" and d["proj"] == p] for p in projs}
    shorts = {s: [] for s in range(N_SESS)}
    Q = []
    pr = lambda i: projs[i % 5]

    def put_log(d, it, day=None):
        j = rng.randrange(len(d["days"])) if day is None else day
        d["slots"][j].append(it); it["day"] = j
        return j

    # 检索：短轮 20、长文档 40（表头式 28 / 日志式 12）
    for i in range(20):
        f = W.fact(pr(i)); it = {"type": "fact", "f": f}
        shorts[rng.randrange(N_SESS)].append(it); Q.append({"cat": "fact_short", "it": it})
    for i in range(40):
        f = W.fact(pr(i + 2)); it = {"type": "fact", "f": f}
        if i < 28:
            rng.choice(heads[f["proj"]])["targets"].append(it)
        else:
            put_log(rng.choice(logs[f["proj"]]), it)
        Q.append({"cat": "fact_long", "it": it})
    # (a) 短轮事件 30
    for i in range(30):
        p = pr(i); s = rng.randrange(N_SESS)
        while True:
            tp = rng.choice(EVENTS[p]); a = rng.choice(AREA); x = rng.choice(PROJ[p][3])
            if (tp, a, x) not in W.ev:
                W.ev.add((tp, a, x)); break
        ev = tp.format(a=a, x=x, p=W.persons.pop())
        it = {"type": "event", "ev": ev, "date": dates[s] - dt.timedelta(days=rng.randint(1, 5))}
        shorts[s].append(it); Q.append({"cat": "time_short", "it": it})
    # (b) 表头日期 40：表头式文档里不含日期的事实
    for i in range(40):
        f = W.fact(pr(i + 1)); it = {"type": "fact", "f": f}
        d = rng.choice(heads[f["proj"]]); d["targets"].append(it)
        Q.append({"cat": "time_head", "it": it, "doc": d})
    # (d) 日志继承 30：日志式文档里不含日期的事实，金标 = 所在日的句首日期
    for i in range(30):
        f = W.fact(pr(i + 3)); it = {"type": "fact", "f": f}
        d = rng.choice(logs[f["proj"]]); j = put_log(d, it)
        Q.append({"cat": "time_loginh", "it": it, "doc": d})
    # (c) 正文句中日期 50：表头式 35 / 日志式 15
    for i in range(50):
        p = pr(i + 4)
        if i < 35:
            d = rng.choice(heads[p]); it = W.mid(p, d["date"]); d["mids"].append(it)
        else:
            d = rng.choice(logs[p]); j = rng.randrange(len(d["days"])); it = W.mid(p, d["days"][j]); put_log(d, it, j)
        Q.append({"cat": "time_body", "it": it, "doc": d})
    # 每篇再补不出题的句中日期条目，凑到 MID_PER_DOC（干扰）
    for d in docs:
        if d["kind"] == "head":
            while len(d["mids"]) < rng.randint(*MID_PER_DOC):
                d["mids"].append(W.mid(d["proj"], d["date"]))
        else:
            n_mid = sum(it["type"] == "mid" for v in d["slots"].values() for it in v)
            for _ in range(max(0, rng.randint(1, 2) - n_mid)):
                j = rng.randrange(len(d["days"])); put_log(d, W.mid(d["proj"], d["days"][j]), j)

    # ---- 渲染
    conv = {"speaker_a": SP, "speaker_b": AS}
    turns_all = []

    def filler(p):
        return rng.choice(FILL).format(o=rng.choice(PROJ[p][3]), p=W.persons.pop() if rng.random() < .5 else rng.choice(W.persons[:40]))

    def ent(it):
        return fact_sent(it["f"], rng) if it["type"] == "fact" else mid_sent(it)

    def render_head(d):
        ents = [(ent(it), it) for it in d["targets"] + d["mids"]]
        n_fill = rng.randint(*HEAD_ENTRIES) - len(ents)
        for k in range(max(0, n_fill)):
            ents.append((fact_sent(W.fact(d["proj"]), rng) if k % 6 == 0 else filler(d["proj"]).rstrip("。"), None))
        rng.shuffle(ents)
        head = rng.choice(HEAD_TPL).format(d=md(d["date"]), t=PROJ[d["proj"]][1])
        return head + "\n" + "\n".join(f"{k + 1}. {e.rstrip('。')}。" for k, (e, _) in enumerate(ents)), [it for _, it in ents if it]

    def render_log(d):
        lines, used = [], []
        for j, day in enumerate(d["days"]):
            n = rng.randint(*LOG_SENTS)
            body = [(ent(it), it) for it in d["slots"][j]]
            for k in range(max(0, n - 1 - len(body))):
                body.append((fact_sent(W.fact(d["proj"]), rng) if k % 5 == 4 else filler(d["proj"]).rstrip("。"), None))
            rng.shuffle(body)
            first = rng.choice(OPEN).format(o=rng.choice(PROJ[d["proj"]][3]), p=W.persons.pop(), a=rng.choice(AREA))
            lines.append(f"{md(day)}：{first}" + "".join(f"{e.rstrip('。')}。" for e, _ in body))
            used += [it for _, it in body if it]
        return rng.choice(LOG_TPL).format(t=PROJ[d["proj"]][2]) + "\n" + "\n".join(lines), used

    for s in range(N_SESS):
        items = []
        for it in shorts[s]:
            if it["type"] == "event":
                t = rng.choice(["说一下，{d}那天我{e}。", "记个事：我{d}{e}。", "{d}我{e}，还算顺利。"]).format(d=md(it["date"]), e=it["ev"])
                items.append((t, [it], None))
            else:
                t = rng.choice(["帮我记一下，", "顺便说下，", "同步一个：", ""]) + fact_sent(it["f"], rng) + "。"
                items.append((t, [it], it["f"]["proj"]))
        for _ in range(rng.randint(2, 4)):
            items.append((rng.choice(CHAT), [], None))
        for d in [d for d in docs if d["sess"] == s]:
            text, its = render_head(d) if d["kind"] == "head" else render_log(d)
            items.append((text, its + [{"type": "doc", "doc": d}], d["proj"]))
        rng.shuffle(items)
        ts = []
        for t, its, p in items:
            dia = f"D{s + 1}:{len(ts) + 1}"
            ts.append({"speaker": SP, "dia_id": dia, "text": t})
            for it in its:
                it["dia"] = dia
                if it["type"] == "doc":
                    it["doc"]["dia"] = dia
            turns_all.append((s, dia, t))
            dia2 = f"D{s + 1}:{len(ts) + 1}"
            ts.append({"speaker": AS, "dia_id": dia2, "text": rng.choice(ACK).format(j=PROJ[p][0]) if p else rng.choice(CHAT_ACK)})
            turns_all.append((s, dia2, ts[-1]["text"]))
        conv[f"session_{s + 1}"] = ts
        conv[f"session_{s + 1}_date_time"] = dates[s].isoformat()

    # ---- 出题
    def alt(val, lo):
        pat = re.compile(r"(?<![0-9])" + re.escape(val) + r"(?![0-9])")
        return sorted({dia for s, dia, t in turns_all if s >= lo and pat.search(t)})

    sess_of = lambda dia: int(dia.split(":")[0][1:]) - 1
    qa = []
    for q in Q:
        it, c = q["it"], q["cat"]
        if c in ("fact_short", "fact_long"):
            f = it["f"]
            row = dict(category=c, question=f"{f['obj']}的{f['attr']}{f['qw']}？", answer=f["value"], evidence=[it["dia"]],
                       evidence_groups=[sorted(set([it["dia"]] + alt(f["value"], sess_of(it["dia"]))))], project=f["proj"])
        elif c == "time_short":
            row = dict(category=c, question=f"我{it['ev']}是在哪一天？", answer=ymd(it["date"]), evidence=[it["dia"]], evidence_groups=[[it["dia"]]])
        elif c == "time_head":
            f, d = it["f"], q["doc"]
            row = dict(category=c, question=f"{f['obj']}的{f['attr']}确定是{f['value']}这件事，记在哪一天的{PROJ[f['proj']][1]}里？",
                       answer=ymd(d["date"]), evidence=[d["dia"]], evidence_groups=[[d["dia"]]], project=f["proj"])
        elif c == "time_loginh":
            f, d = it["f"], q["doc"]
            row = dict(category=c, question=f"{f['obj']}的{f['attr']}是{f['value']}，这是哪一天的{PROJ[f['proj']][2]}里写的？",
                       answer=ymd(d["days"][it["day"]]), evidence=[d["dia"]], evidence_groups=[[d["dia"]]], project=f["proj"])
        else:
            row = dict(category=c, question=MID[it["tpl"]][1].format(o=it["obj"], t=it["task"]), answer=ymd(it["date"]),
                       evidence=[it["dia"]], evidence_groups=[[it["dia"]]], project=it["proj"], doc_kind=q["doc"]["kind"])
        qa.append(row)
    for k, r in enumerate(qa):
        r["qid"] = f"bd{k:03d}"
    return [{"sample_id": "crossproj-zh-bodydate-hold", "conversation": conv, "qa": qa,
             "doc_dia_ids": sorted(d["dia"] for d in docs), "doc_kind": {d["dia"]: d["kind"] for d in docs}}]


def main():
    data = build()
    out = HERE / "release" / "crossproj_zh_bodydate_hold.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    c = data[0]["conversation"]
    n = sum(len(v) for k, v in c.items() if re.fullmatch(r"session_\d+", k))
    print(f"写出 {out.name}：会话 {N_SESS}，轮 {n}，长文档 {len(data[0]['doc_dia_ids'])}，题 {len(data[0]['qa'])}")


if __name__ == "__main__":
    main()
