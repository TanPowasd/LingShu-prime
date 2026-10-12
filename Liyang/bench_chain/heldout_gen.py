# -*- coding: utf-8 -*-
"""保留扰动集 H1 生成（见 PREREG_HELDOUT.md）：事件句由 LLM（cline-pass/deepseek-v4.1-flash，thinking 关，temperature 1.0）
按段批量改写——与 perturb.py 的规则替换是两种生成方式。主体/属性/值/并存值/起因逐字保留由机械校验保证，校验不过重试 2 次，
仍不过则保留原句并计数。生成结果只落盘、不人工查看，评测前不据此改任何代码。
  python heldout_gen.py run [budget_sec]     （缓存命中即跳过，可断点续跑）
  python heldout_gen.py build                → out/heldout/corpus_h1.json（全部事件句改写）+ rewrite_map.json"""
import hashlib, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from cb_common import *  # noqa
sys.path[1:1] = [HMBD]
import llm as L  # noqa: E402
from lingshu_ng.chain.extract import extract  # noqa: E402

VARIANT = os.environ.get("HO_VARIANT", "h1")
D = os.path.join(OUT, "heldout" if VARIANT == "h1" else f"heldout_{VARIANT}"); os.makedirs(D, exist_ok=True)
L.CACHE = os.path.join(OUT, "llm", "cache"); L.COSTLOG = os.path.join(OUT, "llm", "cost.jsonl")   # 与本线同一账本
import llm_shared  # noqa: E402   2026-10-12：统一缓存 LINGSHU_LLM_CACHE（键不变，旧缓存只读回退），记前缀缓存命中
llm_shared.install(L, costlog=L.COSTLOG)
BUDGET_USD = float(os.environ.get("HO_BUDGET", "1.5"))   # chain-r10：本轮跑时设 HO_BUDGET=0.8123（起点 $0.5123 + 本轮上限 $0.3）
SPLIT = re.compile(r"(?<=[。])")
EV_MARK = ("首次确立为", "此后确立为", "调整为", "转为", " 移到了 ", "被撤销，此后不再保留取值", "出现两种并存的取值：", "的争议就此裁定为")
BANNED = ("首次确立为", "此后确立为", "调整为", "转为", "移到了", "被撤销", "并存的取值", "裁定为", "起因是")
SYS = ("你是中文写作者。下面每条是一句工作日志/叙事里的「状态变更记录」。请把每条改写成一句自然的中文叙述句。要求：\n"
       "1. 意思不变：首次定下某值、改成新值、搬到新位置、被撤销此后不再有值、出现两个并存的值尚未定下、争议最终定为某值——原句是哪种就写哪种；原句有起因就保留起因。\n"
       "2. 每条后面列出的「必须逐字出现」的字符串，要原样出现在改写句里（不改字、不拆开、不加引号）。\n"
       "3. 换一种与原句明显不同的说法和语序，不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。"
       "句式自由选择（倒装、口语、被动、把主体放在后面、把起因放在前面等都可以），各条风格可以不同。\n"
       "4. 不要引入任何别的名称或数值。\n"
       "5. 每条只写一句话，以句号结尾，句中不出现其他句号。\n"
       "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")


