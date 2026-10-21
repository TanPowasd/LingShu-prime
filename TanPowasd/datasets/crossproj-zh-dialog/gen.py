# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""crossproj-zh-dialog v0.1 生成器：对话体（用户 / AI助手 交替）中文记忆保留集。零 LLM、零 key、确定性（固定种子 20261023）。
用途：正文日期 v0.2（vsa/PREREG_body_date_v0.2.md）的新保留集；本生成器与数据在 PREREG v0.2 与任何 v0.2 实现之前冻结。
形态仿 PerLTQA 对话记录（每单元 = 一段对话记录：首行「YYYY年M月D日 hh:mm:ss」+ 「说话人:话语」逐行，说话人与冒号之间无空格），
四个互不相干的人物各一个记忆库（库内单元按日期升序）；每库 24 段长对话（> K_MAX，多日期）+ 16 条短记录。
  python3 gen.py            # → release/crossproj_zh_dialog_hold.json（结构校验 vsa/dialog_hold.py --check；冻结哈希 release/SHA256SUMS.json）
只用标准库；不读任何算法输出，不 import vsa/ 任何模块；与 crossproj-zh-long / crossproj-zh-bodydate 的生成器不共享代码、人物、对象表与句式。"""
import datetime as dt
import json
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261023
AI = "AI助手"
N_LONG, N_SHORT = 24, 16
LINES = (26, 34)                      # 长对话行数（不含首行时间戳）
PER_BANK = {"first_plain": 6, "first_interf": 7, "body_echo": 10, "body_plain": 5, "short_time": 8, "fact": 8}

# ---------------------------------------------------------------- 人物（各自的对象、属性、事件、短记录事件、闲聊）
PERSONAS = [
    {"name": "苏沐晴", "city": "舟山", "role": "纪录片导演",
     "ents": ["《雾港》", "《盐田往事》", "《北纬三十度》", "《旧船坞》", "《潮汐笔记》", "《灯塔守望者》", "《渔火》", "《岛上的学校》"],
     "attrs": [("配乐", "person", "是谁"), ("摄影指导", "person", "是谁"), ("出品方", "org", "是哪家"), ("主要取景地", "place", "在哪里"),
               ("片长", "num:分钟", "是多少"), ("制作预算", "num:万元", "是多少")],
     "events": [("{e}的开机", "{e}正式开机", "D"), ("{e}的首映", "{e}首映", "D"), ("{e}的拍摄", "我们拍了{e}", "Y"),
                ("{e}在影展获奖", "{e}在影展拿了奖", "Y"), ("{e}的剪辑定稿", "{e}剪辑定稿", "D"), ("{e}立项", "{e}立项", "Y")],
     "life": ["我搬到了{c}的海边小屋", "我第一次一个人出海跟拍", "我买了第一台摄影机", "我在{c}办过一次小型放映会", "我去北京读了半年进修班"],
     "short": [("去{a}取了{x}", "去{a}取{x}"), ("在{a}补拍了{x}的空镜", "在{a}补拍{x}的空镜"), ("跟{p}在{a}看了{x}的粗剪", "跟{p}在{a}看{x}的粗剪"),
               ("把{x}的硬盘送去了{a}", "把{x}的硬盘送去{a}")],
     "fill": ["拍{e}的时候，海风大得镜头都在抖。", "{p}一直帮我盯着{e}的进度。", "{e}里那段渔民的采访我剪了很多遍。", "有时候我会怀疑{e}到底有没有人看。",
              "{e}的素材加起来有好几十个小时。", "{p}说{e}的节奏前半段有点慢。", "我挺想把{e}带去学校放给孩子们看。", "那段时间为了{e}几乎没睡过整觉。",
              "{e}最难拍的是夜里的码头。", "跟{p}聊完之后，我对{e}的结尾有了新想法。", "{e}的字幕翻译还没完全弄好。", "其实{e}最早只是一个很小的念头。"],
     "obj": ["航拍器", "收音杆", "调色样片", "采访录音", "场记单"]},
    {"name": "顾远舟", "city": "宁波", "role": "桥梁工程师",
     "ents": ["东湾大桥", "青石隧道", "南渡口栈桥", "西环高架", "河心岛步道桥", "老城人行天桥", "北仑货运支线", "月湖景观桥"],
     "attrs": [("总监理", "person", "是谁"), ("结构负责人", "person", "是谁"), ("施工单位", "org", "是哪家"), ("预制场", "place", "在哪里"),
               ("主跨长度", "num:米", "是多少"), ("合同金额", "num:万元", "是多少")],
     "events": [("{e}的合龙", "{e}合龙", "D"), ("{e}的通车", "{e}通车", "D"), ("{e}开工", "{e}开工", "Y"), ("{e}的荷载试验", "{e}做了荷载试验", "D"),
                ("{e}拿到设计批复", "{e}拿到设计批复", "Y"), ("{e}的竣工验收", "{e}竣工验收", "D")],
     "life": ["我考下了一级建造师", "我调到了{c}分公司", "我第一次带队做方案投标", "我在{c}买了房", "我去德国做过三个月访问"],
     "short": [("去{a}看了{x}的钢筋绑扎", "去{a}看{x}的钢筋绑扎"), ("在{a}签了{x}的变更单", "在{a}签{x}的变更单"),
               ("跟{p}去{a}复测了{x}", "跟{p}去{a}复测{x}"), ("把{x}的图纸交到了{a}", "把{x}的图纸交到{a}")],
     "fill": ["{e}的工期压得特别紧。", "{p}对{e}的质量抓得很严。", "下雨天{e}的现场全是泥。", "{e}那边的地质条件比预想复杂。", "我经常半夜被{e}的电话叫醒。",
              "{p}建议{e}的支座换个型号。", "{e}的监测数据我每天都要看一遍。", "说实话{e}是我做过最累的项目。", "{e}的方案前后改了不下十次。",
              "跟{p}吵过一架之后，{e}的分工反而清楚了。", "{e}周边的居民意见也挺多的。", "{e}的模型现在还摆在我办公桌上。"],
     "obj": ["检测报告", "全站仪", "沉降观测表", "焊缝样件", "施工日志本"]},
    {"name": "方知夏", "city": "扬州", "role": "中学语文老师",
     "ents": ["《松间集》", "青蓝读书会", "云岭支教", "启明话剧社", "校园作文大赛", "《晨读》校刊", "古诗词研学营", "毕业纪念册"],
     "attrs": [("指导老师", "person", "是谁"), ("主编", "person", "是谁"), ("合作出版社", "org", "是哪家"), ("活动地点", "place", "在哪里"),
               ("印数", "num:册", "是多少"), ("经费", "num:元", "是多少")],
     "events": [("{e}的首次活动", "{e}办了首次活动", "D"), ("{e}的成立", "{e}成立", "Y"), ("{e}的汇报演出", "{e}办了汇报演出", "D"),
                ("{e}的出版", "{e}出版", "Y"), ("{e}的颁奖", "{e}颁奖", "D"), ("{e}的启动", "{e}启动", "Y")],
     "life": ["我第一次当班主任", "我调到了{c}的新学校", "我评上了高级教师", "我在{c}租了带院子的老房子", "我去山区支教了一学期"],
     "short": [("去{a}领了{x}", "去{a}领{x}"), ("在{a}给学生讲了{x}", "在{a}给学生讲{x}"), ("跟{p}去{a}布置了{x}", "跟{p}去{a}布置{x}"),
               ("把{x}的稿子交到了{a}", "把{x}的稿子交到{a}")],
     "fill": ["{e}让我重新喜欢上了教书。", "{p}为{e}操了不少心。", "学生们对{e}的热情比我想的高。", "{e}的筹备工作琐碎得很。", "有家长对{e}提过一些意见。",
              "{p}觉得{e}可以再办得轻松一点。", "{e}里有个孩子的文章让我读哭了。", "我把{e}的照片都存在一个相册里。", "{e}的经费一直是个难题。",
              "跟{p}商量过后，{e}改成了每月一次。", "{e}的流程我写了满满三页纸。", "以后还想把{e}继续做下去。"],
     "obj": ["获奖证书", "排练剧本", "借书清单", "活动横幅", "学生作品集"]},
    {"name": "程一帆", "city": "成都", "role": "餐厅主厨",
     "ents": ["湖畔店", "老街店", "秋季菜单", "川味发酵实验室", "青年厨艺大赛", "山野供货农场", "夜宵档口", "私房宴"],
     "attrs": [("店长", "person", "是谁"), ("面点主管", "person", "是谁"), ("供应商", "org", "是哪家"), ("中央厨房", "place", "在哪里"),
               ("座位数", "num:位", "是多少"), ("装修投入", "num:万元", "是多少")],
     "events": [("{e}的开业", "{e}开业", "D"), ("{e}的试菜会", "{e}办了试菜会", "D"), ("{e}的筹建", "{e}开始筹建", "Y"),
                ("{e}拿到金奖", "{e}拿到金奖", "Y"), ("{e}的上新", "{e}上新", "D"), ("{e}的签约", "{e}签约", "Y")],
     "life": ["我在{c}开了第一家小馆子", "我去日本学了半年料理", "我拿到了高级厨师证", "我把爸妈接到了{c}", "我第一次上电视做节目"],
     "short": [("去{a}挑了{x}", "去{a}挑{x}"), ("在{a}试做了{x}", "在{a}试做{x}"), ("跟{p}去{a}谈了{x}", "跟{p}去{a}谈{x}"),
               ("把{x}的样品送到了{a}", "把{x}的样品送到{a}")],
     "fill": ["{e}那阵子我每天站十几个小时。", "{p}在{e}上帮了我大忙。", "{e}的口味调整了好多轮。", "客人对{e}的评价两极分化。", "{e}的成本一直压不下来。",
              "{p}说{e}的出菜速度得再快些。", "{e}的员工流动有点大。", "我经常在{e}关门后一个人试菜。", "{e}的灶台是我亲自挑的。",
              "跟{p}聊完，我决定{e}先不扩张。", "{e}的招牌菜是辣子鸡。", "其实{e}最开始就是想给朋友做顿饭。"],
     "obj": ["菌菇", "新菜单样张", "砂锅", "辣椒样品", "冷链箱"]},
]
SUR = list("白柏毕边卞蔡曹岑常陈成褚崔戴邓丁董杜段樊范方费冯符傅甘高葛耿龚古谷顾关管郭韩杭郝何贺洪侯胡华黄霍姬季贾简江姜蒋金靳景康柯孔赖蓝郎雷黎李连梁廖林凌刘柳龙卢鲁陆路罗骆吕马麦毛梅孟苗莫穆倪聂宁欧潘庞裴彭皮蒲齐钱乔秦邱裘曲饶任荣阮单尚邵沈盛施石时史舒宋苏孙谭汤唐陶滕田童万汪王韦卫魏温文翁吴伍武奚夏向萧谢辛邢熊徐许薛严颜晏杨姚叶易殷尹应于余俞虞袁岳云詹张章赵郑钟周朱祝卓邹左")
GIV = ["若兰", "清和", "子衿", "望舒", "砚秋", "听澜", "知远", "星河", "既白", "安歌", "南星", "疏影", "长庚", "未央", "惊蛰",
       "怀远", "临川", "思齐", "敬亭", "晚舟", "青禾", "云岫", "照野", "明岚", "书亦", "沐风", "景澄"]
ORG_A = ["远帆", "青柏", "澜庭", "拾光", "海纳", "鸿图", "知序", "百木", "云栖", "叠翠", "朗润", "初见", "磐石", "竹里", "星汉", "东篱"]
ORG_B = ["影业", "传媒", "建工集团", "路桥公司", "出版社", "文化公司", "餐饮管理公司", "农业合作社", "设计院", "印务公司"]
AREA = ["城东", "城西", "老城区", "新区", "江边", "湖西", "大学城", "高铁站南", "工业园", "港区", "古镇", "山脚"]
SPOT = ["二号仓库", "临时工棚", "社区活动室", "旧厂房", "文化站", "会展中心", "物流园", "图书馆三楼"]

AI_GEN = ["这听起来真的很不容易呢。", "那段时间您是怎么调整状态的呢？", "这是什么时候的事呢？", "您当时最担心的是什么？", "后来进展顺利吗？",
          "能再多讲讲{e}吗？", "{p}是您的老搭档吗？", "您觉得这件事对您影响大吗？", "我很好奇当时大家的反应。", "嗯嗯，我在听，您继续说。",
          "听起来{e}对您意义很特别。", "那您现在回头看，会有什么不一样的选择吗？", "这个细节我记下了。", "您身边有人支持您吗？"]
USR_ACK = ["嗯，", "是的，", "这个我记得，", "说来话长，", "对，", "哈哈，", ""]
# 事实句（无日期）：(陈述, 用于 F 题的问句模板)
FACT_S = {"person": ["{e}的{k}是{v}。", "{e}的{k}请的是{v}。", "{e}这边，{k}是{v}在做。", "{e}的{k}我们最终敲定为{v}。"],
          "org": ["{e}的{k}是{v}。", "{e}最后选了{v}当{k}。", "{e}这边，{k}定了{v}。", "{e}的{k}我们最终敲定为{v}。"],
          "place": ["{e}的{k}在{v}。", "{e}这边，{k}定在了{v}。", "{e}的{k}最后选在{v}。", "{e}的{k}我们最终敲定为{v}。"],
          "num": ["{e}的{k}是{v}。", "{e}的{k}最后控制在{v}。", "{e}这边，{k}定了{v}。", "{e}的{k}我们最终敲定为{v}。"]}
FACT_Q_F = ["{e}的{k}是{v}这件事，{n}是在哪一天跟AI助手说的？", "{n}在哪一天提到{e}的{k}定为{v}？", "什么时候{n}聊到{e}的{k}是{v}的？",
            "{n}告诉AI助手{e}的{k}是{v}，是在哪一天？"]
# 正文日期陈述：mid = 日期在句中（句首为说话人或连接语）；head = 日期作为该行第二句的句首
BODY_MID = ["{ack}{s}是在{t}。", "{ack}我记得{s}应该是{t}，没错。", "{ack}{s}定在了{t}，那天特别忙。", "{ack}{v}，那是{t}的事了。"]
BODY_HEAD = ["这个我印象很深。{t}，{v}。", "我想想。{t}那会儿，{v}。"]
# AI 回声提问（问句形、无日期）：near = 与问题近同文；para = 换说法
ECHO_NEAR = ["请问{s}是在哪一{u}呢？", "{n}，我想问一下{s}是在哪一{u}呀？", "对了，{s}是在哪一{u}来着？"]
ECHO_PARA = ["{e}这件事，大概是什么时候呢？", "您还记得{s}的时间吗？", "那{s}具体是哪个时间点呀？"]
# 主动提及的正文日期（无回声）引子
VOLUN = ["对了，", "跟你说个事，", "差点忘了，", "还有，"]
# 干扰候选：提到同一对象与属性但不给取值的句子 + 两个早段日期句
DECOY_K = ["{e}的{k}当时其实考虑过好几个人选。", "说到{e}的{k}，一开始我们分歧挺大。", "{e}的{k}这件事拖了很久才有眉目。"]
DECOY_T = ["{t}我们第一次认真讨论{e}。", "到了{t}，{e}又推翻重来了一版。", "{e}最早的草案是{t}写的。"]
LIFE_T = ["{t}的时候，{l}。", "我还记得{t}{l}。", "{l}，那是{t}。"]
FILL_G = ["{p}前两天还专门打电话问{e}的情况。", "为了{e}我推掉了好几个饭局。", "{e}的群里每天消息都刷不完。", "我在笔记本上给{e}画了个时间表。",
          "{p}的建议我觉得挺中肯的。", "最近天气忽冷忽热，人也跟着没精神。", "{e}的事情我还没跟家里人细说。", "那天跟{p}一直聊到很晚。",
          "我最怕的是{e}半途而废。", "有一阵子我差点想放弃{e}。", "{p}帮我联系了几个靠谱的人。", "做{e}让我认识了不少新朋友。",
          "晚上回家路上我还在想{e}。", "说起{e}，我总会想起{p}那句玩笑话。", "{e}的账本是我自己记的。", "我和{p}约好下个月再碰一次头。",
          "{e}的进展比计划慢了一点。", "我妈总念叨让我别把自己逼太紧。", "{e}的事暂时就这些。", "下周我打算去{a}转转，找找灵感。"]
SHORT_TAIL = ["好的，已经帮您记下了。", "收到，辛苦啦。", "明白，这条存好了。", "记好了，注意休息。"]


def ymd(d):
    return f"{d.year}年{d.month}月{d.day}日"


class Bank:
    def __init__(self, P, rng):
        self.P, self.rng = P, rng
        self.vals, self.used_fact, self.used_ev = set(), set(), set()
        self.persons = [s + g for s in SUR for g in GIV if s + g != P["name"]]
        rng.shuffle(self.persons)
        n = N_LONG + N_SHORT
        start = dt.date(2026, 1, 5) + dt.timedelta(days=rng.randint(0, 6))
        self.hdates = [start + dt.timedelta(days=round(i * 6.5)) for i in range(n)]   # 库内每单元日期互不相同，全在 2026 年
        kinds = ["long"] * N_LONG + ["short"] * N_SHORT
        rng.shuffle(kinds)
        self.units = [{"kind": k, "date": d, "main": rng.choice(P["ents"]), "slots": [], "early": []} for k, d in zip(kinds, self.hdates)]

    def person(self):
        return self.persons.pop()

    def value(self, kind):
        r = self.rng
        for _ in range(10000):
            if kind == "person":
                v = self.person()
            elif kind == "org":
                v = r.choice(ORG_A) + r.choice(ORG_B)
            elif kind == "place":
                v = r.choice(AREA) + r.choice(SPOT)
            else:
                u = kind.split(":")[1]
                n = {"分钟": r.randint(40, 180), "万元": r.randint(3, 900), "米": r.randint(30, 1200), "册": r.randint(200, 9000),
                     "元": r.randint(500, 99000), "位": r.randint(20, 300)}[u]
                v = f"{n}{u}"
            if v not in self.vals:
                self.vals.add(v); return v
        raise RuntimeError("取值池耗尽")

    def fact(self, e=None):
        for _ in range(10000):
            ee = e or self.rng.choice(self.P["ents"]); a = self.rng.choice(self.P["attrs"])
            if (ee, a[0]) not in self.used_fact:
                self.used_fact.add((ee, a[0]))
                return {"e": ee, "k": a[0], "qw": a[2], "kind": a[1].split(":")[0], "v": self.value(a[1])}
        raise RuntimeError("对象×属性耗尽")

    def event(self, e=None):
        for _ in range(10000):
            ee = e or self.rng.choice(self.P["ents"]); ev = self.rng.choice(self.P["events"])
            if (ee, ev[0]) not in self.used_ev:
                self.used_ev.add((ee, ev[0]))
                return {"e": ee, "s": ev[0].format(e=ee), "v": ev[1].format(e=ee), "g": ev[2]}
        raise RuntimeError("对象×事件耗尽")


def rand_date(rng, gran, avoid_years, avoid_dates):
    """事件日期：Y 粒度 2010–2025 年中未在本单元出现过的年份；D 粒度 2014–2026 年的具体日期（不与本单元已有日期同日、同年）。"""
    for _ in range(10000):
        y = rng.randint(2010, 2025) if gran == "Y" else rng.randint(2014, 2025)
        if y in avoid_years:
            continue
        d = dt.date(y, rng.randint(1, 12), rng.randint(1, 28))
        if d in avoid_dates:
            continue
        return d
    raise RuntimeError("日期耗尽")


def tstr(d, gran):
    return f"{d.year}年" if gran == "Y" else ymd(d)


def build():
    rng = random.Random(SEED)
    banks, qa = {}, []
    for P in PERSONAS:
        B = Bank(P, rng)
        n = P["name"]
        longs = [i for i, u in enumerate(B.units) if u["kind"] == "long"]
        shorts = [i for i, u in enumerate(B.units) if u["kind"] == "short"]
        Q = []
        # 题目植入（每库）：首日期（普通 / 干扰）、正文日期（回声 / 主动）、短记录时间、检索事实
        for c in ("first_plain", "first_interf"):
            for _ in range(PER_BANK[c]):
                u = rng.choice(longs); f = B.fact(B.units[u]["main"] if rng.random() < .6 else None)
                it = {"type": "fact", "f": f}
                B.units[u]["slots"].append(it)
                q = {"cat": c, "it": it, "unit": u}
                if c == "first_interf":
                    du = rng.choice([x for x in longs if x != u])
                    B.units[du]["early"].append({"type": "decoy", "f": f})
                    q["decoy"] = du
                Q.append(q)
        for c in ("body_echo", "body_plain"):
            for _ in range(PER_BANK[c]):
                u = rng.choice(longs); ev = B.event(B.units[u]["main"] if rng.random() < .5 else None)
                it = {"type": c, "ev": ev, "style": ("near" if rng.random() < .65 else "para") if c == "body_echo" else None,
                      "head": rng.random() < .25}
                B.units[u]["slots"].append(it)
                Q.append({"cat": c, "it": it, "unit": u})
        for _ in range(PER_BANK["short_time"]):
            u = rng.choice([x for x in shorts if not any(s["type"] == "short_ev" for s in B.units[x]["slots"])])
            tp = rng.choice(P["short"])
            a, x, p = B.value("place"), rng.choice(P["ents"] + P["obj"]), B.person()     # 地点走取值池：不与事实取值撞车
            it = {"type": "short_ev", "st": tp[0].format(a=a, x=x, p=p), "sq": tp[1].format(a=a, x=x, p=p)}
            B.units[u]["slots"].append(it)
            Q.append({"cat": "short_time", "it": it, "unit": u})
        for k in range(PER_BANK["fact"]):
            u = rng.choice(longs if k % 2 == 0 else shorts); f = B.fact()
            it = {"type": "fact", "f": f}
            B.units[u]["slots"].append(it)
            Q.append({"cat": "fact", "it": it, "unit": u})

        # 渲染
        texts = []
        for ui, U in enumerate(B.units):
            hd = U["date"]
            hdr = f"{ymd(hd)} {rng.randint(8, 22):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
            used_years, used_dates = {hd.year}, {hd}

            def take(gran):
                d = rand_date(rng, gran, used_years, used_dates)
                used_years.add(d.year); used_dates.add(d)
                return d

            def P_(): return B.person() if rng.random() < .4 else rng.choice(B.persons[:60])
            pool = [(x, None) for x in P["fill"]] + [(x, "g") for x in FILL_G]
            rng.shuffle(pool)

            def fill(e):                                            # 单元内填充句不放回抽取（用尽再洗牌），减少逐字重复
                if not pool:
                    pool.extend([(x, None) for x in P["fill"]] + [(x, "g") for x in FILL_G]); rng.shuffle(pool)
                x, _ = pool.pop()
                return x.format(e=e, p=P_(), a=rng.choice(AREA))
            if U["kind"] == "short":
                lines = []
                for it in U["slots"]:
                    if it["type"] == "short_ev":
                        lines.append(f"{n}:" + rng.choice(["今天", "今天下午", "今天一早", "刚才"]) + f"{it['st']}。")
                    else:
                        f = it["f"]
                        lines.append(f"{n}:" + rng.choice(["记一下，", "跟你说一声，", "同步一下，", ""]) + rng.choice(FACT_S[f["kind"]]).format(e=f["e"], k=f["k"], v=f["v"]))
                if not lines:
                    lines.append(f"{n}:" + fill(U["main"]))
                lines.append(f"{AI}:" + rng.choice(SHORT_TAIL))
                texts.append(hdr + "\n" + "\n".join(lines)); U["text"] = texts[-1]
                continue
            # 长对话：块 = 若干行（AI 行 / 用户行）；先排早段（干扰与生活日期），再随机插入题目块与填充
            e0 = U["main"]
            early, body = [], []
            for it in U["early"]:
                f = it["f"]
                t1, t2 = take("Y"), take("Y")
                early.append([f"{AI}:" + rng.choice(["能讲讲{e}是怎么开始的吗？", "{e}的来龙去脉是怎样的呢？", "我很想听听{e}的故事。"]).format(e=f["e"]),
                              f"{n}:" + rng.choice(USR_ACK) + "".join(x.format(t=tstr(tt, "Y"), e=f["e"]) for x, tt in zip(rng.sample(DECOY_T, 2), (t1, t2)))
                              + rng.choice(DECOY_K).format(e=f["e"], k=f["k"])])
            for _ in range(rng.randint(1, 2)):                     # 每段长对话 1–2 句生活日期（多日期来源之一）
                g = "Y" if rng.random() < .6 else "D"
                t = take(g)
                body.append([f"{AI}:" + rng.choice(AI_GEN).format(e=e0, p=P_()), f"{n}:" + rng.choice(LIFE_T).format(t=tstr(t, g), l=rng.choice(P["life"]).format(c=P["city"]))])
            for it in U["slots"]:
                if it["type"] == "fact":
                    f = it["f"]
                    blk = [f"{AI}:" + rng.choice(AI_GEN).format(e=f["e"], p=P_()),
                           f"{n}:" + rng.choice(USR_ACK) + rng.choice(FACT_S[f["kind"]]).format(e=f["e"], k=f["k"], v=f["v"])
                           + fill(f["e"])]
                elif it["type"] in ("body_echo", "body_plain"):
                    ev = it["ev"]; d = take(ev["g"]); it["date"] = d
                    t = tstr(d, ev["g"]); u_ = "年" if ev["g"] == "Y" else "天"
                    stmt = (rng.choice(BODY_HEAD).format(t=t, v=ev["v"]) if it["head"]
                            else rng.choice(BODY_MID).format(ack=rng.choice(USR_ACK), s=ev["s"], t=t, v=ev["v"]))
                    tail = fill(ev["e"])
                    if it["type"] == "body_echo":
                        tpl = rng.choice(ECHO_NEAR if it["style"] == "near" else ECHO_PARA)
                        it["echo"] = tpl.format(s=ev["s"], u=u_, n=n, e=ev["e"])
                        blk = [f"{AI}:" + it["echo"], f"{n}:" + stmt + tail]
                    else:
                        blk = [f"{AI}:" + rng.choice(AI_GEN).format(e=ev["e"], p=P_()), f"{n}:" + rng.choice(VOLUN) + stmt + tail]
                body.append(blk)
            n_lines = rng.randint(*LINES)
            have = sum(len(b) for b in early + body)
            while have < n_lines:                                   # 填充：AI 泛问 + 用户闲谈（无日期）
                body.append([f"{AI}:" + rng.choice(AI_GEN).format(e=e0, p=P_()),
                             f"{n}:" + rng.choice(USR_ACK) + fill(e0) + fill(rng.choice(P["ents"]))])
                have += 2
            rng.shuffle(body)
            opening = [f"{AI}:" + rng.choice(["您好，{n}，今天想聊点什么？", "{n}，好久不见，最近怎么样？", "嗨，{n}，今天心情如何？"]).format(n=n),
                       f"{n}:" + rng.choice(["想跟你聊聊{e}。", "最近一直在忙{e}，跟你说说。", "还行，就是{e}的事情有点多。"]).format(e=e0)]
            lines = opening + [x for b in early for x in b] + [x for b in body for x in b]
            texts.append(hdr + "\n" + "\n".join(lines)); U["text"] = texts[-1]

        # 出题
        for q in Q:
            it, c, u = q["it"], q["cat"], q["unit"]
            U = B.units[u]
            if c in ("first_plain", "first_interf"):
                f = it["f"]
                row = dict(category=c, question=rng.choice(FACT_Q_F).format(e=f["e"], k=f["k"], v=f["v"], n=n), answer=ymd(U["date"]))
                row["fact"] = {"e": f["e"], "k": f["k"], "v": f["v"]}
                if c == "first_interf":
                    row["decoy_unit"] = q["decoy"]
            elif c in ("body_echo", "body_plain"):
                ev = it["ev"]
                row = dict(category=c, question=f"{ev['s']}是在哪一{'年' if ev['g'] == 'Y' else '天'}？", answer=tstr(it["date"], ev["g"]),
                           head_form=it["head"])
                if c == "body_echo":
                    row["echo"] = it["echo"]; row["echo_style"] = it["style"]
            elif c == "short_time":
                row = dict(category=c, question=f"{n}{it['sq']}是在哪一天？", answer=ymd(U["date"]))
            else:
                f = it["f"]
                row = dict(category=c, question=f"{f['e']}的{f['k']}{f['qw']}？", answer=f["v"], fact={"e": f["e"], "k": f["k"], "v": f["v"]})
            row["evidence"] = [u]
            qa.append(dict(bank=n, **row))
        banks[n] = {"persona": {"name": n, "city": P["city"], "role": P["role"]}, "texts": texts,
                    "unit_kind": [U["kind"] for U in B.units]}
    for k, r in enumerate(qa):
        r["qid"] = f"dg{k:03d}"
    return {"name": "crossproj-zh-dialog", "version": "0.1", "seed": SEED, "banks": banks, "qa": qa}


def main():
    data = build()
    out = HERE / "release" / "crossproj_zh_dialog_hold.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    nu = sum(len(b["texts"]) for b in data["banks"].values())
    print(f"写出 {out.name}：库 {len(data['banks'])}，单元 {nu}，题 {len(data['qa'])}")


if __name__ == "__main__":
    main()