#: H2（PREREG_HELDOUT_H2.md）：另一种提示词——口语化的群聊/随笔/旁白，允许插话、先说结论再补细节、一句里带语气词；
#: temperature 1.3、只改写 test 文档（dev 文档 A1/B1 不生成）
SYS_H2 = ("你是一位写东西很随意的中文作者。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条用你自己的话、"
          "像在工作群聊里随口汇报、或在随笔/小说旁白里顺带一提那样，写成一句中文。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开）。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。"
          "可以口语、可以加语气词、可以先说结论再补原因、可以用问句或感叹句的语气，但整条只能是一句话。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以句号结尾，句中不出现其他句号、问号或叹号。\n"
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")
#: d3（dev 改写集，只改 dev 文档 A1/B1，用于迭代 v8 宽松抽取；2026-10-12 加）：叙事/旁白式长句，时间或场景开头、可插入修饰语
SYS_D3 = ("你是一位中文小说/纪实作者。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条写成叙事文字里的一句话，"
          "可以用时间或场景开头（如「到了那时」「会后」「那阵子」），可以在主体前后加修饰语，可以把起因放在句首或句中。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开）。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以句号结尾，句中不出现其他句号、问号或叹号。\n"
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")
#: H3（PREREG_HELDOUT_H3.md，保留集，只改 test 文档）：书面公文体——周报/会议纪要/公告/新闻通稿条目，可用被动、名词化、「经…」「鉴于…」「根据…」
SYS_H3 = ("你是一位负责写周报、会议纪要和对外公告的中文文秘。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条改写成正式书面语的一句话，"
          "风格像周报条目、会议纪要决议、通知公告或新闻通稿：可以用被动句、名词化表达、「经……」「鉴于……」「根据……」「为……」等书面连接，可以把主体放在句中或句末。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开）。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以句号结尾，句中不出现其他句号、问号或叹号。\n"
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")
#: H4（PREREG_HELDOUT_H4.md，保留集，只改 test 文档）：中英夹杂的工单/提交说明/站会速记体
SYS_H4 = ("你是一位习惯中英夹杂写工作记录的工程师或项目助理。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条改写成一句中英夹杂的速记，"
          "风格像工单备注、commit message 的中文说明、站会速记或交接便条：可以夹英文动词或术语（如 switch、bump、rollback、deprecate、pin、update、move、TBD、pending），"
          "可以省略主语前的修饰，可以用冒号、括号或箭头（→）。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因（起因可以写成中文）。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译成英文）。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以句号结尾，句中不出现其他句号、问号或叹号。\n"
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")

#: chain-r10（2026-10-12）：D4/D5 为 dev 改写集（只改 dev 文档），H5 为新保留集（只改 test 文档，提示词与 D4/D5 均不同）。
#: D4：与 H4 同一提示词 SYS_H4，用于在 dev 文档上复现中英夹杂速记体。
#: D5：英文句式框架为主、中文名词嵌入（邮件/英文周报口吻），并允许数值换写法（见 NUMFMT）。
NUMFMT = ("6. 「必须逐字出现」的字符串里，纯数字或 key=数字 形式的取值可以换写法（其余字符串仍须逐字）：可加千分位逗号（21600→21,600），"
          "可加单位（秒数写成 300s、300 sec、300秒），秒数可换算成整数分钟/小时/天（如 3600→1h、1小时，1800→30min、30分钟）；"
          "key=数字 可写成 key: 数字、key = 数字 或 key 数字。数值本身不许改变。\n")
SYS_D5 = ("你是一位在外企工作、写英文为主的工程师或项目助理。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条改写成一句以英文句式为框架、"
          "中文名词原样嵌入的句子，像英文邮件、英文周报或英文工单里的一句（如 “X 的 A updated to V due to R” 这类，但请自由变化说法、时态与语序）。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因（起因中文原样嵌入）。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译成英文），例外见第 6 条。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以中文句号「。」结尾，句中不出现其他句号、问号或叹号。\n" + NUMFMT +
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")
#: H5（PREREG_HELDOUT_H5.md，保留集，只改 test 文档）：Jira 字段变更 / changelog 条目 / IM 群消息 / git log 一行 的极简速记，允许数值换写法
SYS_H5 = ("你是一位习惯用极简速记写变更记录的工程师或运营。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条改写成一行中英夹杂的极简记录，"
          "风格像 Jira 字段变更历史、changelog / release note 条目、IM 群里一句话同步、git log 一行或交接 checklist：可以用方括号标签（如 [变更]、[fix]）、"
          "「字段: 值」写法、英文动词过去式或缩写（updated、changed、moved、dropped、reverted、chg、upd、mv、rm、wip、tbd、n/a）、中英文标点混用、全角半角混用，可以省略「的」和连接词。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因（起因中文原样嵌入）。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译成英文），例外见第 6 条。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以中文句号「。」结尾，句中不出现其他句号、问号或叹号。\n" + NUMFMT +
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")
_NUMV = re.compile(r"^(?:(?P<k>[A-Za-z_][A-Za-z0-9_]*)=)?(?P<n>\d+)$")


def _num_forms(x):
    """bench 侧（与被测抽取器无关）的数值换写法等价表：返回可接受的正则列表；不是数值型取值返回 None。"""
    m = _NUMV.match(x)
    if not m:
        return None
    n = int(m.group("n")); forms = [re.escape(m.group("n")), re.escape(f"{n:,}")]
    units = [r"\s*(?:s|sec|secs|秒)"]
    for d, us in ((60, r"\s*(?:min|mins|m|分钟)"), (3600, r"\s*(?:h|hr|hrs|hour|hours|小时)"), (86400, r"\s*(?:d|day|days|天)")):
        if n % d == 0 and n >= d:
            forms.append(re.escape(str(n // d)) + us)
    num = r"(?<![\d,.])(?:" + "|".join(forms) + r")(?:" + "|".join(units) + r")?(?![\d,])"
    if m.group("k"):
        return [re.escape(m.group("k")) + r"\s*(?:=|:|：|\s)\s*" + num]
    return [num]


def _has(s, x):
    if x in s:
        return True
    if VARIANT not in ("d5", "h5", "h6", "h7", "h8", "h9", "h10", "h11"):
        return False
    f = _num_forms(x)
    return bool(f) and any(re.search(p, s) for p in f)

#: H6（PREREG_HELDOUT_H6.md，chain-r10 第 2 轮保留集，只改 test 文档；提示词与 dev 用的 SYS_H4/SYS_D5 及已暴露的 SYS_H5 都不同）：
#: 值班交接 / 群消息 / action item / 邮件主题行，允许属性在主体前、@提及与时间前缀、中文口语动词夹英文名词，并允许数值换写法
SYS_H6 = ("你是一位在中英双语团队里做值班交接和项目同步的同事。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条改写成一句中英夹杂的工作消息，"
          "风格像 oncall 交接记录、飞书/Slack 群里的同步、周会 action item 或邮件主题行：可以在句首加 @oncall、FYI、update、今早、刚刚 这类前缀，"
          "可以把属性写在主体前面（如「A of S」「S 这边 A」「A（S）」），可以用 = 或 ：赋值，可以用中文口语动词（改了、换成、挪到、拍板、先挂着）夹英文名词。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因（起因中文原样嵌入）。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译成英文），例外见第 6 条。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以中文句号「。」结尾，句中不出现其他句号、问号或叹号。\n" + NUMFMT +
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")

#: H7（PREREG_HELDOUT_H7.md，chain-r10 第 3 轮保留集，只改 test 文档）：**不列举任何写法手段**的通用中英夹杂工作速记——
#: 只给场景（各种工作沟通渠道），写法由模型自由决定，用来检验 dev 上积累的规则对「自然出现的速记」的覆盖，而不是对某份提示词清单的覆盖
SYS_H7 = ("你在一个中英双语的技术团队工作。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条写成一句你在日常工作沟通里会顺手写下的中英夹杂记录，"
          "渠道随你选（聊天、工单、文档批注、提交记录、会议速记、邮件等都可以），写法按你的习惯自由发挥，各条之间可以不一样。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因（起因中文原样嵌入）。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译成英文），例外见第 6 条。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以中文句号「。」结尾，句中不出现其他句号、问号或叹号。\n" + NUMFMT +
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")


#: H8（PREREG_R12.md，chain-r12 保留集，只改 test 文档；基础语料先经 h8_map.py 换实体、换取值）：场景换成移动端随手记/语音转写口述/
#: 表格备注/看板卡片/代码注释/Release Note 条目，不列举写法手段；与 SYS_H2–H7 均不同
SYS_H8 = ("你是一个中英双语产品研发团队的成员。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条写成一句你会在下面某个地方随手留下的中英夹杂文字："
          "手机上的随手记、语音转文字后的口述笔记、表格单元格里的备注、看板卡片标题、代码注释、Release Note 条目。场景和写法都由你决定，各条之间可以不一样。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因（起因中文原样嵌入）。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译成英文），例外见第 6 条。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以中文句号「。」结尾，句中不出现其他句号、问号或叹号。\n" + NUMFMT +
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")


#: H9（PREREG_R13.md，chain-r13 保留集，只改 test 文档；基础语料先经 h9_map.py 换实体、换取值，映射与 H8 不同）：场景换成
#: 审批流批注 / 运维变更单「变更内容」栏 / 售后工单回复 / 白板拍照 OCR 转写 / PRD 修订记录 / 表单自由填写栏 / 群机器人播报，不列举写法手段；与 SYS_H2–H8 均不同
SYS_H9 = ("你在一家中英双语的软件公司做产品和交付。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条写成一句会出现在下面某处的文字："
          "审批流里的批注意见、运维变更单的「变更内容」栏、售后工单的处理回复、周会白板拍照后 OCR 出来的一行、PRD 文档的修订记录、内部表单的自由填写栏、项目群机器人的自动播报。"
          "选哪种、怎么写都由你决定，各条之间尽量不一样，中英文都可以用。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因（起因中文原样嵌入）。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译成英文），例外见第 6 条。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以中文句号「。」结尾，句中不出现其他句号、问号或叹号。\n" + NUMFMT +
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")


#: H10（PREREG_R14.md，chain-r14 保留集，只改 test 文档；基础语料先经 h10_map.py 换实体、换取值，映射与 H8/H9 不同）：场景换成
#: 邮件主题行或正文首句 / 事故复盘时间线条目 / git 提交说明 / 日历邀请议程描述 / 客户回访电话记录摘要 / 知识库 FAQ 答案 / App 推送通知文案 / 口头汇报语音逐字稿，不列举写法手段；与 SYS_H2–H9 均不同
SYS_H10 = ("你在一家做 SaaS 产品的中英双语公司上班，经常要把内部的变化写给不同的人看。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条写成一句会出现在下面某处的文字："
           "一封邮件的主题行或正文第一句、事故复盘文档时间线里的一条、git 提交说明、日历邀请里的议程描述、客户回访电话的记录摘要、知识库 FAQ 的一条回答、App 推送通知的文案、口头汇报录音转成的逐字稿。"
           "用哪种、怎么写都由你决定，各条之间尽量不一样，中英文都可以用。要求：\n"
           "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因（起因中文原样嵌入）。\n"
           "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译成英文），例外见第 6 条。\n"
           "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
           "4. 不要引入任何别的名称或数值。\n"
           "5. 以中文句号「。」结尾，句中不出现其他句号、问号或叹号。\n" + NUMFMT +
           "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")


#: H11（PREREG_R15.md，chain-r15 保留集，只改 test 文档；基础语料先经 h11_map.py 换实体、换取值，映射与 H8/H9/H10 不同）：场景换成
#: 周报/日报里的进展条目 / 内部通讯稿或公众号推文里的一句 / 内部论坛跟帖 / 新人培训讲义 / 短信通知 / 用户访谈笔记 / Wiki 页面编辑摘要 / 智能音箱语音播报，不列举写法手段；与 SYS_H2–H10 均不同
SYS_H11 = ("你在一家中英双语的互联网公司做项目协调，同一件事常常要写进不同的地方。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条写成一句会出现在下面某处的文字："
           "周报或日报里的一条进展、内部通讯稿或公众号推文里的一句、内部论坛里的一条跟帖、新人培训讲义里的一句说明、发给相关人的短信通知、用户访谈笔记里的一行、Wiki 页面的编辑摘要、智能音箱的语音播报词。"
           "选哪种、怎么写都由你决定，各条之间尽量不一样，中英文都可以用。要求：\n"
           "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因（起因中文原样嵌入）。\n"
           "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译成英文），例外见第 6 条。\n"
           "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
           "4. 不要引入任何别的名称或数值。\n"
           "5. 以中文句号「。」结尾，句中不出现其他句号、问号或叹号。\n" + NUMFMT +
           "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")


TEMP = {"h2": 1.3, "d2": 1.3, "d3": 1.2}.get(VARIANT, 1.0)
DEVDOCS = {"猎户项目", "青石镇"}
TEST_ONLY = VARIANT in ("h2", "h3", "h4", "h5", "h6", "h7", "h8", "h9", "h10", "h11")       # 保留集：只改 test 文档
DEV_ONLY = VARIANT in ("d2", "d3", "d4", "d5")        # dev 改写集：只改 dev 文档
SYSP = {"h2": SYS_H2, "d2": SYS_H2, "d3": SYS_D3, "h3": SYS_H3, "h4": SYS_H4, "d4": SYS_H4, "d5": SYS_D5, "h5": SYS_H5, "h6": SYS_H6, "h7": SYS_H7, "h8": SYS_H8, "h9": SYS_H9, "h10": SYS_H10, "h11": SYS_H11}.get(VARIANT, SYS)
SEED0 = {"h2": 2000, "d2": 3000, "d3": 4000, "h3": 5000, "h4": 6000, "d4": 7000, "d5": 8000, "h5": 9000, "h6": 10000, "h7": 11000, "h8": 12000, "h9": 13000, "h10": 14000, "h11": 15000}.get(VARIANT)


if VARIANT in ("h8", "h9", "h10", "h11"):                           # 换名后的基础语料（h8_map.py / h9_map.py）
    def corpus():  # noqa: F811
        return load(os.path.join(D, f"corpus_{VARIANT}base.json"))


def event_sents():
    """[(cid, 句号, 原句, 必须逐字串)]：原句用本分支抽取器解析（原句式全部在表内）。"""
    out = []
    for c in corpus():
        if (TEST_ONLY and c["doc"] in DEVDOCS) or (DEV_ONLY and c["doc"] not in DEVDOCS):
            continue
        for i, s in enumerate(SPLIT.split(c["text"])):
            if not any(m in s for m in EV_MARK):
                continue
            ev = [e for e in extract(s) if e.op != "mention"]
            assert ev, s
            e = ev[0]
            req = [x for x in (e.entity, None if e.attr == "位置" else e.attr, e.value, e.alt, e.reason) if x]
            out.append((c["cid"], i, s, req))
    return out


def by_seg(evs):
    g = {}
    for t in evs:
        g.setdefault(t[0], []).append(t)
    return g


def prompt(items):
    lines = [f"{k + 1}. 原句：{s}\n   必须逐字出现：" + "；".join(f"「{x}」" for x in req) for k, (_, _, s, req) in enumerate(items)]
    return [{"role": "system", "content": SYSP}, {"role": "user", "content": "\n".join(lines)}]


def parse(content, n):
    m = re.search(r"\[.*\]", content or "", re.S)
    try:
        arr = json.loads(m.group(0)) if m else None
    except ValueError:
        arr = None
    return arr if isinstance(arr, list) and len(arr) == n and all(isinstance(x, str) for x in arr) else None


def ok(sent, req):
    s = sent.strip()
    if VARIANT != "h1" and re.search(r"[？?！!]", s):
        return False
    return bool(s) and s.endswith("。") and s.count("。") == 1 and all(_has(s, x) for x in req)


def cost():
    try:
        return sum(json.loads(l)["cost"] for l in open(L.COSTLOG))
    except OSError:
        return 0.0


def gen_seg(items):
    """返回每句改写（None＝3 次都不过校验）。逐句判：某次调用里过校验的句子即采用，不过的再试。"""
    res = [None] * len(items)
    for attempt in range(3):
        todo = [k for k in range(len(items)) if res[k] is None]
        if not todo or cost() > BUDGET_USD:
            break
        sub = [items[k] for k in todo]
        r = L.call(prompt(sub), max_tokens=2000, temperature=TEMP, thinking=False, tag=f"cb:heldout_gen_{VARIANT}",
                   seed=(None if attempt == 0 else 100 + attempt) if VARIANT == "h1" else SEED0 + attempt)
        arr = parse(r.get("content"), len(sub))
        if arr is None:
            continue
        for k, s in zip(todo, arr):
            if ok(s, items[k][3]):
                res[k] = s.strip()
    return res


def run(budget):
    g = by_seg(event_sents()); t0 = time.time()
    resp = load(os.path.join(D, "gen_raw.json"), {})
    todo = [cid for cid in g if cid not in resp]

    def one(cid):
        if time.time() - t0 > budget or cost() > BUDGET_USD:
            return None
        return cid, gen_seg(g[cid])
    from concurrent.futures import as_completed
    ex = ThreadPoolExecutor(6)
    futs = [ex.submit(one, cid) for cid in todo]
    try:
        for f in as_completed(futs, timeout=budget + 20):
            r = f.result()
            if r:
                resp[r[0]] = r[1]
                dump(os.path.join(D, "gen_raw.json"), resp)     # 逐段落盘：被外层超时杀掉也不丢
    except Exception as e:  # noqa: BLE001
        print("stop:", type(e).__name__, flush=True)
    ex.shutdown(wait=False, cancel_futures=True)
    n = sum(len(v) for v in resp.values()); bad = sum(x is None for v in resp.values() for x in v)
    print(f"segs {len(resp)}/{len(g)} sents {n} fail {bad} cost_total ${cost():.4f}", flush=True)


def build():
    g = by_seg(event_sents()); resp = load(os.path.join(D, "gen_raw.json"))
    assert set(resp) == set(g), (len(resp), len(g))
    rw = {}
    for cid, items in g.items():
        for (c, i, s, req), new in zip(items, resp[cid]):
            rw[f"{c}|{i}"] = {"orig": s, "new": new, "req": req}
    out = []
    for c in corpus():
        sents = SPLIT.split(c["text"])
        if (TEST_ONLY and c["doc"] in DEVDOCS) or (DEV_ONLY and c["doc"] not in DEVDOCS):
            out.append(c); continue
        for i in range(len(sents)):
            r = rw.get(f"{c['cid']}|{i}")
            if r and r["new"]:
                sents[i] = r["new"]
        out.append(dict(c, text="".join(sents)))
    dump(os.path.join(D, "rewrite_map.json"), rw)
    dump(os.path.join(D, f"corpus_{VARIANT}.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    fails = sum(1 for r in rw.values() if not r["new"])
    print(f"event_sents {len(rw)} fallback_orig {fails} corpus_sha {h}")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(float(sys.argv[2]) if len(sys.argv) > 2 else 100)
    else:
        build()
